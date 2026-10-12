# Backend fix prompts (review of 2026-10-10)

Paste the **header** first, then **one** prompt, into a fresh Claude session.
Each prompt is one bug. Prompts are independent and can run in any order,
except where a prompt says "after #N".

---

## Header (paste before every prompt)

```
Repo: /home/wenboliu68/developer/personal/custom-stock-analysis. Python 3.12
backend: server.py, api/, src/, data_provider/. Virtualenv at .venv. Run tests
with `.venv/bin/python -m pytest tests -q -m "not network"` (baseline: all
passing). Rules for this repo: write the failing test first, then the fix;
comments say why in plain words, like the existing code; any fallback, retry
or degraded result a user should know about appends a warning sentence to the
run's warnings list, never a silent patch; keep the app's own vocabulary (the
analysis page's words). Do not commit. Fix ONLY the bug below. If you notice
other bugs, list them at the end instead of fixing them. When done, run the
full test suite and `.venv/bin/python -m flake8` on the files you touched, and
report what you changed and what you verified. Line numbers below are
approximate.
```

---

## A. Loading order and startup

### A1. [DONE 2026-10-10] `.env` loads only by accident, and heavy libraries first load inside worker threads

Files: `api/app.py`, `src/config.py`, `server.py`.

Problem 1: `.env` is loaded as a side effect of importing `src.config`
(`load_dotenv()` at `src/config.py:27`). `server.py` imports it first on
purpose, but `api/app.py` never does, and `app = create_app()` reads
`CORS_ALLOW_ORIGINS` at import time (`app.py:50`). Starting the app any other
way (`uvicorn api.app:app`, tests using `TestClient(api.app.app)`) silently
drops `.env` settings.

Problem 2: `load_llm_client()` in `api/app.py` preloads only litellm. The
price-data stack is still first imported inside request and worker threads:
`src/tiered_analysis/run_gate.py:106,113,123,205` lazily import
`src.core.trading_calendar` (which pulls pandas, exchange_calendars and the
whole `data_provider` package) from `GET /status`, `POST /analyze` and every
chat turn; `src/tiered_analysis/integration.py:84` imports `data_provider.base`
in run threads; yfinance, akshare and efinance are imported inside provider
code. Startup's `run_queue.resume()` spawns threads immediately, so several
threads race on the same first import. This is the same shape as the litellm
import deadlock already fixed.

Problem 3: if litellm fails to import, `load_llm_client` logs a warning and
keeps serving, but litellm's logging hook stays attached, so the first model
call re-runs the import inside a worker thread, recreating the deadlock.
litellm is a required dependency, so a failed import should fail startup.

Fix: (1) `import src.config` (or `from src.config import get_config`) as the
first project import at the top of `api/app.py`, with a comment saying it
loads `.env` before anything reads the environment. (2) Replace
`load_llm_client` with `preload_libraries()` that imports, in order:
`litellm`, `src.core.trading_calendar`, `data_provider`, `yfinance`,
`akshare`, `efinance` (measured: about 7 s total, litellm 4 s of it). (3) A
failed import raises a clear RuntimeError naming the library. Update
`tests/test_app_startup.py` (it monkeypatches `import_module` and
`load_llm_client`; keep the "loaded before the first request" test).

### A2. [DONE 2026-10-10] One new DataFetcherManager per price load defeats the vendor rate limits

Files: `src/tiered_analysis/integration.py:84-86`, `data_provider/base.py`.

Problem: `bars_loader` builds a fresh `DataFetcherManager()` (five fetcher
instances) every call, and a run calls it 3 to 4 times (`technicals.py:781`,
`technicals.py:1668`, `fundamentals_us.py:751`, `cross_fields.py:171`).
Rate-limit state (`_last_request_time` in `akshare_fetcher.py:305`,
`efinance_fetcher.py:289`) is per fetcher instance and the "one call to a
vendor at a time" locks (`base.py:453,511-519`) are per manager, so 4
concurrent A-share runs become up to 16 independent clients hitting the same
vendor. Only the circuit breaker is shared.

Fix: one process-wide manager, created lazily under a lock (same pattern as
`cache_store.default_cache_store`), used by `bars_loader`. Check the manager
is safe to share across threads (it holds its own locks). Test: two
`bars_loader` calls get the same manager; a test can reset it.

### A3. [DONE 2026-10-10] Decision needed: `src` imports from `api` (layering inversion)

Files: `src/chat/tools.py:312,327,336,357` import `api.v1.endpoints.tiered`
for `run_queue`, `submit_run`, `RunRefused`, `effective_inputs`.

Problem: no import cycle today, but these live in an HTTP route module. One
`src.chat` import added to `tiered.py` would create a cycle that only fails at
request time. Not a bug yet; a design smell.

Fix, if the owner wants it: move `run_queue`, `submit_run`, `RunRefused` and
`effective_inputs` into `src/tiered_analysis/run_service.py` and import it at
top level from both `tiered.py` and `tools.py`. The request schema
`TieredAnalyzeRequest` lives in `api/v1/endpoints/tiered_schemas.py`; decide
whether it moves too. Run the chat and tiered API tests after.

---

## B. Chat harness and API

### B1. [DONE 2026-10-12] Hitting the tool-call limit leaves tool calls unanswered and breaks the conversation for good

File: `src/chat/harness.py` (`_loop`, around lines 193-209).

Problem: `_ask_model` stores the model's reply with its `tool_calls` before
the limit check. When `tool_calls >= TOOL_CALL_LIMIT`, the loop appends the
`tool_call_limit` notice and returns without storing a `tool` message for
those calls. `model_view` keeps `tool_calls`, so every later turn sends the
provider an assistant message whose tool calls were never answered, which
OpenAI-style providers reject with a 400. Every later message in that
conversation then fails. Reproduce with the existing test
`test_tool_call_limit_stops_a_looping_model` and then send one more message.

Fix: before appending the notice, store a tool result for each of the reply's
tool calls with `{"error": "tool_call_limit", "message": "the tool-call limit
for this turn was reached; this call was not run"}` via `_store_tool_result`.
Update the existing test (it asserts `count("tool") == TOOL_CALL_LIMIT`) and
add a test that a second `send` after the limit produces a request where every
tool call id has a matching tool message.

### B2. [DONE 2026-10-12] A long turn can push the user's own question out of the history window

File: `src/chat/harness.py` (`trim_history`, lines 112-118).

Problem: the window is the last `HISTORY_MESSAGE_LIMIT` (40) rows, then
advanced to the first `user` row. One turn can produce more than 40 rows
(8 tool-calling replies times several calls each), after which no `user` row
is inside the window and `kept` is empty: the model gets only the system
prompt. Reproduced with 8 replies of 5 tool calls each.

Fix: always keep the whole most recent turn (from the last `user` row to the
end), then add older turns while they fit in the limit, cutting at a user
boundary. Add a test with a 50-row single turn asserting the user line and all
its tool results are kept, and keep the existing `trim_history` tests passing.

### B3. [DONE 2026-10-12] Deleting a conversation during its turn gives a 500, and locks are never freed

Files: `api/v1/endpoints/chat.py:152-157`, `src/chat/harness.py:136,329-334`,
`src/chat/store.py:188-191,216-218`.

Problem: `delete_conversation` ignores the harness's per-conversation lock.
The in-flight turn's `store.append_message`/`set_pending` then raise a plain
`KeyError` (not `UnknownConversationError`), so `send_message` returns 500
`internal_error` and the paid model call is wasted. Also `_turn` checks
`conversation_exists` before taking the lock, so a delete in that gap has the
same effect. And `ChatHarness._locks` gains one lock per conversation ever
messaged and never drops one.

Fix: add `ChatHarness.delete_conversation(id)` that takes the conversation's
lock non-blocking (409 `busy` if a turn runs, via `ConversationBusyError`),
deletes through the store, and pops the lock entry. Move the existence check
inside the lock in `_Turn`. The DELETE route calls the harness. Tests: delete
while a turn is blocked on a scripted model returns 409; delete after it
returns 200 and the lock entry is gone; unknown id is still 404.

### B4. [DONE 2026-10-12] Answering a held action writes the result and the new pending state in two transactions

Files: `src/chat/harness.py` (`confirm`, lines 172-180), `src/chat/store.py`.

Problem: `_store_tool_result` commits, then `set_pending` rewrites the held
list. A crash between the two leaves the already-run call still pending; the
next `confirm` runs it again. For `start_run` that can start and pay for a
second run.

Fix: give `store.append_message` an optional `pending` argument (sentinel for
"unchanged") that sets `pending_json` in the same session and commit, and have
`confirm` store the result together with the remaining pending list (or None).
Test: after a confirm with two held calls, one DB session wrote both the tool
row and the shortened pending list.

### B5. [DONE 2026-10-12] The conversation list parses every stored transcript on every sidebar refresh

Files: `src/chat/store.py:46-98` (`_stats`, `list_conversations`),
`src/storage.py` (`ChatMessageRecord`), `api/app.py` (startup).

Problem: each assistant row stores the whole rendered prompt in
`content_json` (20 KB and growing with the conversation), and
`list_conversations` loads and JSON-parses every row of every conversation
just to count tokens. The page refreshes the list after every turn. A few
dozen conversations means tens of MB parsed per refresh.

Fix: add nullable `input_tokens` and `output_tokens` Integer columns to
`ChatMessageRecord`, filled by `append_message` from `message["usage"]` (0 when
there is none). Compute `message_count`, `user_input_count`, `ended_at`
(max user `created_at`) and `total_tokens` with one grouped SQL query. For
existing databases add a generic step in `DatabaseManager` after
`create_all` that compares each mapped table with the live table (SQLAlchemy
`inspect`) and runs `ALTER TABLE ... ADD COLUMN` for missing columns (works on
sqlite and Postgres). Backfill once at startup: assistant rows with NULL
tokens get their values parsed from `content_json`, 0 when absent. Tests:
stats match the old computation on a seeded DB; an old-shape sqlite file gains
the columns and is backfilled.

### B6. [DONE 2026-10-12] Timestamps handed to the model carry no timezone

Files: `src/chat/store.py:32-33` (`_iso`), `src/tiered_analysis/history.py:428-429,583`.

Problem: `created_at`/`updated_at` are naive UTC rendered without `Z` or
offset (`2026-10-10T12:00:00.123456`) although the schemas say "ISO 8601,
UTC". The web page compensates (`parseUtc` in
`web/src/components/analysis/format.ts` appends `Z` and already accepts a
`+` offset), but chat tool results go to the model as is, next to a system
prompt whose server time carries `+00:00` and market clocks carry local
offsets, so the model can misplace a run's time by the user's offset.

Fix: render naive values as UTC with an explicit offset
(`value.replace(tzinfo=timezone.utc).isoformat()`) in both helpers. Run the
chat, history and tiered API tests; fix any that assert the old string.

### B7. [DONE 2026-10-12] A run can stay `running` forever if its thread fails to start

File: `src/tiered_analysis/run_queue.py` (`dispatch`, lines 123-131).

Problem: `history.mark_running` and `_active.add` happen before
`Thread.start()`. If `start()` raises (`RuntimeError: can't start new
thread`), the row stays `running`, the id stays in `_active` (one slot lost
until restart), and `submit` reports `queued` while the row says `running`.

Fix: wrap `start()`; on failure `history.mark_failed(run_id, reason)` and
`_active.discard(run_id)`, log it, and continue the dispatch loop. Test:
monkeypatch `threading.Thread.start` to raise and assert the row is `failed`
and the slot is free.

### B8. [DONE 2026-10-12] Dead error middleware that would leak exception text

Files: `api/middlewares/error_handler.py:24-67`, `api/middlewares/__init__.py`.

Problem: `ErrorHandlerMiddleware` is never registered (`api/app.py` only calls
`add_error_handlers`). If someone wires it in, it returns `str(e)` to clients
whenever the logger is at DEBUG. The registered handlers are fine.

Fix: delete the class and its export; keep `add_error_handlers`. Run the API
tests.

---

## C. Analysis pipeline

### C1. [DONE 2026-10-12] A wrong-language retry that fails to parse throws away a valid reply

File: `src/tiered_analysis/llm_support.py:300-337` (`in_language`).

Problem: the first reply parses but is in the wrong language; the retry
returns `None` (unparseable); the loop returns `None`, so the stage reports
"produced no outlook" although a valid score existed. The same path can void
a lister sheet, a check or deciding round, or the summary. The docstring
promises "a stubborn model costs wording, never the run".

Fix: remember the last non-None result; when a retry returns None, return
that result with the existing "shown as written" warning. Test: scripted
`ask` returning a wrong-language reply then None keeps the first reply and
warns.

### C2. [DONE 2026-10-12] A news judgment with a non-integer materiality is cached as "unknown" forever

File: `src/tiered_analysis/news_screen.py:455-458,718-725`.

Problem: a model reply like `[[1, true, 3.0]]` (float) or `"3"` (string)
makes `materiality=None` but keeps `from_model=True`, so `judge_news_cached`
writes it to the cache. Every later run reads the hit, never re-judges, and
`None` passes the `select_events` threshold, so the article is always a card
candidate of unknown importance with no warning. `request_structured` returns
the raw parsed dict, so the float survives.

Fix: coerce whole floats and digit strings to int in `_clean_judgment`; if
materiality is still None, set `from_model=False` (or skip `cache.put`) so it
is re-judged next run, and keep the existing warning. Tests for both inputs.

### C3. [DONE 2026-10-12] One API error in one lister voids the whole deep analysis

File: `src/tiered_analysis/deep_analysis.py` (`_listers` ~1000-1040,
`_vote_round` ~1348-1369, `run` ~802).

Problem: a transport exception (timeout, 5xx) inside one lister's worker
propagates through `futures[i].result()` out of `_run_stages`; `run()` catches
it and returns "deep analysis LLM call failed" with `items=[]`. The documented
degrade paths (one sheet failing proceeds with the other; a failed deciding
round excludes the tied items) only cover invalid replies, not failed calls.
The other lister's completed, paid work is discarded.

Fix: in `run_stage`'s `job` and in `_vote_round`, catch `Exception` except
`LlmConfigError`, append a warning naming the stage and the error, and return
None so the existing degrade branches apply. Tests: one lister raising leaves
the other's items and a warning; a deciding-round failure excludes the tied
items with a warning.

### C4. [DONE 2026-10-12] A citation fix round drops the code-injected own-field link

File: `src/tiered_analysis/deep_analysis.py` (`_sheet_items` ~1047-1075,
`_fix_citations` ~1222-1280).

Problem: `_sheet_items` injects `own_link` (the graded field's exact display
value) so "the AI cannot misquote its own field". After a fix round the
candidate's `links` are whatever the model returned; the own link may be
dropped or repointed, and the item passes as long as its remaining links
verify. The stored vote item then names field X with no link to X.

Fix: pass the id-to-ref map (`ref_by_id` from `_sheet_items`) into
`_fix_citations`; after accepting a candidate, rebuild its links as
`[own_link, *links whose ref != field]` the same way `_sheet_items` does.
Test: a fix reply that omits the own link still yields an item whose first
link is the field with its display value.

### C5. [DONE 2026-10-12] An empty-string report value crashes the lister thread

File: `src/tiered_analysis/deep_analysis.py` (`_payload_value` ~296-330,
`gradable_field_refs` ~249-272), `deep_analysis_models.py:100-116`.

Problem: `_payload_value` treats `""` as a gradable leaf, but
`LinkModel(ref, value="")` raises `ValidationError` inside `_sheet_items`,
which runs in the lister thread, so the whole deep analysis fails.
`fundamentals_us.py:1276` passes any string through (an SEC entity name or
sector could be `""`). Also `value_pattern("")` matches anything.

Fix: treat empty or whitespace-only strings like `None` in `_payload_value`
(no row, like a blank field). Test: a payload with `"sector": ""` produces no
grade-sheet row and no crash.

### C6. [DONE 2026-10-12] Plan review: a rejected later proposal discards an earlier accepted one, and an unusable reply is reported as "no change helps"

File: `src/tiered_analysis/plan_review.py` (`_merge_proposals` ~860-882,
`review_plan` ~985-1090, `evaluate` ~918).

Problem 1: round 1 proposes stop=95 (accepted); round 2 proposes stop=90,
which `apply_adjustments` rejects (outside the ATR band). `_merge_proposals`
already replaced 95 with 90, so the plan reverts to the base stop, not 95. A
valid adjustment is lost with only a "rejected" warning.

Problem 2: when both the first reply and the fix reply are unparseable,
`_request_adjustments` returns `[]`, which `review_plan` treats as the AI
saying "no change helps". With a plan-dependent check firing, the warning
says "did not converge: the adjusted plan still tripped risk checks" although
no adjustment was ever applied.

Fix 1: when a later proposal for a level is rejected, keep the previous
accepted value for that level (validate before merging, or restore on
rejection), and word the warning accordingly. Fix 2: make
`_request_adjustments` distinguish "no usable reply" (return None) from "no
adjustments" and treat None as an outage with its own warning. Tests for
both.

### C7. [DONE 2026-10-12] The grader prompts show doubled braces in the JSON shape they ask the model to copy

File: `src/tiered_analysis/deep_analysis.py:414-455` (`_LINK_RULES`,
`_VOTE_RULES`).

Problem: these constants use `{{"ref": ...}}` escaping but are passed to
`str.format` as values, not as the template, so every grader, check, deciding
and fix prompt shows the model `{{"ref": …}}`. Cosmetic, but it is exactly the
shape the model is told to copy.

Fix: single braces in those two constants. Verify no template formats them
again (grep `.format(` uses). Add a test that a rendered lister prompt
contains `{"ref":` and not `{{"ref":`.

### C8. [DONE 2026-10-12] Failed model calls are missing from the run's usage counts

File: `src/tiered_analysis/llm_support.py:450-469` (`_summarize`).

Problem: a call that raises is written to the transcript but never reaches
`record_llm_usage`, so `llm_usage.<stage>.calls` undercounts and a stage with
only failures shows 0 calls.

Fix: call `record_llm_usage(None, None)` in the except branch (check
`LlmUsageTracker.record` counts a call with None tokens), or document that
`calls` means successful calls. Prefer counting. Test: a raising summarizer
adds one call with zero tokens.

### C9. [DONE 2026-10-12] "Today" for the earnings and macro gates is the server's clock, not the market's

Files: `src/tiered_analysis/earnings.py:150,161`,
`src/tiered_analysis/plan_review.py:291`.

Problem: `date.today()` is the server's local date while the as-of dates are
market dates. On a UTC host after 20:00 New York time, `days_until` is one day
short, so the 7-day earnings or macro-event gate can fire a day early or
late.

Fix: callers pass `today` computed from the market's local time
(`src/core/trading_calendar.get_market_now(market).date()`) instead of the
wall clock; keep the `today` parameter for tests. Test with a fixed clock
near midnight UTC.

---

## D. Data fetchers

### D1. [DONE 2026-10-12] Yahoo's end date is exclusive, so the newest US bar is never fetched on most servers

Files: `data_provider/yfinance_fetcher.py:179-186`, `data_provider/base.py:328`.

Problem: `_fetch_raw_data` passes `end=end_date`; yfinance documents `end`
as exclusive. `base.py` defaults `end_date` to the server's local
`datetime.now()` date. On a server in a US or European timezone, a run at
17:00 New York time asks for `end=today` and gets bars through yesterday, so
`is_lagging` fires for every US stock: with AlphaVantage set, every run pays a
top-up call (25 per day cap) and the S&P index is always one day stale;
without it, every after-close run fails the staleness gate. A UTC+8 machine
hides this because its "today" is already tomorrow.

Fix: in the yfinance fetcher only, request `end = end_date + 1 day`. Test:
the yfinance call receives the day after the requested end date.

### D2. [DONE 2026-10-12] A-share volume is in lots from two vendors and shares from the others

Files: `data_provider/efinance_fetcher.py` (`_normalize_data` ~510),
`data_provider/akshare_fetcher.py` (`_normalize_data` ~640),
`data_provider/tencent_fetcher.py:175-178`.

Problem: Efinance (priority 0) and akshare's Eastmoney channel return 成交量
in lots (手, 100 shares); Tencent's fetcher multiplies by 100; Yahoo, Sina and
akshare-Tencent return shares. Nothing converts in the Efinance or
akshare-Eastmoney normalizers. `technicals.py:1048` documents
`volume.avg_vol_60d` as mean daily share volume, and
`plan_review.py:214-232` divides planned shares by it, so the liquidity flag
is 100x too eager on days Efinance answers and silently right on days Tencent
answers. Confirm the unit first: efinance's own sample (600519 on 2001-08-27:
volume 406,318 against turnover 1.41e9 at about 34.7) implies lots; akshare's
`stock_zh_a_hist` docstring says 手. HK (`stock_hk_hist`) is already shares.

Fix: multiply by 100 for mainland codes in both normalizers so `volume` is
shares from every fetcher, with a comment naming the unit. Check tests and
fixtures that assert raw volumes and update them.

### D3. [DONE 2026-10-12] Prefixed or suffixed A-share spellings bypass the market-open and staleness gates

Files: `src/core/trading_calendar.py:51-74` (`get_market_for_stock`),
`data_provider/base.py:213` (`_market_tag`), `src/services/market_symbol_utils.py`.

Problem: `get_market_for_stock("600519.SH")` (also `SH600519`, `600519.SS`,
`sz000001`) returns None, while `_market_tag` routes the same strings to `cn`
and fetches fine. With None, `market_open_check` fails open,
`expected_bar_date` is None, `trim_incomplete_bars` keeps today's half-day
bar and `is_lagging` never fires: an intraday bar is analyzed as a daily one.

Fix: normalize the code first (`normalize_stock_code`, or reuse
`_market_tag` and map 6-digit results to `cn`) in `get_market_for_stock`.
Tests for each spelling.

### D4. [DONE 2026-10-12] EDGAR annual series can take a one-quarter row as the fiscal-year value

File: `src/tiered_analysis/providers/edgar_series.py:84-120`.

Problem: any 10-K row with `fp=FY` is kept keyed by `end`, with no check that
`start` to `end` spans a year. The module's own note (line 117) says some
filers tag the Q4 row in the 10-K with the same `end` date; whichever comes
later in the JSON wins. Then `gross_margin_pct` = FY gross profit / Q4
revenue, about 4x too high, with a correct-looking `period_end`.

Fix: for rows with a `start`, require a span between `YEAR_MIN_DAYS` and
`YEAR_MAX_DAYS` (define them, about 350 to 380); instant balance-sheet rows
have no `start` and stay. Test with an FY row and a Q4 row sharing `end`.

### D5. [DONE 2026-10-12] Relative strength compares the stock and the index over different dates

Files: `src/tiered_analysis/providers/technicals.py:678-686,1668-1674`,
`data_provider/base.py:854`.

Problem: `rs_1m` and the regime fields take the last N closes of the stock
and of the index independently with no date alignment. The stock can be
topped up by AlphaVantage while the index never is, and index staleness is
never checked. Stock bars ending Friday against index bars ending Thursday
gives a misaligned comparison and a regime that describes Thursday, with no
warning.

Fix: truncate both series to their common last date before `pct_change`, and
append a warning when the index's last date differs from the stock's. Test
with two frames one day apart.

### D6. [DONE 2026-10-12] A bare 5-digit Hong Kong code becomes a Shenzhen symbol in the Yahoo fallback

File: `data_provider/yfinance_fetcher.py:140-151` (`_convert_stock_code`).

Problem: `_convert_stock_code("00700")` returns `"00700.SZ"` (logged
"默认使用深市"). The manager routes `00700` as HK and keeps Yahoo as the HK
backup, so when akshare fails the fallback queries a non-existent symbol and
a fetchable stock fails loudly.

Fix: check the HK rule (5-digit numeric, see `_is_hk_market` in `base.py`)
before the Shanghai/Shenzhen prefix rules and emit Yahoo's `0700.HK` form
(4 digits plus `.HK`). Test `00700` and `hk00700`.

### D7. [DONE 2026-10-12] Implied report move can pick an options expiry that ends before the report

File: `src/tiered_analysis/providers/positioning.py:426`.

Problem: expirations strictly before the report date are skipped, so a
Friday after-close report with a Friday expiry selects a straddle that expires
before the jump.

Fix: require `expiration > earnings_date` (report timing is unknown, so the
later expiry is the safe pick) and say so in the field's explanation. Test
with an expiry on the report date.

### D8. [DONE 2026-10-12] Retry decorators that never fire, and a failure message with no reason

Files: `data_provider/yfinance_fetcher.py:153-158`,
`data_provider/akshare_fetcher.py:307-312`, `data_provider/base.py:767-786`.

Problem: the tenacity decorators retry only on `ConnectionError`/`TimeoutError`,
but the function bodies wrap every exception into `DataFetchError`, so the
retry never runs. And when every fetcher returns an empty frame, the final
error is "所有数据源获取失败:" with an empty reason list.

Fix: retry on a `DataFetchError` whose `__cause__` is a connection or timeout
error (`retry_if_exception` with a predicate), so legitimate "no data" is not
retried; append an "empty result" entry to `errors` in the manager. Tests for
both.

### D9. [DONE 2026-10-12] Cold-day caches are fetched once per concurrent run instead of once

Files: `src/tiered_analysis/providers/macro_economy.py:330-369`,
`src/tiered_analysis/providers/world_news.py:371-594` (pool write at 428-438),
`src/tiered_analysis/cache_store.py`.

Problem: the day cache is check-then-fetch with no lock across threads.
Several runs starting on a cold day each miss, each call FRED and each run the
LLM news screen; the world article pool is read-modify-written last-writer-wins.
Data stays correct; cost does not.

Fix: a process-level lock per provider around the miss path (check, fetch,
store) so the second run waits and then hits the cache. Test with two threads
and a counting fake fetcher: one fetch.

### D10. [DONE 2026-10-12] The ticker-to-CIK map is fetched once per process and never refreshed

File: `src/tiered_analysis/providers/fundamentals_us.py:427-450`.

Problem: `_cik_cache` is filled once; a ticker listed after startup raises
`LookupError` for the process lifetime (blank fundamentals with a warning).
Also the check-then-set has no lock, so two runs download the SEC file at once.

Fix: guard with a lock; on a miss, refetch at most once per hour (store the
fetch time); keep the warning when still missing. Test: a miss after a stale
fetch triggers one refetch.

---

## Not fixing (listed for the owner)

- litellm fetches its model price map over the network at import (now at
  startup, 5 s timeout offline). Setting `LITELLM_LOCAL_MODEL_COST_MAP=true`
  avoids it but freezes the list of known models to the installed copy. Left as
  is; the owner's call.
- `fundamentals_us.py:388-393` measures the earnings-day move from report-day
  close to next close, which understates it for before-open reporters. The code
  documents this as a two-session limitation. Left as is.
- A3 above is a refactor, not a bug.
