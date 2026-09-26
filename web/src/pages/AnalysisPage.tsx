import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import {
  tieredApi,
  type TieredTier,
  type TieredDuplicateRun,
  type TieredMarketOpenGate,
  type TieredResult,
  type TieredRunPage,
  type TieredRunRequest,
} from '../api/tiered';
import { RunForm } from '../components/analysis/RunForm';
import { RunHistory } from '../components/analysis/RunHistory';
import {
  NO_FILTERS,
  toListQuery,
  type HistoryFilters,
} from '../components/analysis/historyFilters';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { getLocalStorage, readStoredValue } from '../utils/storedValue';

const POLL_INTERVAL_MS = 5000;
const DEFAULT_TIER: TieredTier = 1;
// Suggestions when nothing was remembered — the user still sees and can
// remove/replace the pill before starting. They match the backend's own
// defaults for a run that sends nothing.
const DEFAULT_CAPITAL = '100000';
const DEFAULT_RISK_PCT = '1';
// Reward-to-risk ratio the plan aims for (owner decision, 2026-07-21):
// required like every other field, default 2. (There is no ownership
// input: held shares would belong to a future portfolio feature.)
const DEFAULT_REWARD_RATIO = '2';
// Max hold time in weeks (owner decision 2026-08-08): required, default
// 2 — feeds the AI prompts, the report and the forward-test window.
const DEFAULT_MAX_HOLD_WEEKS = '2';

// Shared with the main tiered page so the values carry across both skins.
const CAPITAL_STORAGE_KEY = 'run.capital';
const RISK_PCT_STORAGE_KEY = 'run.risk_pct';
const REWARD_RATIO_STORAGE_KEY = 'run.reward_ratio';
const MAX_HOLD_WEEKS_STORAGE_KEY = 'run.max_hold_weeks';
// The keys these were saved under before the 2026-09-24 rename (same
// units); a value still there is read once and moved (owner audit 2026-09-25).
const LEGACY_STORAGE_KEYS: Record<string, string> = {
  [CAPITAL_STORAGE_KEY]: 'tiered.sizing.capital',
  [RISK_PCT_STORAGE_KEY]: 'tiered.sizing.riskPct',
  [REWARD_RATIO_STORAGE_KEY]: 'tiered.sizing.reward',
  [MAX_HOLD_WEEKS_STORAGE_KEY]: 'tiered.holdWeeks',
};

const EMPTY_PAGE: TieredRunPage = { items: [], page: 1, page_size: 10, total: 0, page_count: 1 };

// The gate payload when the backend rejected the start because the
// ticker's market is inside the trading day (409 with the market_open
// code); null for every other error.
function marketOpenRejection(error: unknown): TieredMarketOpenGate | null {
  if (!axios.isAxiosError(error) || error.response?.status !== 409) {
    return null;
  }
  const detail = (
    error.response.data as {
      detail?: { code?: string; market?: string; session_open?: string; session_close?: string };
    } | undefined
  )?.detail;
  if (detail?.code !== 'market_open') {
    return null;
  }
  return {
    market: detail.market ?? null,
    sessionOpen: detail.session_open ?? null,
    sessionClose: detail.session_close ?? null,
  };
}

// The duplicate payload when the backend refused the start because an
// unfinished run has the same ticker and inputs (409 with the
// duplicate_run code); null for every other error.
function duplicateRejection(error: unknown): TieredDuplicateRun | null {
  if (!axios.isAxiosError(error) || error.response?.status !== 409) {
    return null;
  }
  const detail = (
    error.response.data as {
      detail?: { code?: string; run_id?: string; status?: string };
    } | undefined
  )?.detail;
  if (detail?.code !== 'duplicate_run' || !detail.run_id) {
    return null;
  }
  return {
    runId: detail.run_id,
    status: detail.status === 'running' ? 'running' : 'queued',
  };
}

// Whether the backend refused a delete because the run is executing
// (409 with the run_in_progress code).
function runInProgressRejection(error: unknown): boolean {
  if (!axios.isAxiosError(error) || error.response?.status !== 409) {
    return false;
  }
  const detail = (error.response.data as { detail?: { code?: string } } | undefined)?.detail;
  return detail?.code === 'run_in_progress';
}

function readStoredNumber(key: string): string | null {
  return readStoredValue(getLocalStorage(), key, LEGACY_STORAGE_KEYS[key]);
}

function storeNumber(key: string, value: string | null): void {
  try {
    if (value) {
      window.localStorage.setItem(key, value);
    } else {
      window.localStorage.removeItem(key);
    }
  } catch {
    // storage unavailable (private mode) — the run still works
  }
}

// Alternate skin for tiered analysis, styled after showplayer.net. Two
// section cards with their titles sitting above: the new-run form
// (write-only fields + pills + Start) and the run history (filters +
// paged rows that expand into the full report). The history is one
// server page at a time (2026-09-21): this page owns the filters and the
// page number, and every change re-asks the server.
const AnalysisPage = () => {
  // The language also rides on every run: the report's model-written
  // sentences are in the language the user chose for the app.
  const { t, language } = useUiLanguage();
  const [ticker, setTicker] = useState<string | null>(null);
  const [tier, setTier] = useState<TieredTier | null>(DEFAULT_TIER);
  // Capital is in the ticker's own currency, so it stays empty until a
  // ticker is picked; capitalDefault is what it then auto-fills with.
  const [capital, setCapital] = useState<string | null>(null);
  const [capitalDefault, setCapitalDefault] = useState<string>(
    () => readStoredNumber(CAPITAL_STORAGE_KEY) ?? DEFAULT_CAPITAL,
  );
  const [riskPct, setRiskPct] = useState<string | null>(
    () => readStoredNumber(RISK_PCT_STORAGE_KEY) ?? DEFAULT_RISK_PCT,
  );
  const [rewardRatio, setRewardRatio] = useState<string | null>(
    () => readStoredNumber(REWARD_RATIO_STORAGE_KEY) ?? DEFAULT_REWARD_RATIO,
  );
  const [maxHoldWeeks, setMaxHoldWeeks] = useState<string | null>(
    () => readStoredNumber(MAX_HOLD_WEEKS_STORAGE_KEY) ?? DEFAULT_MAX_HOLD_WEEKS,
  );
  // Clock-gate popup: the 409 market_open payload while it's showing.
  const [gate, setGate] = useState<TieredMarketOpenGate | null>(null);
  // Duplicate-run popup: the 409 duplicate_run payload while it's showing.
  const [duplicate, setDuplicate] = useState<TieredDuplicateRun | null>(null);
  const [filters, setFilters] = useState<HistoryFilters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [runPage, setRunPage] = useState<TieredRunPage>(EMPTY_PAGE);
  const [tickers, setTickers] = useState<string[]>([]);
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, TieredResult>>({});
  const [detailError, setDetailError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [deletingTaskId, setDeletingTaskId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const loadingDetailRef = useRef<string | null>(null);
  // A poll and a filter change can be in flight together; only the
  // latest request may write the list, whatever order they return in.
  const listRequestRef = useRef(0);

  const runs = runPage.items;

  // Poll while anything on the page is still in flight — queued runs
  // start by themselves, so a queued row needs the same polling as a
  // running one.
  const anyRunning = useMemo(
    () => runs.some((run) => run.status === 'running' || run.status === 'queued'),
    [runs],
  );

  const refreshRuns = useCallback(async () => {
    const request = ++listRequestRef.current;
    try {
      const fetched = await tieredApi.listRuns(toListQuery(filters, page));
      if (request === listRequestRef.current) {
        setRunPage(fetched);
      }
    } catch {
      // transient — next poll retries
    }
  }, [filters, page]);

  const refreshTickers = useCallback(async () => {
    try {
      setTickers(await tieredApi.listTickers());
    } catch {
      // the dropdown just stays as it was
    }
  }, []);

  useEffect(() => {
    void refreshRuns();
  }, [refreshRuns]);

  useEffect(() => {
    void refreshTickers();
  }, [refreshTickers]);

  useEffect(() => {
    if (!anyRunning) {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshRuns();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [anyRunning, refreshRuns]);

  // A page past the end (the last row of a page was filtered away, or
  // the server has fewer pages than before) falls back to the last one.
  useEffect(() => {
    if (page > runPage.page_count) {
      setPage(runPage.page_count);
    }
  }, [page, runPage.page_count]);

  const handleFilters = useCallback((patch: Partial<HistoryFilters>) => {
    setFilters((prev) => ({ ...prev, ...patch }));
    setPage(1);
  }, []);

  const expandedRun = useMemo(
    () => runs.find((run) => run.run_id === expandedTaskId) ?? null,
    [runs, expandedTaskId],
  );

  // Fetch the full report the first time a finished run is expanded (a run
  // started as Running loads here too, the moment polling flips it to done).
  useEffect(() => {
    const runId = expandedTaskId;
    if (!runId || expandedRun?.status !== 'done' || details[runId]) {
      return;
    }
    if (loadingDetailRef.current === runId) {
      return;
    }
    loadingDetailRef.current = runId;
    void (async () => {
      try {
        const run = await tieredApi.getRun(runId);
        const result = run.result;
        if (result) {
          setDetails((prev) => ({ ...prev, [runId]: result }));
          setDetailError(null);
        } else {
          setDetailError(run.error || t('tiered.error.title'));
        }
      } catch (error) {
        setDetailError(error instanceof Error ? error.message : String(error));
      } finally {
        loadingDetailRef.current = null;
      }
    })();
  }, [expandedTaskId, expandedRun?.status, details, t]);

  const handleToggle = useCallback((runId: string) => {
    setDetailError(null);
    setDeleteError(null);
    setExpandedTaskId((prev) => (prev === runId ? null : runId));
  }, []);

  // Remove a run (a queued one is thereby cancelled), then re-ask the
  // server for the page and the tickers so the row and, if it was the
  // last of its ticker, the dropdown entry go together.
  const handleDelete = useCallback(
    async (runId: string) => {
      setDeleteError(null);
      setDeletingTaskId(runId);
      try {
        await tieredApi.deleteRun(runId);
        setExpandedTaskId((prev) => (prev === runId ? null : prev));
        setDetails((prev) =>
          Object.fromEntries(Object.entries(prev).filter(([id]) => id !== runId)),
        );
        await Promise.all([refreshRuns(), refreshTickers()]);
      } catch (error) {
        setDeleteError(
          runInProgressRejection(error)
            ? t('tiered.history.deleteInProgress')
            : t('tiered.history.deleteError', {
                error: error instanceof Error ? error.message : String(error),
              }),
        );
      } finally {
        setDeletingTaskId(null);
      }
    },
    [refreshRuns, refreshTickers, t],
  );

  // Capital follows the ticker: picking a ticker auto-fills capital with
  // the remembered/default amount; removing the ticker removes capital too
  // (the amount's currency belongs to that ticker's market).
  const handleTicker = useCallback(
    (value: string | null) => {
      setTicker(value);
      if (value === null) {
        setCapital(null);
      } else {
        setCapital((prev) => prev ?? capitalDefault);
      }
    },
    [capitalDefault],
  );

  const handleStart = useCallback(
    async (runAnyway = false) => {
      // The form popup enforces every field; this is the last-line guard.
      if (!ticker || tier === null || !capital || !riskPct || !rewardRatio || !maxHoldWeeks || submitting) {
        return;
      }
      setSubmitError(null);
      setGate(null);
      setDuplicate(null);
      setSubmitting(true);
      try {
        // The request carries the form's fields as typed (risk as a
        // percent); a value outside its range is left out and the server
        // fills its default.
        const capitalValue = Number(capital);
        const pctValue = Number(riskPct);
        const rewardValue = Number(rewardRatio);
        const holdValue = Number(maxHoldWeeks);
        const request: TieredRunRequest = {
          ticker,
          ...(capital && Number.isFinite(capitalValue) && capitalValue > 0
            ? { capital: capitalValue }
            : {}),
          ...(riskPct && Number.isFinite(pctValue) && pctValue > 0 && pctValue < 100
            ? { risk_pct: pctValue }
            : {}),
          ...(rewardRatio && Number.isFinite(rewardValue) && rewardValue > 1 && rewardValue <= 10
            ? { reward_ratio: rewardValue }
            : {}),
          ...(Number.isInteger(holdValue) && holdValue >= 1 && holdValue <= 4
            ? { max_hold_weeks: holdValue }
            : {}),
          tier: tier ?? DEFAULT_TIER,
          language,
          ...(runAnyway ? { run_anyway: true } : {}),
        };
        const started = await tieredApi.start(request);
        storeNumber(CAPITAL_STORAGE_KEY, capital);
        storeNumber(RISK_PCT_STORAGE_KEY, riskPct);
        storeNumber(REWARD_RATIO_STORAGE_KEY, rewardRatio);
        storeNumber(MAX_HOLD_WEEKS_STORAGE_KEY, maxHoldWeeks);
        setCapitalDefault(capital);
        setTicker(null);
        setCapital(null);
        // The new run is newest, so it heads page 1 of the history (as
        // long as the filters admit it); show it there, expanded, until
        // polling flips it to done.
        setPage(1);
        await Promise.all([refreshRuns(), refreshTickers()]);
        setDetailError(null);
        setExpandedTaskId(started.run_id);
      } catch (error) {
        const rejection = marketOpenRejection(error);
        const duplicated = duplicateRejection(error);
        if (rejection) {
          // Clock gate: not an error — a choice. The popup offers
          // "run anyway" (analyze the previous completed session).
          setGate(rejection);
        } else if (duplicated) {
          // Same run already waiting or running: the Start popup says
          // so and the history shows that run.
          setDuplicate(duplicated);
          await refreshRuns();
          setDetailError(null);
          setExpandedTaskId(duplicated.runId);
        } else {
          setSubmitError(error instanceof Error ? error.message : String(error));
        }
      } finally {
        setSubmitting(false);
      }
    },
    [ticker, submitting, tier, capital, riskPct, rewardRatio, maxHoldWeeks, language, refreshRuns, refreshTickers],
  );

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 pb-8 pt-4 md:px-6 lg:px-8">
      <section className="flex flex-col gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-4">
          {t('tiered.form.title')}
        </h2>
        <div className="rounded bg-surface-1 p-4 text-ink-3 sm:p-6">
          <RunForm
            ticker={ticker}
            tier={tier}
            capital={capital}
            riskPct={riskPct}
            rewardRatio={rewardRatio}
            maxHoldWeeks={maxHoldWeeks}
            submitting={submitting}
            error={submitError}
            gate={gate}
            duplicate={duplicate}
            onTicker={handleTicker}
            onTier={setTier}
            onCapital={setCapital}
            onRiskPct={setRiskPct}
            onRewardRatio={setRewardRatio}
            onMaxHoldWeeks={setMaxHoldWeeks}
            onStart={() => void handleStart()}
            onRunAnyway={() => void handleStart(true)}
            onGateClose={() => setGate(null)}
            onDuplicateClose={() => setDuplicate(null)}
          />
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-4">
          {t('tiered.history.title')}
        </h2>
        <div className="rounded bg-surface-1 p-4 text-ink-3 sm:p-6">
          <RunHistory
            runs={runs}
            tickers={tickers}
            filters={filters}
            onFilters={handleFilters}
            page={runPage.page}
            pageCount={runPage.page_count}
            onPage={setPage}
            expandedTaskId={expandedTaskId}
            expandedResult={expandedTaskId ? (details[expandedTaskId] ?? null) : null}
            expandedError={detailError}
            onToggle={handleToggle}
            onDelete={(runId) => void handleDelete(runId)}
            deletingTaskId={deletingTaskId}
            deleteError={deleteError}
          />
        </div>
      </section>
    </main>
  );
};

export default AnalysisPage;
