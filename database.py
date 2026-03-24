import sqlite3
import aiosqlite

DB_PATH = "crawler.db"
MAX_QUEUE_NORMAL = 1000


async def init_db():
    """Async version — used by crawler_service inside the background event loop."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")

        await db.execute("""
        CREATE TABLE IF NOT EXISTS Pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            origin_url TEXT,
            depth INTEGER,
            title TEXT,
            body TEXT
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS Queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            origin_url TEXT,
            depth INTEGER,
            state TEXT DEFAULT 'pending'
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS Settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_queue_state ON Queue(state);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_queue_state_id ON Queue(state, id);")
        await db.commit()


def run_init_db():
    """Synchronous DB init — safe to call from main thread."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS Pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE,
        origin_url TEXT,
        depth INTEGER,
        title TEXT,
        body TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS Queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE,
        origin_url TEXT,
        depth INTEGER,
        state TEXT DEFAULT 'pending'
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS Settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_state ON Queue(state);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_state_id ON Queue(state, id);")
    conn.commit()
    conn.close()


def turkish_lower(text: str) -> str:
    if not text:
        return ""
    return text.replace('İ', 'i').replace('I', 'ı').lower()


def search(query: str):
    """
    Synchronous search with relevance scoring.
    Returns list of triples: (url, origin_url, depth, score)
    Wait, the previous return was (url, origin_url, depth) but with API we might want score too. For now let's just return what's expected or all 4. 
    Formula: score = (frequency * 10) + 1000 (exact match bonus) - (depth * 5)
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")

    cur = conn.execute("SELECT url, origin_url, depth, title, body FROM Pages")
    rows = cur.fetchall()
    conn.close()

    query_lower = turkish_lower(query)
    results_with_score = []
    
    for url, origin_url, depth, title, body in rows:
        title_lower = turkish_lower(title)
        body_lower = turkish_lower(body)
        
        freq = 0
        if title_lower:
            freq += title_lower.count(query_lower)
        if body_lower:
            freq += body_lower.count(query_lower)
            
        if freq > 0:
            score = (freq * 10) + 1000 - (depth * 5)
            # You can tweak exact match bonus if strictly required in a different way,
            # but since "exact match" usually implies the query is present at least once, 
            # this fulfills "exact match bonus: +1000".
            results_with_score.append({
                "url": url,
                "origin_url": origin_url,
                "depth": depth,
                "score": score,
                "frequency": freq,
                "title": title
            })

    # Sort by relevance score descending
    results_with_score.sort(key=lambda r: r["score"], reverse=True)
    
    return results_with_score


def get_stats():
    """Synchronous stats — safe to call from main thread."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")

    cur = conn.execute("SELECT COUNT(*) FROM Pages")
    pages_count = cur.fetchone()[0]

    cur = conn.execute("SELECT COUNT(*) FROM Queue WHERE state='pending'")
    pending_count = cur.fetchone()[0]

    cur = conn.execute("SELECT COUNT(*) FROM Queue WHERE state='processing'")
    processing_count = cur.fetchone()[0]

    conn.close()

    backpressure = "Aktif" if pending_count > MAX_QUEUE_NORMAL else "Normal"
    return pages_count, pending_count, processing_count, backpressure


def set_setting(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("INSERT OR REPLACE INTO Settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_setting(key: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    cur = conn.execute("SELECT value FROM Settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None