# Web Crawler & Search Engine

This project is a concurrent, asynchronous web crawler and search engine built entirely with Python native libraries (`asyncio`, `sqlite3`, `html.parser`) fulfilling all the requirements of the web crawler assignment. It is designed to be highly scalable on a single machine, featuring background threading, Write-Ahead Logging (WAL) for concurrent DB access, and robust backpressure management.

## Features

- **Index (Depth `k`) & Deduplication:** 
  Given an origin URL, crawls up to depth `k` without ever crawling the same page twice. It strictly uses `html.parser` instead of large external libraries (like Scrapy or BeautifulSoup).
- **Simultaneous Search & Indexing:**
  Search queries can be executed in the CLI while the background crawler is actively indexing new pages. This is achieved using SQLite WAL mode and a non-blocking asyncio event loop.
- **Search Triples:**
  The ranking algorithm scores results based on title and body hits, and returns exactly the requested format: `(relevant_url, origin_url, depth)`.
- **Backpressure & Queue Management:**
  Pulls batches of links from the SQLite persistent queue into a bounded in-memory `asyncio.Queue`. When the in-memory queue reaches its limit, the crawler respects the backpressure and pauses further DB extraction.
- **Interactive CLI & State Viewing:**
  Provides an easy-to-use menu to start crawling, perform searches, and view real-time system state (pages crawled, queue depth, and backpressure status).
- **Resume Capability (Bonus):**
  If interrupted (e.g., Ctrl+C), crawls can be resumed seamlessly. The crawler remembers the `max_depth` target using a `Settings` table and picks up exactly where it left off, avoiding redundant downloads.

## How to Run Locally (Localhost Runnable)

1. **Install dependencies:**
   Make sure you have Python 3.9+ installed.
   ```bash
   pip install aiohttp aiosqlite
   ```

2. **Start the application:**
   ```bash
   python main.py
   ```

3. **Using the CLI:**
   - Press `1` to **Start Indexing** (Enter URL and Depth `k`). The crawler runs in the background.
   - Press `3` to **Search**, even while indexing is running.
   - Press `4` to **View the state of the system** (e.g. indexing progress, queue depth, back pressure status).
   - Press `2` to **Resume** if you previously stopped the crawler. It will fetch the saved depth from the database and continue.

## Project Anatomy

- `main.py`: Interactive CLI and entry point.
- `crawler_service.py`: Contains the engine (`CrawlerService`). Manages the asyncio event loop, the workers, html parsing, DB locking, and backpressure logic.
- `database.py`: Handles SQLite connection initialization, state tracking logic (`get_stats`), search queries, and the Settings table for the resume feature.
- `product_prd.md` / `recommendation.md` / `crawler_project_architecture.md`: Project documentation and production deployment recommendations.