# Community Voices — Beekeeping & Apiculture Forum

## Overview

A small web app that generates a **Community Voices Document** for a given message board community. This document contains a digest of what it's talked about in the past week (or day/month/year - see [Getting Started](#getting-started)), and a prediction of what it'll talk about next. This report is generated with a RAG (retrieval-augmented generation) pipeline over that forum's own recent posts.

## Timeline

This project was built by Ash Joyce for the Transcendent Endeavors "Community Voices" coding challenge, with the assistance of Claude.

The specification called for me to choose a message board topic that interests me, and I saw this as an opportunity to showcase one of my great passions: beekeeping! I am a third year backyard beekeeper in New Jersey, though my hives are currently dormant and will not be revived until at least next spring. 

Finding an online community to use as a source for a Community Voices Document for beekeepers was a real challenge. Facebook and Reddit famously block automated requests from bots, and the turnaround time to request a Reddit API key was too cumbersome for this challenge. Initially I chose Beemaster's Forum, one of my favorite boards, for this challenge. However, when I reached the live testing phase, I realized that my RAG pipeline was being blocked by their Cloudflare solution, probably after hitting it a few too many times. Oops.

So instead I changed the source to beekeepingforum.co.uk, a discussion board for beekeepers across the pond. While a good deal of discussion that takes place on these boards is regional, there's still a lot to be learned about different climates, ecological considerations, and cultural customs (for example, the Irish tradition of "Telling it to the Bees" and talking to hives about our daily lives, even going so far as to designate someone to bring condolences to our hives when we're no longer able to visit.) Plus, many beekeeping practices are universal!

However, even while using the Beemaster forum, I recognized that it was running off of SMF, and I also know of Xenforo and phpBB as platforms, and thought to myself "well, this platform doesn't have to be bound to exclusively one board".

Enter the adapter design pattern. The SMFAdapter, while vestigial to this implementation, represents the ability to point this app at any message board that is running the SMF platform. The XenForoAdapter was built for beekeepingforum.co.uk, but can be pointed at other forums using that platform. This ensures the extensibility of the app!

But enough about my thought process. Here are the brass tacks.

## How it works

The report generation produces a plain-language weekly digest of what an online community has been discussing, plus a prediction of what it'll discuss next, alongside a standard LLM report generation.

**How it works, at a glance** (full diagram + spec-item mapping in
[Architecture](#architecture) below):

1. **Crawl** a forum's recent-activity feed - bounded by a lookback
   window, a post cap, and an off-topic-board exclusion list - through a
   pluggable `ForumAdapter`, not code tied to one forum's exact markup.
2. **Chunk + embed** each post locally (`sentence-transformers`, no API
   key needed) into a SQLite + `sqlite-vec` vector store.
3. **Retrieve** the top-k most relevant chunks for a query, logging every
   retrieval for later stats.
4. **Generate** the document twice with Claude: once grounded in the
   retrieved chunks (RAG), once with zero retrieval (baseline).
5. **Serve** both, plus an embedding scatter plot and retrieval-frequency
   stats, through a FastAPI JSON API and a small decoupled vanilla-JS
   frontend - and download the generated document as a styled PDF named
   after whichever community was analyzed.

Nothing here is hardcoded to one specific forum - see
[Pointing this at a different forum](#pointing-this-at-a-different-forum).

## Getting Started

Start here either way - Docker needs nothing but Docker itself; running
it directly needs Python 3.11+.

```bash
git clone git@github.com:ashrosejoyce/transcendentcodechallenge.git
cd transcendentcodechallenge

cp .env.example .env
```

Then edit .env and set your own ANTHROPIC_API_KEY (get one at https://platform.claude.com/settings/keys — see note below) every other setting in .env.example is optional; defaults work out of the box for exploring the app against beekeepingforum.co.uk.

**On the API key:** the app reads `ANTHROPIC_API_KEY` from your environment (via `.env`, which is git-ignored). Reviewers should use their **own** key — never a key shared over chat/email — by generating one at platform.claude.com and dropping it into their local `.env`. The app will not run generation without it, but ingestion/embedding/retrieval/the visualization all work with no key at all.

You can also define the FORUM_BASE_URL and the FORUM_ADAPTER environment values to point to different message boards. Available adapters are xenforo and smf.

### Option A: Docker (recommended)

No local Python install needed - everything, including the embedding model, is baked into the image at build time.

```bash
docker compose up --build
```

Then open **http://localhost:8000**. Two containers, deliberately decoupled - no reverse proxy between them, just CORS (see `docker-compose.yml`):

| Service | What it is | Port |
|---|---|---|
| `frontend` | nginx serving the static UI - talks to `backend` directly and cross-origin | http://localhost:8000 |
| `backend` | FastAPI + crawler/RAG/generation pipeline + embedded SQLite (sqlite-vec) | http://localhost:8080 |

No separate database container: SQLite is an in-process file store, not a
service of its own, and is persisted across restarts via the `db-data`
named volume instead. The backend's Dockerfile also installs the CPU-only
PyTorch build explicitly (`sentence-transformers`'s default resolution
otherwise pulls several GB of unused CUDA libraries into an image that
never has a GPU).

To stop: `docker compose down` (add `-v` to also drop the persisted
database volume).

### Option B: Run locally with Python

Same decoupled shape as Docker: the backend and frontend are two
separate processes, each in its own terminal.

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

uvicorn app.main:app --reload --app-dir backend --port 8080
```

In a second terminal, serve the static frontend on port 8000 (any static
file server works - this one needs nothing beyond Python itself):

```bash
cd frontend
python3 -m http.server 8000
```

Then open **http://localhost:8000**.

### Using it

Either way, once it's running:

1. Click **"Refresh data from forum"** first — this starts a crawl in the
   background and returns immediately (see `api/ingest_job.py`), so a
   progress bar tracks real counts as they happen: an indeterminate sweep
   while discovery has no fixed total yet, then a real percentage once
   the number of topics to fetch is known. A real crawl under a polite
   rate limit (`CRAWL_REQUEST_DELAY_SECONDS`) can take a couple of
   minutes - that delay is real, not the UI being slow. Finishes with a
   green "Success — N posts saved, M chunks indexed" banner (red on
   failure), not a raw JSON dump.
2. Pick a **timeframe** (day/week/month/year - defaults to week) and click
   **"Generate"** — this runs the RAG pipeline and the no-retrieval
   baseline side by side over that window of posts, predicting the same
   length of time ahead, and logs the retrieval stats / updates the
   embedding scatter plot. See `generation/timeframe.py`.
3. Click **"Download report"** to save the RAG document, baseline, and
   full source list as a formatted PDF (`generation/report_pdf.py`),
   named after whichever community was analyzed (see
   `generation/report_filename.py`).

## Architecture

```
crawler (httpx + BeautifulSoup)
   -> discovers recent activity however the platform's ForumAdapter does
      it (SMF: one global feed; XenForo: per-board pagination - see
      "Pointing this at a different forum" below), bounded to the last
      N days and a max-post cap, skipping off-topic boards
   -> fetches each active topic once, keeps only in-window posts
        |
        v
chunking (paragraph-aware, overlapping)
        |
        v
embeddings (sentence-transformers, local, no API key)
        |
        v
SQLite + sqlite-vec vector store  <-- retrieval events logged here
        |
        v
retrieval (top-k nearest chunks, every retrieval logged for stats)
        |
        v
generation (Claude, via ANTHROPIC_API_KEY)
   -> RAG-grounded document (uses retrieved chunks)
   -> baseline document (same prompt, zero retrieval) --- the A/B pair
        |
        v
FastAPI JSON API  ->  decoupled frontend (vanilla JS, no build step,
                       cross-origin over CORS - see "Getting Started")
   - document view (RAG vs. baseline, side by side)
   - embedding scatter plot (PCA-flattened, spec item 3b)
   - most-retrieved-chunk stats (spec item 3c)
   - "Download report" -> WeasyPrint renders the same content as a PDF
```

Spec item mapping, for reviewers skimming against the brief:

| Spec item | Where |
|---|---|
| 1. Active community | beekeepingforum.co.uk (see [Choosing a forum](#choosing-a-forum)) |
| 2. Community Voices Document | `generation/document_generator.py`, rendered in the frontend |
| 3a. Vector store | SQLite + `sqlite-vec` (`db/schema.py`, `db/connection.py`) |
| 3b. Flattened embedding visualization | `rag/visualization.py` (PCA to 2D) + the scatter plot in the frontend |
| 3c. Retrieval stats | `retrieval_events` table, logged in `rag/retrieval.py`, surfaced via `/api/stats` and the bar chart |
| 4. Automated ingestion | `crawler/` (bounded, idempotent, skips off-topic boards) |
| 4b. Bounding data volume | lookback window + `CRAWL_MAX_POSTS` cap + board exclusion list, all in `.env` |
| 5. A/B comparison | `generation/ab_comparison.py`, rendered side by side in the UI |

## Running the tests

```bash
pytest
```

110 tests across 18 files:

| File | Covers |
|---|---|
| `test_parser.py` | HTML parsing against representative SMF-structure fixtures |
| `test_xenforo_parser.py` | HTML parsing against representative XenForo-structure fixtures, incl. sticky-thread flagging and quote/signature stripping |
| `test_http_client.py` | `RateLimiter`'s wait/no-wait timing logic in isolation, with `time.monotonic`/`time.sleep` mocked out - no real waiting |
| `test_ingest.py` | platform-agnostic fetch-phase orchestration (max-posts cap, per-post windowing, topic-fetch errors, phase transitions), against a fake HTTP client - no real network calls |
| `test_ingest_job.py` | the background-job state machine (idle/running/done/error transitions, "already running" guard), with the crawl/DB/indexing collaborators mocked out |
| `test_smf_adapter.py` | SMF's discovery mechanics: single global feed, paginated newest-first, stopping on the first too-old entry |
| `test_xenforo_adapter.py` | XenForo's discovery mechanics: per-board pagination, board exclusion skipping a fetch entirely, and sticky threads never triggering a false stop |
| `test_forum_adapter.py` | the `ForumAdapter` registry, and that crawl orchestration works with a fake adapter whose discovery mechanics resemble neither shipped platform |
| `test_chunking.py` | paragraph packing, overlap, edge cases (empty text, oversized paragraphs) |
| `test_timeframe.py` | day/week/month/year preset resolution, cutoff math, and unknown-label rejection |
| `test_prompts.py` | RAG vs. baseline prompt construction never leaks retrieved content into the baseline, and reflects the chosen timeframe |
| `test_report_filename.py` | report-filename slugification, parameterized per community and (optionally) timeframe |
| `test_report_pdf.py` | the markdown-lite-to-HTML conversion (headings, inline bold/italic, HTML-escaping) and that a real PDF comes out |
| `test_retrieval.py` | `retrieve()`'s row-mapping, `since`-cutoff filtering/overfetch, and retrieval-logging, against a stub DB connection |
| `test_indexing.py` | chunk/embed orchestration, with the embedding model and DB mocked out |
| `test_ab_comparison.py` | the RAG-vs-baseline A/B orchestration, with the LLM and retrieval mocked out |
| `test_repository.py` | all SQL that doesn't touch `sqlite-vec`, against a real in-memory SQLite DB (`save_posts` idempotency, `retrieval_counts` ordering, `corpus_stats`, …) |
| `test_visualization.py` | PCA projection actually clusters similar embeddings closer together than dissimilar ones |

## Design notes & honest limitations

**Embeddings run locally (sentence-transformers), not Voyage AI.** Anthropic
doesn't offer its own embedding model — their docs point to Voyage AI as a
separate paid service with its own API key. Requiring reviewers to sign up
for *two* API keys just to run a take-home project felt like the wrong
tradeoff, so embeddings run locally instead; only generation calls Claude.

**The forum parser targets SMF's stable conventions, not exact CSS
classes.** Simple Machines Forum (the software Beemaster's Forum runs on)
themes vary in their CSS, but two things are stable across every SMF
install because the software's own internal linking depends on them: topic
links always carry `topic=<id>.msg<id>`, and every individual post is
reachable at an `id="msg<id>"` anchor. `crawler/parser.py` is built around
those two invariants rather than guessing at theme-specific class names.
This was a deliberate choice, not a shortcut: during development, this
environment's network policy allowed a summarizing fetch of the live site
(enough to confirm real activity and general structure) but blocked raw
HTML retrieval and blocked installing Python dependencies entirely
(`pypi.org` was outside the sandbox's egress allowlist), so the parser was
built against representative fixtures modeled on SMF's documented
invariants (`tests/fixtures/`) rather than the live page's exact markup.
The packages that happened to already be present in that sandbox
(BeautifulSoup, lxml, httpx, numpy, pydantic, scikit-learn) were enough to
actually run 44 of the suite's assertions end-to-end there - including
`test_repository.py`'s SQL against a real in-memory SQLite database (every
table except the `sqlite-vec` virtual table needs no extension at all) -
which caught and fixed three real bugs along the way: a post-container
boundary that could bleed into a neighboring post, a naive-vs-timezone-aware
datetime comparison, and a board-exclusion filter that used exact string
equality against board names that actually drift (`"Forum Bylaws"` was in
the exclusion list, but the real board is `"Forum Bylaws 2019"` - fixed to
a case-insensitive substring match). `pytest` itself, FastAPI, `sqlite-vec`,
`anthropic`, and `sentence-transformers` could not be installed in that
sandbox, so the full suite and the live crawl should be treated as verified
by you, the first time you run this locally with normal internet access -
not by me. If Beemaster's markup has drifted from the assumptions above,
`crawler/parser.py` is the one file to check first.

**Bounding data volume:** the crawler's discovery pass stops paginating the
instant it crosses the lookback window (default 7 days), skips boards
matching `FORUM_EXCLUDED_BOARDS` before fetching a single topic page (for
XenForo specifically, this skips fetching an excluded board's listing at
all, rather than SMF's fetch-then-filter, since XenForo discovery is
already scoped per board), and hard-caps at `CRAWL_MAX_POSTS`. Re-running
ingestion is idempotent - already-stored posts are skipped by primary key.

**Clean Code pass:** after the first working version, the whole codebase
was re-read specifically against self-documenting naming, small
single-responsibility functions, and DRY. That pass had real findings, not
just a rubber stamp - e.g. `crawler/parser.py` had two near-duplicate
DOM-ancestor-walking functions (now one shared `_walk_ancestors` generator
plus two small predicate functions), magic numbers like the container
text-length threshold became named constants
(`_MIN_POST_CONTAINER_CHARS`), `crawler/ingest.py`'s page-discovery loop
had three responsibilities tangled together (now split into
`_fetch_recent_entries_page` / `_collect_in_window_topics` /
`_parse_timestamp_or_record_error`, each independently readable), and the
frontend's retrieval bar-chart had inline style mutation doing double duty
as layout logic (now a named `buildBarTrack` helper with the positioning
rule in CSS, not JS). Test coverage grew from 25 to 44 assertions in the
same pass, adding the retrieval, indexing, and repository-SQL tests that
were missing the first time.

**A later hardening pass** (SOLID review, Dockerization, generalization)
fixed a real dependency-inversion violation (`db/repository.py` imported
its `IngestedPost` type from `crawler/ingest.py` - a low-level module
reaching up into a higher-level one; moved to the neutral `models.py`),
replaced the crawler's hardcoded SMF assumptions with the `ForumAdapter`
interface described above, added the two-container Docker setup, and
moved every remaining Beemaster/beekeeping-specific default (community
name, off-topic boards) out of code and into `.env` - the codebase itself
now assumes nothing about which forum or community it's pointed at. Test
coverage grew again, from 44 to 54 assertions, covering the adapter
registry and the new report-filename logic.

**A `ruff` pass** added a real linter (`pyproject.toml`'s `[tool.ruff]`,
line-length matched to this codebase's existing style rather than the
88-char default) and fixed everything it found: import sorting/dedup,
`typing.Iterable`/`Sequence` → `collections.abc`, `datetime.timezone.utc`
→ the `UTC` alias, missing explicit `zip(..., strict=...)`, a lambda
assigned to a variable rewritten as a small function, and a few
over-length lines reflowed.

**Report timeframe was parameterized** (`generation/timeframe.py`):
`/api/generate` now accepts `timeframe: "day"|"week"|"month"|"year"`
(defaulting to the spec's original "week"), which drives both the
document's section headings ("This Past Month" / "the coming month", …)
and an actual `since`-cutoff on retrieval - `rag/retrieval.py` overfetches
a wide vec0 candidate pool and date-filters/trims to `top_k` when a
timeframe is given, since sqlite-vec's KNN has no notion of the joined
`posts.posted_at` column and a plain `k=top_k` MATCH would return the
globally-nearest chunks *before* any date filtering could happen.

**A live smoke test against the real target found and fixed two SMF
parser bugs** that no unit test had caught, because the only fixtures on
hand were shaped after Beemaster's specific theme: (1) the timestamp
regex assumed Beemaster's "Today **at** 8:04:12 PM" date-format setting,
but SMF's date format is admin-configurable per install, and other real
installs use "Today**,** 8:04:12 PM" instead; (2) post-body extraction
did `get_text()` on the whole post container, which is fine when a
theme keeps the author sidebar and timestamp outside it (as the existing
fixtures happened to), but leaked "Posts: 332", "Logged", etc. into the
body on themes that nest everything inside the same container. Both are
now covered by regression tests (`test_parse_smf_timestamp_comma_separated_variant`,
`test_parse_topic_page_excludes_author_sidebar_on_nested_themes`).

**Beemaster's Forum went behind a Cloudflare bot challenge** (confirmed
from three independent network paths - this wasn't an IP-reputation
issue, but active bot-management rejecting every non-browser client), so
a second adapter (`xenforo_adapter.py` / `xenforo_parser.py`) was built
for beekeepingforum.co.uk, and the `ForumAdapter` interface itself was
restructured: discovery moved from several small shared pieces
(`recent_activity_path` + `parse_recent_activity` + `topic_path`) into
one adapter-owned `discover_recent_topics()` method, because XenForo's
per-board pagination isn't just different URLs from SMF's single global
feed - it's a different *stopping algorithm* (per board, not global; and
immune to a pinned sticky thread's own age). Forcing both through one
shared loop would have meant either breaking XenForo or smuggling SMF
assumptions into "platform-agnostic" code. See `forum_adapter.py`'s
module docstring for the full reasoning. Test coverage grew from 69 to 93
assertions in this pass.

**Frontend and backend were decoupled onto separate ports** (8000 for the
static UI, 8080 for the API) instead of nginx reverse-proxying `/api/` to
one same-origin backend. That trade-off is real: it's simpler to reason
about (two independent processes, neither aware of the other's existence
- the frontend's `API_BASE` just assumes the API lives on port 8080 of
whatever host served the page) at the cost of needing actual CORS
(`main.py`) instead of getting a free ride from same-origin requests.
Chosen because it was asked for directly, not because it's strictly
better - the earlier nginx-proxy setup was a perfectly reasonable choice
too.

**PDF generation uses WeasyPrint** (`generation/report_pdf.py`) - real
HTML+CSS converted to a PDF, so the "Download report" button produces a
styled document instead of a raw `.txt` dump, with zero manual
drawing/positioning code to maintain. One real surprise worth recording:
WeasyPrint imports cleanly and renders correctly with nothing extra
installed in a normal dev environment, which looks like proof it's
pure-Python - it isn't. It `dlopen()`s Pango/GLib at import time and only
worked locally because those happened to already be present on that
machine for unrelated reasons; it failed immediately in the actual
`python:3.12-slim` Docker image, which is the environment that matters.
Caught by testing the real container, not the dev venv - `backend/Dockerfile`
now installs `libpango-1.0-0`, `libpangoft2-1.0-0`, `libgdk-pixbuf-2.0-0`,
and `fonts-dejavu-core` explicitly.

**Ingestion runs as a background job, not one blocking request**
(`api/ingest_job.py`): a real crawl under a polite rate limit can take
minutes, so `/api/ingest` starts it and returns immediately, and the
frontend polls `/api/ingest/status` for a progress bar - genuinely
accurate where the numbers are knowable (a real "N of M topics fetched"
once discovery finishes), honestly indeterminate where they aren't
(discovery has no fixed page count to aim for). Replaced a raw
`JSON.stringify()` debug dump in the UI with that progress bar and a
plain success/error banner.

**A second SOLID pass** re-read every class and function against all
five principles specifically (not just Clean Code generally). Two real
gaps: `ingest.py` and both adapters type-hinted the *concrete*
`PoliteForumClient` even though tests were already duck-typing fakes
against it - added an explicit `ForumClient` Protocol (`http_client.py`)
so that inversion is now visible in the type system, matching the
`ForumAdapter` pattern already used for platforms. And `PoliteForumClient`
bundled "reach the network" with "pace requests" in one class - split
into a standalone `RateLimiter`, independently unit-testable with mocked
time instead of only ever being exercised indirectly through a crawl.
`report_pdf.render_report_pdf` was similarly split into a pure
`_build_html` (testable as plain text) and a two-line wrapper that just
calls WeasyPrint. One thing deliberately *not* changed: `IngestReport`
knowingly serves two purposes (final summary and live progress snapshot)
- splitting it would mean threading two parallel objects through the
crawl for the same underlying counters, for no real benefit.

**The spec's optional `/insights` step:** this was built in Cowork (an
Anthropic product for delegating file/task work), not the Claude Code CLI,
so there's no `/insights` command available in this environment to run and
share output from. Noting that explicitly rather than fabricating output
for a command that wasn't actually run.

## Project structure

```
backend/app/
  crawler/       HTTP client + rate limiter (http_client.py), ingestion orchestration, pluggable ForumAdapter (forum_adapter.py, adapter_registry.py); parser.py + smf_adapter.py (SMF) and xenforo_parser.py + xenforo_adapter.py (XenForo) are the two shipped implementations
  rag/            chunking, embeddings, vector store, retrieval, visualization
  generation/     prompts, Claude client, RAG doc, baseline doc, A/B comparison, report filename + PDF rendering (WeasyPrint)
  db/              schema, connection (sqlite-vec), repository (all SQL lives here)
  api/             FastAPI routes + request/response schemas + the background ingest-job tracker (ingest_job.py)
  tests/           pytest suite + HTML fixtures
  models.py        shared data types (e.g. `IngestedPost`) used across layers
  main.py          FastAPI app + CORS setup - no longer serves the frontend itself (see "decoupled" note below)
  Dockerfile       backend container image (built from repo root as context)
frontend/          vanilla HTML/CSS/JS, no build step - a separate static server, not served by the backend
  Dockerfile       nginx container image, serves the static files only (no /api/ proxying - see Architecture)
docker-compose.yml two-service stack (backend + frontend), decoupled - see "Getting Started"
```
