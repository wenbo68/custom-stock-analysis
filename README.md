# Custom Stock Analysis

Standalone tiered stock analysis — the "tiered alt" page extracted from the
[daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) fork
into its own app on 2026-08-24.

One page, one job: enter a ticker (A-shares, HK, or US), pick quick or deep
analysis and a max hold time, and get a structured report — technicals,
fundamentals, news, macro, an AI debate, a trade plan with sizing — plus a
run history.

This is the self-host version: one person, one machine, no sign-in. The
model and its API key come from `.env`. A hosted, many-user version with
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

At most `TIERED_MAX_CONCURRENT_RUNS` analyses (default 4) run at once;
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
