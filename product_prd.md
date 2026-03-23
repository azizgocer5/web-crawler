# Product Requirements Document (PRD)
## Project: Mini Google (Async Web Crawler + Search)
## Repository: azizgocer5/web-crawler
## Date: 2026-03-19

---

## 1) Objective

The objective of this project is to build a simple “Mini Google” system using **Python** and **SQLite**, with asynchronous crawling and searchable indexed content.

The system must provide two core capabilities:

1. **Index/Crawl**: Start from a given origin URL, visit pages, extract content, discover links, and continue crawling up to depth `k`.
2. **Search**: Query indexed pages and return relevant results based on a simple relevance strategy.

---

## 2) Scope

### In Scope
- `index(origin, k)` function
- `search(query)` function
- Persistent storage with SQLite
- Asynchronous crawling using `asyncio`
- Backpressure control using Semaphore and/or bounded Queue
- Simple CLI interface for commands and runtime visibility
- Ability to run search while crawling is still ongoing

### Out of Scope (MVP v1)
- Distributed architecture
- Advanced ranking algorithms (e.g., PageRank)
- Large-scale production hardening
- Full web-based GUI

---

## 3) Functional Requirements

### FR-1: Indexing
The system must support `index(origin, k)` to start crawling.

- `origin`: starting URL
- `k`: maximum crawl depth
- `k=0`: only origin page
- `k=1`: origin + links found on origin
- `k=2`: next-level links included

Crawler behavior:
- Download page content
- Extract `title` and visible `body` text
- Parse outgoing links
- Add eligible links to crawl queue
- Avoid duplicate processing of the same URL (deduplication)

### FR-2: Search
The system must support `search(query)` over indexed pages.

- Baseline relevance policy:
  - Query match in title = higher score
  - Query match in body = lower score
- Results must be sorted by relevance score (highest first)
- Each result MUST be returned as a tuple in the format `(relevant_url, origin_url, depth)` to match the technical assignment requirements.

### FR-3: Concurrency and Continuity
- Search must work while indexing is still running.
- Queue state must persist in SQLite so the crawler can resume after restart.

### FR-4: Backpressure
The crawler may discover URLs faster than they can be processed; the system must remain stable.

- Queue size must have an upper bound
- Worker concurrency must be limited
- When queue is full, producers must slow down or wait

---

## 4) Technical Requirements

- Language: **Python**
- Database: **SQLite**
- Async runtime: **asyncio**
- HTTP client (recommended): `aiohttp`
- HTML parser: Standard library `html.parser` (to satisfy language-native requirement)
- Runtime interface: CLI

---

## 5) Data Model (Initial Schema Draft)

### 5.1 Pages Table
Stores crawled/visited pages.

Suggested fields:
- `id` (PK)
- `url` (UNIQUE)
- `origin_url` (TEXT)
- `title` (TEXT)
- `body` (TEXT)
- `depth` (INTEGER)
- `status` (TEXT: success/failed)
- `error` (TEXT, nullable)
- `created_at` (DATETIME)
- `updated_at` (DATETIME)
- `last_crawled_at` (DATETIME)

### 5.2 Queue Table
Stores URLs to be processed and enables resume capability.

Suggested fields:
- `id` (PK)
- `url` (UNIQUE)
- `origin_url` (TEXT)
- `depth` (INTEGER)
- `state` (TEXT: pending/processing/done/failed)
- `discovered_from` (TEXT, nullable)
- `priority` (INTEGER, default 0)
- `attempt_count` (INTEGER, default 0)
- `last_error` (TEXT, nullable)
- `created_at` (DATETIME)
- `updated_at` (DATETIME)

---

## 6) Relevance Strategy (MVP)

Simple scoring approach:

- Title exact/substring match: +5
- Body match: +1 (or frequency-based +n)
- Optional penalty for empty/very short pages

Sort results using `score DESC`.

---

## 7) Error Handling and Reliability

- Invalid URLs, timeouts, and HTTP 4xx/5xx errors must be logged
- A failed worker should not crash the whole system
- Failed URLs should be marked as `failed`
- `attempt_count` should increase for retries (limited retries in MVP)

---

## 8) Performance and Safety Notes

- Limit concurrent workers (`Semaphore`)
- Limit queue capacity (backpressure)
- Optionally apply politeness delay per domain
- Normalize URLs to reduce duplicate crawling

---

## 9) CLI Requirements (MVP)

Basic commands:

- `index <origin> <k>` (Start new crawl)
- `resume` (Resume a previously interrupted crawl from queue)
- `search <query>`
- `status` (Show queue size, indexed pages count, backpressure state)

Runtime visibility should include:
- Active worker count
- Queue size
- Total indexed pages

---

## 10) Acceptance Criteria

1. `index(origin, k)` starts crawling and respects depth `k`.
2. Visited pages are saved in `Pages`.
3. Discovered URLs are managed in `Queue`.
4. System can resume from persisted queue after restart.
5. `search(query)` works while crawl is running.
6. Backpressure prevents uncontrolled queue growth.
7. Duplicate URLs are not processed repeatedly.
8. CLI provides observable crawl/search status.

---

## 11) Delivery Plan

- **Phase 1:** PRD + schema finalization
- **Phase 2:** Core async crawler + persistent queue
- **Phase 3:** Search + relevance scoring
- **Phase 4:** CLI observability + stability improvements
- **Phase 5:** Enhancements (retry policy, politeness, scoring refinements)

---

## 12) MVP Success Metrics

- Crawls a small/medium site to target depth without crashing
- Returns meaningful ranked search results
- Resumes from saved state after restart