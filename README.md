# Community Voices — Beekeeping & Apiculture Forum

A small web app that generates a **Community Voices Document** for the
beekeeping community on [beekeepingforum.co.uk](https://beekeepingforum.co.uk/):
what it's talked about in the past week (or day/month/year - see
[Getting Started](#getting-started)), and a prediction of what it'll talk
about next, generated with a RAG (retrieval-augmented generation) pipeline
over that forum's own recent posts.

Originally built against [Beemaster's Forum](https://beemaster.com/forum/index.php)
(SMF-based); that forum has since put up a Cloudflare bot challenge that
blocks every non-browser client, so the live deployment moved to
beekeepingforum.co.uk (XenForo-based) instead - see
[Choosing a forum](#choosing-a-forum). Both platforms are still supported
via the pluggable `ForumAdapter` interface.

Built for the Transcendent Endeavors "Community Voices" coding challenge.

## Overview

**What it does:** produces a plain-language weekly digest of what an
online community has been discussing, plus a prediction of what it'll
discuss next - grounded in that community's own recent posts via
retrieval-augmented generation (RAG), and shown side by side against what
a plain LLM produces with *no* retrieval at all (the spec's A/B
comparison).

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
   stats, through a FastAPI JSON API and a small vanilla-JS frontend - and
   download the generated document as a file named after whichever
   community was analyzed.

Nothing here is hardcoded to one specific forum - see
[Pointing this at a different forum](#pointing-this-at-a-different-forum).

## Choosing a forum

The challenge asks for a community with frequent activity throughout any
given week. Beemaster's Forum was the original choice, picked after
checking several candidates by hand: it was freely crawlable (no login
wall, permissive `robots.txt`) and its recent-posts feed showed 8+
distinct posts in a single day at the time - comfortably active enough
for a week-over-week digest.

Reddit's r/beekeeping was the first choice, but as of 2026 Reddit's Data API
requires explicit pre-approval under its Responsible Builder Policy for
*any* app, including small read-only hobby scripts — with no published SLA
(reports of 8+ week waits, denials with no reason given). That's incompatible
with a short take-home project, so it was dropped in favor of a source with
no approval gate.

**Beemaster's Forum later put up a Cloudflare bot challenge** that returns
a "Just a moment..." JS-challenge page to every non-browser client -
confirmed from three independent network paths, so it's not an IP-
reputation issue that switching networks would fix. Circumventing an
active anti-bot challenge wasn't something to build around, so the live
deployment moved to [beekeepingforum.co.uk](https://beekeepingforum.co.uk/)
instead: a genuinely active beekeeping community (real posts spread
across every hour of the day at the time of writing), reachable with a
plain HTTP client, and with a robots.txt that explicitly permits crawling
(`Crawl-delay: 5`, respected via `CRAWL_REQUEST_DELAY_SECONDS`) - it even
carries a dedicated, explicit allowance for AI-related crawlers
(throttled rather than blocked), unlike some other candidates checked
along the way that disallow them outright. It runs XenForo rather than
SMF, which is what motivated adding a second `ForumAdapter` (see
[Pointing this at a different forum](#pointing-this-at-a-different-forum))
instead of only ever supporting one platform.

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
FastAPI JSON API  ->  interactive frontend (vanilla JS, no build step)
   - document view (RAG vs. baseline, side by side)
   - embedding scatter plot (PCA-flattened, spec item 3b)
   - most-retrieved-chunk stats (spec item 3c)
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

### Pointing this at a different forum

The crawler talks to forums through a `ForumAdapter` interface
(`crawler/forum_adapter.py`) instead of assuming any one platform's
conventions directly - `ingest.py`'s orchestration only ever calls the
adapter, including for *discovering* recent activity, never a specific
platform's URLs/HTML/timestamps/discovery mechanics itself.

That last part matters: SMF exposes one global "recent activity" feed,
paginated newest-first, where one too-old entry means everything after it
is too old too. XenForo has no such feed a crawler is allowed to use (its
equivalent, `/whats-new/`, is `Disallow`ed by robots.txt on real
installs) - discovery instead means paging each board's own listing
independently, and XenForo always pins "sticky" threads to the top
regardless of their own age, so an old sticky must never be mistaken for
a stop signal. Rather than force every platform through one shared
pagination loop (breaking XenForo, or smuggling SMF assumptions into
"platform-agnostic" code), each adapter owns its whole
`discover_recent_topics()` method - see `forum_adapter.py`'s module
docstring for the full reasoning.

- **Another SMF-based or XenForo-based forum:** just change
  `FORUM_BASE_URL` (and `FORUM_EXCLUDED_BOARDS`) in `.env` - no code
  changes needed.
- **A forum running different software** (phpBB, Discourse, vBulletin,
  ...): write a new class implementing `ForumAdapter`, register it in
  `crawler/adapter_registry.py` under a new name, then point
  `FORUM_ADAPTER` at that name. `smf_adapter.py` and `xenforo_adapter.py`
  (each wrapping their own `*_parser.py`) are complete reference
  implementations, deliberately different in shape from each other, to
  model a new one on. No other module needs to change.

## Getting Started

Start here either way - Docker needs nothing but Docker itself; running
it directly needs Python 3.11+.

```bash
git clone git@github.com:ashrosejoyce/transcendentcodechallenge.git
cd transcendentcodechallenge

cp .env.example .env
# then edit .env and set your own ANTHROPIC_API_KEY
# (get one at https://platform.claude.com/settings/keys — see note below)
# every other setting in .env.example is optional; defaults work out of
# the box for exploring the app against beekeepingforum.co.uk.
```

> **On the API key:** the app reads `ANTHROPIC_API_KEY` from your environment
> (via `.env`, which is git-ignored). Reviewers should use their **own** key —
> never a key shared over chat/email — by generating one at
> platform.claude.com and dropping it into their local `.env`. The app will
> not run generation without it, but ingestion/embedding/retrieval/the
> visualization all work with no key at all.

### Option A: Docker (recommended)

No local Python install needed - everything, including the embedding
model, is baked into the image at build time.

```bash
docker compose up --build
```

Then open **http://localhost:8080**. Two containers, matching the app's
actual architecture (see `docker-compose.yml`):

| Service | What it is | Port |
|---|---|---|
| `frontend` | nginx serving the static UI, reverse-proxying `/api/` to `backend` | http://localhost:8080 |
| `backend` | FastAPI + crawler/RAG/generation pipeline + embedded SQLite (sqlite-vec) | http://localhost:8000 (direct, for debugging) |

No separate database container: SQLite is an in-process file store, not a
service of its own, and is persisted across restarts via the `db-data`
named volume instead. The backend's Dockerfile also installs the CPU-only
PyTorch build explicitly (`sentence-transformers`'s default resolution
otherwise pulls several GB of unused CUDA libraries into an image that
never has a GPU).

To stop: `docker compose down` (add `-v` to also drop the persisted
database volume).

### Option B: Run locally with Python

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

uvicorn app.main:app --reload --app-dir backend
```

Then open **http://localhost:8000**.

### Using it

Either way, once it's running:

1. Click **"Refresh data from forum"** first — this crawls the forum,
   chunks and embeds the results, and populates the vector store. (Takes
   a minute or two the first time under Option B, mostly spent
   downloading the local embedding model on its very first run - Docker
   bakes the model in at build time, so this is fast there.)
2. Pick a **timeframe** (day/week/month/year - defaults to week) and click
   **"Generate"** — this runs the RAG pipeline and the no-retrieval
   baseline side by side over that window of posts, predicting the same
   length of time ahead, and logs the retrieval stats / updates the
   embedding scatter plot. See `generation/timeframe.py`.
3. Click **"Download report"** to save the generated document as a local
   file, named after whichever community was analyzed (see
   `generation/report_filename.py`).

## Running the tests

```bash
pytest
```

93 tests across 15 files:

| File | Covers |
|---|---|
| `test_parser.py` | HTML parsing against representative SMF-structure fixtures |
| `test_xenforo_parser.py` | HTML parsing against representative XenForo-structure fixtures, incl. sticky-thread flagging and quote/signature stripping |
| `test_ingest.py` | platform-agnostic fetch-phase orchestration (max-posts cap, per-post windowing, topic-fetch errors), against a fake HTTP client - no real network calls |
| `test_smf_adapter.py` | SMF's discovery mechanics: single global feed, paginated newest-first, stopping on the first too-old entry |
| `test_xenforo_adapter.py` | XenForo's discovery mechanics: per-board pagination, board exclusion skipping a fetch entirely, and sticky threads never triggering a false stop |
| `test_forum_adapter.py` | the `ForumAdapter` registry, and that crawl orchestration works with a fake adapter whose discovery mechanics resemble neither shipped platform |
| `test_chunking.py` | paragraph packing, overlap, edge cases (empty text, oversized paragraphs) |
| `test_timeframe.py` | day/week/month/year preset resolution, cutoff math, and unknown-label rejection |
| `test_prompts.py` | RAG vs. baseline prompt construction never leaks retrieved content into the baseline, and reflects the chosen timeframe |
| `test_report_filename.py` | report-filename slugification, parameterized per community and (optionally) timeframe |
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

**The spec's optional `/insights` step:** this was built in Cowork (an
Anthropic product for delegating file/task work), not the Claude Code CLI,
so there's no `/insights` command available in this environment to run and
share output from. Noting that explicitly rather than fabricating output
for a command that wasn't actually run.

## Project structure

```
backend/app/
  crawler/       HTTP client, ingestion orchestration, pluggable ForumAdapter (forum_adapter.py, adapter_registry.py); parser.py + smf_adapter.py (SMF) and xenforo_parser.py + xenforo_adapter.py (XenForo) are the two shipped implementations
  rag/            chunking, embeddings, vector store, retrieval, visualization
  generation/     prompts, Claude client, RAG doc, baseline doc, A/B comparison, report filename
  db/              schema, connection (sqlite-vec), repository (all SQL lives here)
  api/             FastAPI routes + request/response schemas
  tests/           pytest suite + HTML fixtures
  models.py        shared data types (e.g. `IngestedPost`) used across layers
  main.py          FastAPI app, serves the frontend as static files
  Dockerfile       backend container image (built from repo root as context)
frontend/          vanilla HTML/CSS/JS, no build step
  Dockerfile       nginx container image, serves the static files
  nginx.conf       reverse-proxies /api/ to the backend container
docker-compose.yml two-service stack (backend + frontend) - see "Getting Started"
```
