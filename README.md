# Custom Stock Analysis

Standalone tiered stock analysis — the "tiered alt" page extracted from the
[daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) fork
into its own app on 2026-08-24.

One page, one job: enter a ticker (A-shares, HK, or US), pick quick or deep
analysis and a max hold time, and get a structured report — technicals,
fundamentals, news, macro, an AI debate, a trade plan with sizing — plus a
run history.

This is the self-host version: one person, one machine, no sign-in. The
model (`MAIN_LLM`) and its key (`LLM_API_KEY`) come from `.env`. A hosted, many-user version with
sign-in and per-user keys lives in the separate
[custom-stock-analysis-hosted](https://github.com/wenbo68/custom-stock-analysis-hosted)
repo (split 2026-09-18); engine and UI improvements flow between the two
by merging.

## Layout

- `server.py` / `api/` — FastAPI backend (the tiered API + static frontend)
- `src/tiered_analysis/` — the analysis engine
- `src/storage.py` — database (run history, transcripts, caches)
- `data_provider/` — multi-source daily price bars with automatic fallback
- `web/` — React frontend (builds into `static/`)
- `tests/` — offline test suite

## Quick start

```bash
# 1. Backend deps
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# 2. Configure (at minimum the LLM model + its provider key)
cp .env.example .env   # then edit

# 3. Frontend
cd web && npm install && npm run build && cd ..

# 4. Run
./start-server.sh                # rebuilds the frontend, then serves http://127.0.0.1:8000
```

Frontend development mode (hot reload, proxies /api to :8000):

```bash
cd web && npm run dev
```

## Run queue

At most `MAX_CONCURRENT_RUNS` analyses (default 4) run at once;
the rest wait in line and start by themselves, and a restart resumes
whatever was still waiting. An unfinished run with the same ticker and
inputs cannot be started twice — the Start popup names the existing one.
A restart marks any run still in flight as failed (runs are in-process
threads).

## Database

Everything durable — run history, LLM transcripts and the fetched-data
caches — lives in one database. By default that is a sqlite file at
`./data/stock_analysis.db`; set `DATABASE_URL` to a Postgres address to
use Postgres instead, with no other change.

## Structured LLM replies

Every AI call that must answer in JSON is protected twice (2026-08-25):
the provider is asked to *enforce* the reply shape while generating
(litellm `response_format` — full schema on models that support it,
plain guaranteed-JSON mode otherwise, silently skipped on models that
support neither), and the reply is *checked* against a pydantic form
with one retry that shows the model what was wrong. The report warns
when a retry was needed. The old fail-soft fallbacks (keep all
articles, no grouping, score order, feed abstracts) remain the last
line of defense.

## API

The frontend talks to a small JSON API under `/api/v1/tiered`; the
server documents it itself at `/docs` (interactive: fill in a form and
send a real request) and `/redoc` (read-only), from the schema at
`/openapi.json`. Every route declares its response shape, so the pages
show what comes back as well as what goes in.

| Route | What it does |
| --- | --- |
| `GET /status` | What the server can do right now: the configured model (never the key), which data sources are set, run slots and how many runs hold or wait for one, the run defaults, and each market's clock — whether a run would be refused now and when runs are accepted again. |
| `POST /analyze` | Start a run (ticker, depth 1 or 2, hold weeks, optional sizing). 409 when the market is open or the same run is already in flight. |
| `GET /runs` | One page of the history, newest first, filtered in the database (ticker, status, outlook, tier, hold, capital/risk/reward ranges, date range; `page`, `page_size`). |
| `GET /runs/tickers` | Every ticker ever run. |
| `GET /runs/{task_id}` | One run with its report — whole, or only the named `section`s (`core`, `dimensions`, `debate`, `plan`), optionally one `dimension`. Every answer carries `dimension_index`: one light row per data report. The `debate` section is an overview; its vote items are paged below. |
| `DELETE /runs/{task_id}` | Delete a run and its transcript. A queued run is thereby cancelled; a running one is refused (409) until it finishes. |
| `GET /runs/{task_id}/debate/items` | One page of a deep run's vote items, filtered by `dimension` and `status` (`counted`, `excluded`). |
| `GET /runs/{task_id}/transcript` | The run's LLM calls without their text (facts plus prompt/reply sizes). |
| `GET /runs/{task_id}/transcript/{seq}` | One LLM call with its full prompt and raw reply. |

## LLM transcripts

Every analysis run stores a transcript of its AI exchanges in the
database — one row per call, with the pipeline stage, model, full prompt,
raw reply, token counts, and the error when a call failed. When a report
shows a warning like "returned no usable JSON", open "View AI transcript"
under the report to see exactly what the model said. Rows older than 14
days are pruned at server startup.

## Fetched-data caches

The macro and world-news fetches and the per-article news judgments are
cached in the database (the `tiered_cache` table), so a restart does not
burn the vendors' daily call budgets. Every row can be refetched; rows
untouched for 60 days are pruned at startup.

## Tests

```bash
./.venv/bin/python -m pytest -m "not network"   # backend (offline)
cd web && npm run lint && npm test              # frontend
```
