import asyncio
import threading
import traceback
from urllib.parse import urljoin, urldefrag, urlparse
import logging

import aiohttp
import aiosqlite

from database import DB_PATH, init_db

logger = logging.getLogger("CrawlerLogger")
logger.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler("crawler_requests.log", encoding="utf-8")
file_handler.setFormatter(log_formatter)
if not logger.handlers:
    logger.addHandler(file_handler)



class CrawlerService:
    def __init__(self, worker_count: int = 15, queue_maxsize: int = 1000):
        self.loop = None
        self.thread = None
        self.stop_event = None

        self.in_memory_queue = None
        self.workers = []
        self.http_session = None

        self.active_index = False
        self.worker_count = worker_count
        self.queue_maxsize = queue_maxsize

        self.state_lock = threading.Lock()
        self.current_job = None

        # Shared DB connection — opened once per crawl job
        self.db = None
        # Serialize all DB writes through a single asyncio.Lock
        self.db_lock = None

        # In-memory set for quick duplicate URL filtering (per-job only)
        self.seen_urls = set()

    def _write_report(self, url: str, links: list):
        import datetime
        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        lines = [f"[{now}] {url} crawl için verildi, bunun içinde {len(links)} link tespit edildi."]
        for i, link in enumerate(links, 1):
            lines.append(f"  link{i}: {link} -> bunun crawlı sıraya eklendi")
        lines.append("-" * 60)
        try:
            with open("crawl_report.txt", "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception:
            pass

    def _write_report_error(self, url: str, error_msg: str):
        import datetime
        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        lines = [
            f"[{now}] {url} crawl için verildi fakat hata alındı: {error_msg}",
            "-" * 60
        ]
        try:
            with open("crawl_report.txt", "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception:
            pass

    def start_background_loop(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._thread_target, daemon=True)
        self.thread.start()

    def _thread_target(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.stop_event = asyncio.Event()
        self.in_memory_queue = asyncio.Queue(maxsize=self.queue_maxsize)
        self.db_lock = asyncio.Lock()
        self.loop.run_forever()
        self.loop.close()

    def start_indexing(self, origin_url: str = None, max_depth: int = 0, resume_only: bool = False):
        if not self.loop:
            raise RuntimeError("Background loop not started yet.")

        with self.state_lock:
            if self.active_index:
                return False, "Crawler is already running."
            self.active_index = True
            if resume_only:
                self.current_job = {"resume": True}
            else:
                self.current_job = {"origin_url": origin_url, "max_depth": max_depth}

        fut = asyncio.run_coroutine_threadsafe(
            self._run_index_job(origin_url, max_depth, resume_only), self.loop
        )

        def _done_callback(f):
            try:
                f.result()
            except Exception as e:
                logger.error(f"[Background crawler error] {e}")
                print(f"[Background crawler error] {e}", flush=True)
            finally:
                with self.state_lock:
                    self.active_index = False
                    self.current_job = None

        fut.add_done_callback(_done_callback)
        return True, "Index job scheduled."

    def is_indexing(self):
        with self.state_lock:
            return self.active_index

    def shutdown(self):
        if not self.loop:
            return

        async def _shutdown():
            if self.stop_event:
                self.stop_event.set()

            for _ in range(len(self.workers)):
                await self.in_memory_queue.put(None)

            if self.workers:
                await asyncio.gather(*self.workers, return_exceptions=True)

            if self.http_session:
                await self.http_session.close()

            if self.db:
                await self.db.close()

        fut = asyncio.run_coroutine_threadsafe(_shutdown(), self.loop)
        try:
            fut.result(timeout=10)
        except Exception:
            pass

        self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread:
            self.thread.join(timeout=3)

    async def _run_index_job(self, origin_url: str, max_depth: int, resume_only: bool):
        await init_db()

        # Single shared DB connection for the entire crawl job
        self.db = await aiosqlite.connect(DB_PATH)
        await self.db.execute("PRAGMA journal_mode=WAL;")
        await self.db.execute("PRAGMA synchronous=NORMAL;")
        await self.db.execute("PRAGMA busy_timeout=5000;")
        await self.db.execute("PRAGMA cache_size=-8000;")  # 8MB cache

        timeout = aiohttp.ClientTimeout(total=15, connect=5)
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=3, ttl_dns_cache=300)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
        self.http_session = aiohttp.ClientSession(
            timeout=timeout, headers=headers, connector=connector
        )

        if not resume_only:
            # ── JOB ISOLATION ──
            # Clear the ENTIRE Queue so this job starts completely fresh.
            # Pages table is kept (already-crawled content remains searchable).
            async with self.db_lock:
                await self.db.execute("DELETE FROM Queue")
                await self.db.execute("""
                    INSERT OR IGNORE INTO Queue (url, origin_url, depth, state)
                    VALUES (?, ?, ?, 'pending')
                """, (origin_url, origin_url, 0))
                await self.db.commit()
            msg = f"Starting crawl: {origin_url} (depth={max_depth})"
            logger.info(msg)
            print(f"[Crawler] {msg}", flush=True)
        else:
            msg = "Resuming crawl from saved queue..."
            logger.info(msg)
            print(f"[Crawler] {msg}", flush=True)
            # Reset any items that were left in 'processing' state during an ungraceful shutdown
            async with self.db_lock:
                await self.db.execute("UPDATE Queue SET state='pending' WHERE state='processing'")
                await self.db.commit()

        if not resume_only:
            self.seen_urls = set()
        else:
            # Sadece yarım kalmış bir işe devam ediyorsak halihazırda veritabanında olanları bir daha indirmeyelim.
            async with self.db_lock:
                cur = await self.db.execute("SELECT url FROM Pages")
                rows = await cur.fetchall()
                self.seen_urls = {r[0] for r in rows}

        self.workers = [
            asyncio.create_task(self._worker(i, max_depth))
            for i in range(self.worker_count)
        ]

        idle_rounds = 0
        while True:
            if self.stop_event.is_set():
                break

            fed = 0
            space = self.queue_maxsize - self.in_memory_queue.qsize()
            if space > 0:
                batch = await self._claim_batch_pending(min(space, 100))
                for row in batch:
                    await self.in_memory_queue.put(row)
                    fed += 1

            pending_count, processing_count = await self._db_queue_counts()
            qsize = self.in_memory_queue.qsize()

            if pending_count == 0 and processing_count == 0 and qsize == 0:
                idle_rounds += 1
                if idle_rounds >= 3:
                    break
            else:
                idle_rounds = 0

            # Adaptive sleep: shorter when there's work, longer when idle
            if fed > 0:
                await asyncio.sleep(0.05)
            elif qsize > 0:
                await asyncio.sleep(0.1)
            else:
                await asyncio.sleep(0.3)

        for _ in range(len(self.workers)):
            await self.in_memory_queue.put(None)
        await asyncio.gather(*self.workers, return_exceptions=True)

        if self.http_session:
            await self.http_session.close()
            self.http_session = None

        if self.db:
            await self.db.close()
            self.db = None

        self.workers = []
        self.seen_urls.clear()
        
        msg = "Crawl job finished."
        logger.info(msg)
        print(f"[Crawler] {msg}", flush=True)

    async def _claim_batch_pending(self, batch_size: int = 100):
        """Claim up to batch_size pending items in a single DB transaction."""
        try:
            async with self.db_lock:
                cur = await self.db.execute("""
                    SELECT id, url, origin_url, depth
                    FROM Queue
                    WHERE state='pending'
                    ORDER BY id
                    LIMIT ?
                """, (batch_size,))
                rows = await cur.fetchall()

                if not rows:
                    return []

                ids = [r[0] for r in rows]
                placeholders = ",".join("?" * len(ids))
                await self.db.execute(
                    f"UPDATE Queue SET state='processing' WHERE id IN ({placeholders})",
                    ids
                )
                await self.db.commit()
                return rows
        except Exception as e:
            logger.error(f"Error claiming batch: {e}")
            print(f"[Crawler] Error claiming batch: {e}", flush=True)
            return []

    async def _worker(self, worker_id: int, max_depth: int):
        while True:
            item = await self.in_memory_queue.get()
            if item is None:
                self.in_memory_queue.task_done()
                break

            qid, url, root_origin, depth = item
            try:
                await self._process_url(qid, url, root_origin, depth, max_depth)
            except Exception as e:
                logger.error(f"Worker-{worker_id} - Error processing {url}: {e}")
                print(f"[Worker-{worker_id}] Error processing {url}: {e}", flush=True)
                traceback.print_exc()
                await self._mark_done(qid)
            finally:
                self.in_memory_queue.task_done()

    async def _process_url(self, qid: int, url: str, root_origin: str, depth: int, max_depth: int):
        # Fast in-memory duplicate check (avoids DB query)
        if url in self.seen_urls:
            await self._mark_done(qid)
            return

        # Fetch HTML with up to 4 retries (to handle Wikipedia rate-limits/timeouts)
        html = None
        last_error = "Bilinmeyen hata veya sayfa boş"
        import random
        for attempt in range(4):
            try:
                # Eş zamanlı saldıran işçileri dağıtarak bot korumasına takılmayı önler
                await asyncio.sleep(random.uniform(0.2, 0.5))
                async with self.http_session.get(url, allow_redirects=True) as resp:
                    if resp.status == 429:
                        last_error = "HTTP 429 Too Many Requests"
                        # Eğer sunucu 'Şu kadar saniye bekle' diyorsa (Retry-After), ona uyar. Demiyorsa katlanarak bekler.
                        retry_after = int(resp.headers.get("Retry-After", 2 + attempt * 2))
                        await asyncio.sleep(retry_after)
                        continue
                    ctype = resp.headers.get("Content-Type", "")
                    if resp.status == 200 and "text/html" in ctype:
                        html = await resp.text(errors="ignore")
                        last_error = None
                    else:
                        last_error = f"HTTP Status: {resp.status}, Content-Type: {ctype}"
                    break
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                last_error = f"Ağ Hatası: {type(e).__name__}"
                await asyncio.sleep(1)
            except Exception as e:
                last_error = f"Beklenmeyen Hata: {str(e)}"
                logger.error(f"HTTP error for {url}: {e}")
                print(f"[Crawler] HTTP error for {url}: {e}", flush=True)
                break

        if not html:
            logger.warning(f"Skipping {url} - Reason: {last_error if last_error else 'No HTML content'}")
            self._write_report_error(url, last_error if last_error else "Sayfa çekilemedi")
            await self._mark_done(qid)
            return

        # Parse HTML in a dedicated thread using standard library html.parser
        def extract_data():
            from html.parser import HTMLParser

            class MiniParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.title = ""
                    self.body_parts = []
                    self.links = []
                    self.in_title = False
                    self.exclude_tags = {'script', 'style', 'head', 'meta', 'link'}
                    self.current_tags = []

                def handle_starttag(self, tag, attrs):
                    if tag not in ('meta', 'link', 'br', 'hr', 'img', 'input'):
                        self.current_tags.append(tag)
                    if tag == 'title':
                        self.in_title = True
                    elif tag == 'a' and depth < max_depth:
                        for attr, value in attrs:
                            if attr == 'href':
                                self.links.append(value)
                                break

                def handle_endtag(self, tag):
                    if self.current_tags and self.current_tags[-1] == tag:
                        self.current_tags.pop()
                    if tag == 'title':
                        self.in_title = False

                def handle_data(self, data):
                    data_str = data.strip()
                    if not data_str:
                        return
                    if self.in_title:
                        self.title += data_str + " "
                    elif not any(t in self.exclude_tags for t in self.current_tags):
                        self.body_parts.append(data_str)

            parser = MiniParser()
            try:
                parser.feed(html)
            except Exception:
                pass
            
            _title = parser.title.strip()
            _body = " ".join(parser.body_parts)
            _links = []
            
            for href in parser.links:
                href = href.strip()
                if not href:
                    continue
                abs_url = urljoin(url, href)
                abs_url, _ = urldefrag(abs_url)
                p = urlparse(abs_url)
                if p.scheme in ("http", "https"):
                    norm = p._replace(fragment="").geturl()
                    _links.append((norm, root_origin, depth + 1))
            return _title, _body, _links

        title, body, child_links = await asyncio.to_thread(extract_data)

        # Add current URL to seen set
        self.seen_urls.add(url)

        # Single DB write: insert page + all child links + mark done
        async with self.db_lock:
            await self.db.execute("""
                INSERT OR REPLACE INTO Pages (url, origin_url, depth, title, body)
                VALUES (?, ?, ?, ?, ?)
            """, (url, root_origin, depth, title, body))

            if child_links:
                await self.db.executemany("""
                    INSERT OR IGNORE INTO Queue (url, origin_url, depth, state)
                    VALUES (?, ?, ?, 'pending')
                """, child_links)

            await self.db.execute("UPDATE Queue SET state='done' WHERE id=?", (qid,))
            await self.db.commit()
            logger.info(f"Successfully processed and recorded: {url}")
            self._write_report(url, [cl[0] for cl in child_links])

    async def _mark_done(self, qid: int):
        async with self.db_lock:
            await self.db.execute("UPDATE Queue SET state='done' WHERE id=?", (qid,))
            await self.db.commit()

    async def _db_queue_counts(self):
        async with self.db_lock:
            cur1 = await self.db.execute("SELECT COUNT(*) FROM Queue WHERE state='pending'")
            pending = (await cur1.fetchone())[0]
            cur2 = await self.db.execute("SELECT COUNT(*) FROM Queue WHERE state='processing'")
            processing = (await cur2.fetchone())[0]
            return pending, processing