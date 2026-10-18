import { useState } from 'react';
import { Square, Trash2 } from 'lucide-react';
import type { TieredResult, TieredRunSummary } from '../../api/tiered';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import { cn } from '../../utils/cn';
import { formatDateTime, isFromPreviousDay, parseUtc, plainNumber, queuePosition, rowKeyDown } from './format';
import { ALT_COLOR, OUTLOOK_TEXT } from './styles';
import { PageSelector, PairField, Pill, PillRow, Select } from './Fields';
import { Report } from './Report';
import { Modal, MODAL_BODY } from './Ui';
import { hasAnyFilter, isValidDay, toggled, type HistoryFilters } from './historyFilters';

// Status (where the run is: queued, running, done, failed) and outlook
// (what the finished analysis says) are separate columns (owner request
// 2026-09-17). Only a real opinion counts as an outlook: a run with none
// (unfinished, failed, or the judge produced nothing) shows a dash —
// and the outlook filter offers that dash too (owner request 2026-09-18).
const FILTER_STATUSES = ['queued', 'running', 'succeeded', 'failed', 'stopped'] as const;
const OUTLOOK_WORDS = ['bullish', 'neutral', 'bearish'] as const;
// The server's name for "rows with no opinion" in the outlook filter.
const NO_OUTLOOK = 'no_outlook';
const FILTER_OUTLOOKS = [...OUTLOOK_WORDS, NO_OUTLOOK] as const;
const FILTER_TIERS = ['1', '2'] as const;
// Max hold choices in weeks — same values the run form offers.
const FILTER_HOLDS = ['1', '2', '3', '4'] as const;

// The filters share the run form's 6-per-row grid (owner request
// 2026-08-09): ticker, capital, risk, rewardRatio, max hold and tier on the
// first line; status, outlook and date on the second (shares dropped,
// owner request 2026-08-16).
const FILTER_GRID =
  'grid w-full grid-cols-2 gap-2 text-sm sm:grid-cols-6 sm:gap-3 md:gap-4';
// The column-name header and every run row share this template, so each
// value sits under its column name. The last, narrow column is the
// trash button (owner request 2026-09-23).
const ROW_GRID =
  'grid w-full grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3 lg:grid-cols-4 lg:gap-4 xl:grid-cols-[repeat(9,minmax(0,1fr))_auto]';

// Filter colors follow the shared palette in field order; a range's Min
// and Max share one color (ALT_COLOR).
const TONE = {
  ticker: ALT_COLOR[1],
  capital: ALT_COLOR[2],
  risk: ALT_COLOR[3],
  rewardRatio: ALT_COLOR[4],
  maxHoldWeeks: ALT_COLOR[5],
  tier: ALT_COLOR[6],
  status: ALT_COLOR[7],
  outlook: ALT_COLOR[8],
  date: ALT_COLOR[9],
};

// The run list's column names, in row order.
const HEADER_KEYS = [
  'tiered.history.h.ticker',
  'tiered.history.h.capital',
  'tiered.history.h.risk',
  'tiered.history.h.reward',
  'tiered.history.h.hold',
  'tiered.history.h.tier',
  'tiered.history.h.status',
  'tiered.history.h.outlook',
  'tiered.history.h.date',
] as const;

const isPositiveNumber = (raw: string): boolean => {
  const value = Number(raw);
  return Number.isFinite(value) && value > 0;
};

const isRiskPct = (raw: string): boolean => {
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 && value < 100;
};

function runTime(run: TieredRunSummary): Date | null {
  return parseUtc(run.created_at);
}

// yyyy/mm/dd, hh:mm in the viewer's local time (altFormat.formatDateTime).
function formatTime(run: TieredRunSummary): string {
  return formatDateTime(run.created_at);
}

// The run's risk input as the percent the user typed ('1%'), or a dash.
function riskCell(run: TieredRunSummary): string {
  return run.risk_pct == null ? '—' : `${plainNumber(run.risk_pct)}%`;
}

// The run's reward-to-risk goal as the multiple the user typed ('2×').
function rewardCell(run: TieredRunSummary): string {
  return run.reward_ratio == null ? '—' : `${plainNumber(run.reward_ratio)}×`;
}

// The row's outlook (null until the run is done).
function runOutlook(run: TieredRunSummary): string {
  return run.outlook ?? 'no_outlook';
}

// Whether the row has an outlook worth a word (see OUTLOOK_WORDS).
function hasOutlook(run: TieredRunSummary): boolean {
  return run.status === 'succeeded' && (OUTLOOK_WORDS as readonly string[]).includes(runOutlook(run));
}

// The outlook filter's option text: the outlook word, or the dash.
function outlookOptionLabel(value: string, t: (key: UiTextKey) => string): string {
  return value === NO_OUTLOOK ? '—' : t(`tiered.outlook.${value}` as UiTextKey);
}

// The history row's date color (owner request 2026-09-18): green when
// the finished report is good to use, amber when it is from a previous
// trading day (clicking it says so), gray while there is no report.
function dateTone(run: TieredRunSummary): 'fresh' | 'stale' | 'none' {
  if (run.status !== 'succeeded') {
    return 'none';
  }
  const time = runTime(run);
  return time && isFromPreviousDay(time) ? 'stale' : 'fresh';
}

export interface RunHistoryProps {
  /** The current page's rows, as the server filtered and ordered them. */
  runs: TieredRunSummary[];
  /** Every ticker ever run, for the ticker filter's dropdown. */
  tickers: string[];
  filters: HistoryFilters;
  onFilters: (patch: Partial<HistoryFilters>) => void;
  page: number;
  pageCount: number;
  onPage: (page: number) => void;
  expandedTaskId: string | null;
  expandedResult: TieredResult | null;
  expandedError: string | null;
  onToggle: (runId: string) => void;
  /** Remove the run (a queued one is thereby cancelled); the page asks the server. */
  onDelete: (runId: string) => void;
  /** The run whose removal is in flight, if any. */
  deletingTaskId: string | null;
  /** Why the last removal failed, shown under the expanded row. */
  deleteError: string | null;
  /** Stop the running run part-way; the page asks the server (2026-10-19). */
  onStop: (runId: string) => void;
  /** The runs whose stop was asked for and not yet confirmed by the
   *  server — their row stays "running" until the step in flight ends. */
  stoppingTaskIds: string[];
  /** Why the last stop was refused, shown under that row. */
  stopError: string | null;
}

// Whether the row offers removal: a running run offers a stop instead
// (2026-10-19); once stopped it is history and offers the trash.
const isRemovable = (run: TieredRunSummary): boolean => run.status !== 'running';

// The same spot and look as the trash, so the two never both show.
const ROW_BUTTON =
  'cursor-pointer justify-self-end rounded p-1 text-ink-5 hover:text-negative disabled:cursor-default disabled:opacity-50 disabled:hover:text-ink-5';

// Section 2: run history. Filters at the top apply the moment something is
// entered or picked — no search button — and show as removable pills
// (ticker, tier, status and outlook take several values at once). The
// page owns the filter and page state and asks the server for one page
// at a time (2026-09-21); this component only draws it. Below, one row
// per run (10 per page), each fact sitting directly under its filter:
// ticker, capital, risk, rewardRatio, max maxHoldWeeks, tier, status, outlook, date,
// and a trash button at the end of the row (owner request 2026-09-23:
// no delete link inside the expanded row) — or, while the run is
// running, a stop button in the same spot (2026-10-19). Clicking a row
// expands the full report inline. A freshly started run appears at the
// top as Queued or Running with a dash for its outlook, and turns into a
// Succeeded row with its outlook when it finishes, or a Stopped row
// whose report holds what finished before the stop.
export const RunHistory = ({
  runs,
  tickers,
  filters,
  onFilters,
  page,
  pageCount,
  onPage,
  expandedTaskId,
  expandedResult,
  expandedError,
  onToggle,
  onDelete,
  deletingTaskId,
  deleteError,
  onStop,
  stoppingTaskIds,
  stopError,
}: RunHistoryProps) => {
  const { t, language } = useUiLanguage();
  // The run whose amber date was clicked — its previous-day note is open.
  const [staleNoteTaskId, setStaleNoteTaskId] = useState<string | null>(null);
  // The run whose trash button was clicked — its confirmation is open.
  const [confirmTaskId, setConfirmTaskId] = useState<string | null>(null);
  // The run whose removal was last confirmed: the server's refusal, if
  // any, shows under that row.
  const [removedTaskId, setRemovedTaskId] = useState<string | null>(null);
  // The same two for the stop button.
  const [confirmStopTaskId, setConfirmStopTaskId] = useState<string | null>(null);
  const [stoppedTaskId, setStoppedTaskId] = useState<string | null>(null);

  const hasFilters = hasAnyFilter(filters);

  // Pills in filter order: ticker, capital, risk, rewardRatio, max maxHoldWeeks, tier,
  // status, outlook, date.
  const pills: { key: string; tone: string; label: string; onRemove: () => void }[] = [];
  filters.tickers.forEach((ticker) => {
    pills.push({
      key: `ticker-${ticker}`,
      tone: TONE.ticker,
      label: t('tiered.pill.ticker', { value: ticker }),
      onRemove: () => onFilters({ tickers: toggled(filters.tickers, ticker) }),
    });
  });
  ([
    ['capitalMin', TONE.capital, 'tiered.pill.capitalMin'],
    ['capitalMax', TONE.capital, 'tiered.pill.capitalMax'],
    ['riskPctMin', TONE.risk, 'tiered.pill.riskPctMin'],
    ['riskPctMax', TONE.risk, 'tiered.pill.riskPctMax'],
    ['rewardRatioMin', TONE.rewardRatio, 'tiered.pill.rewardRatioMin'],
    ['rewardRatioMax', TONE.rewardRatio, 'tiered.pill.rewardRatioMax'],
  ] as const).forEach(([field, tone, labelKey]) => {
    const value = filters[field];
    if (value) {
      pills.push({
        key: field,
        tone,
        label: t(labelKey, { value }),
        onRemove: () => onFilters({ [field]: null }),
      });
    }
  });
  filters.maxHoldWeeks.forEach((maxHoldWeeks) => {
    pills.push({
      key: `hold-${maxHoldWeeks}`,
      tone: TONE.maxHoldWeeks,
      label: t('tiered.pill.hold', { value: maxHoldWeeks }),
      onRemove: () => onFilters({ maxHoldWeeks: toggled(filters.maxHoldWeeks, maxHoldWeeks) }),
    });
  });
  filters.tiers.forEach((tier) => {
    pills.push({
      key: `tier-${tier}`,
      tone: TONE.tier,
      label: t('tiered.pill.tier', { value: tier }),
      onRemove: () => onFilters({ tiers: toggled(filters.tiers, tier) }),
    });
  });
  filters.statuses.forEach((status) => {
    pills.push({
      key: `status-${status}`,
      tone: TONE.status,
      label: t('tiered.pill.status', {
        value: t(`tiered.status.${status}` as UiTextKey),
      }),
      onRemove: () => onFilters({ statuses: toggled(filters.statuses, status) }),
    });
  });
  filters.outlooks.forEach((outlook) => {
    pills.push({
      key: `outlook-${outlook}`,
      tone: TONE.outlook,
      label: t('tiered.pill.outlook', { value: outlookOptionLabel(outlook, t) }),
      onRemove: () => onFilters({ outlooks: toggled(filters.outlooks, outlook) }),
    });
  });
  ([
    ['dateMin', TONE.date, 'tiered.pill.dateMin'],
    ['dateMax', TONE.date, 'tiered.pill.dateMax'],
  ] as const).forEach(([field, tone, labelKey]) => {
    const value = filters[field];
    if (value) {
      pills.push({
        key: field,
        tone,
        label: t(labelKey, { value }),
        onRemove: () => onFilters({ [field]: null }),
      });
    }
  });

  return (
    <div className="flex w-full flex-col gap-4">
      <div className={FILTER_GRID}>
        <Select
          label={t('tiered.form.ticker')}
          tone={filters.tickers.length > 0 ? TONE.ticker : undefined}
          options={tickers.map((value) => ({ value, label: value }))}
          selected={filters.tickers}
          placeholder={t('tiered.filter.tickerPh')}
          multi
          onCommit={(value) => onFilters({ tickers: toggled(filters.tickers, value) })}
        />
        <PairField
          label={t('tiered.filter.capital')}
          tone={filters.capitalMin || filters.capitalMax ? TONE.capital : undefined}
          start={{
            placeholder: t('tiered.filter.min'),
            inputMode: 'decimal',
            validate: isPositiveNumber,
            onCommit: (value) => onFilters({ capitalMin: value }),
          }}
          end={{
            placeholder: t('tiered.filter.max'),
            inputMode: 'decimal',
            validate: isPositiveNumber,
            onCommit: (value) => onFilters({ capitalMax: value }),
          }}
        />
        <PairField
          label={t('tiered.filter.risk')}
          tone={filters.riskPctMin || filters.riskPctMax ? TONE.risk : undefined}
          start={{
            placeholder: t('tiered.filter.min'),
            inputMode: 'decimal',
            validate: isRiskPct,
            onCommit: (value) => onFilters({ riskPctMin: value }),
          }}
          end={{
            placeholder: t('tiered.filter.max'),
            inputMode: 'decimal',
            validate: isRiskPct,
            onCommit: (value) => onFilters({ riskPctMax: value }),
          }}
        />
        <PairField
          label={t('tiered.filter.reward')}
          tone={filters.rewardRatioMin || filters.rewardRatioMax ? TONE.rewardRatio : undefined}
          start={{
            placeholder: t('tiered.filter.min'),
            inputMode: 'decimal',
            validate: isPositiveNumber,
            onCommit: (value) => onFilters({ rewardRatioMin: value }),
          }}
          end={{
            placeholder: t('tiered.filter.max'),
            inputMode: 'decimal',
            validate: isPositiveNumber,
            onCommit: (value) => onFilters({ rewardRatioMax: value }),
          }}
        />
        <Select
          label={t('tiered.form.hold')}
          tone={filters.maxHoldWeeks.length > 0 ? TONE.maxHoldWeeks : undefined}
          options={FILTER_HOLDS.map((value) => ({ value, label: value }))}
          selected={filters.maxHoldWeeks}
          placeholder={t('tiered.filter.holdPh')}
          multi
          onCommit={(value) => onFilters({ maxHoldWeeks: toggled(filters.maxHoldWeeks, value) })}
        />
        <Select
          label={t('tiered.filter.tier')}
          tone={filters.tiers.length > 0 ? TONE.tier : undefined}
          options={FILTER_TIERS.map((value) => ({
            value,
            label: t(`tiered.form.tierOption${value}` as UiTextKey),
          }))}
          selected={filters.tiers}
          placeholder={t('tiered.filter.tierPh')}
          multi
          onCommit={(value) => onFilters({ tiers: toggled(filters.tiers, value) })}
        />
        <Select
          label={t('tiered.filter.status')}
          tone={filters.statuses.length > 0 ? TONE.status : undefined}
          options={FILTER_STATUSES.map((value) => ({
            value,
            label: t(`tiered.status.${value}` as UiTextKey),
          }))}
          selected={filters.statuses}
          placeholder={t('tiered.filter.statusPh')}
          multi
          onCommit={(value) => onFilters({ statuses: toggled(filters.statuses, value) })}
        />
        <Select
          label={t('tiered.filter.outlook')}
          tone={filters.outlooks.length > 0 ? TONE.outlook : undefined}
          options={FILTER_OUTLOOKS.map((value) => ({
            value,
            label: outlookOptionLabel(value, t),
          }))}
          selected={filters.outlooks}
          placeholder={t('tiered.filter.outlookPh')}
          multi
          onCommit={(value) => onFilters({ outlooks: toggled(filters.outlooks, value) })}
        />
        <PairField
          label={t('tiered.filter.date')}
          tone={filters.dateMin || filters.dateMax ? TONE.date : undefined}
          start={{
            placeholder: t('tiered.filter.min'),
            validate: isValidDay,
            onCommit: (value) => onFilters({ dateMin: value }),
          }}
          end={{
            placeholder: t('tiered.filter.max'),
            validate: isValidDay,
            onCommit: (value) => onFilters({ dateMax: value }),
          }}
        />
      </div>

      {/* the row keeps its height when empty so pills cause no layout shift */}
      <PillRow>
        {pills.map((pill) => (
          <Pill key={pill.key} tone={pill.tone} onRemove={pill.onRemove}>
            {pill.label}
          </Pill>
        ))}
      </PillRow>

      {runs.length === 0 ? (
        <p className="py-8 text-center text-sm text-ink-5">
          {hasFilters ? t('tiered.history.none') : t('tiered.empty')}
        </p>
      ) : (
        <>
          {/* Column names, so each row value reads without guessing. */}
          <div
            data-testid="history-header"
            className={cn(ROW_GRID, 'border-b border-border/40 pb-1.5')}
          >
            {HEADER_KEYS.map((key) => (
              <span key={key} className="text-xs font-semibold text-ink-4">
                {t(key)}
              </span>
            ))}
            {/* The trash column has no name. */}
            <span aria-hidden="true" className="w-6" />
          </div>
          <ul className="flex flex-col divide-y divide-border/40">
          {runs.map((run) => {
            const isExpanded = run.run_id === expandedTaskId;
            return (
              <li key={run.run_id}>
                <div
                  role="button"
                  tabIndex={0}
                  aria-expanded={isExpanded}
                  onClick={() => onToggle(run.run_id)}
                  onKeyDown={rowKeyDown(() => onToggle(run.run_id))}
                  className={cn(
                    ROW_GRID,
                    'cursor-pointer items-center rounded py-2.5 text-start text-sm hover:bg-surface-2/60',
                    isExpanded ? 'bg-surface-2/40' : '',
                  )}
                >
                  <span className="truncate font-semibold text-ink-2">{run.ticker}</span>
                  <span
                    id={`run-${run.run_id}-capital`}
                    className="text-xs tabular-nums text-ink-3"
                  >
                    {run.capital == null ? '—' : plainNumber(run.capital)}
                  </span>
                  <span
                    id={`run-${run.run_id}-risk`}
                    className="text-xs tabular-nums text-ink-3"
                  >
                    {riskCell(run)}
                  </span>
                  <span
                    id={`run-${run.run_id}-reward`}
                    className="text-xs tabular-nums text-ink-3"
                  >
                    {rewardCell(run)}
                  </span>
                  <span className="text-xs tabular-nums text-ink-3">
                    {run.max_hold_weeks == null
                      ? '—'
                      : t('tiered.history.hold', { value: run.max_hold_weeks })}
                  </span>
                  <span className="text-xs text-ink-3">
                    {run.tier == null ? '—' : t('tiered.history.tier', { value: run.tier })}
                  </span>
                  {run.status === 'queued' ? (
                    <span className="text-xs text-caution">
                      {run.queue_position == null
                        ? t('tiered.status.queued')
                        : t('tiered.status.queuedAt', {
                            position: queuePosition(run.queue_position, language),
                          })}
                    </span>
                  ) : run.status === 'running' ? (
                    <span className="text-xs text-info">{t('tiered.status.running')}</span>
                  ) : run.status === 'failed' ? (
                    <span className="text-xs text-negative">{t('tiered.status.failed')}</span>
                  ) : run.status === 'stopped' ? (
                    <span className="text-xs text-caution">{t('tiered.status.stopped')}</span>
                  ) : (
                    <span className="text-xs text-positive">{t('tiered.status.succeeded')}</span>
                  )}
                  {hasOutlook(run) ? (
                    <span className={cn('text-xs', OUTLOOK_TEXT[runOutlook(run)])}>
                      {t(`tiered.outlook.${runOutlook(run)}` as UiTextKey)}
                    </span>
                  ) : (
                    <span className="text-xs text-ink-3">—</span>
                  )}
                  {dateTone(run) === 'stale' ? (
                    // A span, not a button: the whole row is already a
                    // button, and a click here must not toggle it.
                    <span
                      role="button"
                      data-testid="run-date-stale"
                      title={t('tiered.staleWarning')}
                      className="cursor-pointer truncate text-xs tabular-nums text-caution hover:text-caution-hover"
                      onClick={(event) => {
                        event.stopPropagation();
                        setStaleNoteTaskId(run.run_id);
                      }}
                    >
                      {formatTime(run)}
                    </span>
                  ) : (
                    <span
                      className={cn(
                        'truncate text-xs tabular-nums',
                        dateTone(run) === 'fresh' ? 'text-positive' : 'text-ink-3',
                      )}
                    >
                      {formatTime(run)}
                    </span>
                  )}
                  {isRemovable(run) ? (
                    // A click here removes the run, never toggles the row.
                    <button
                      type="button"
                      data-testid="run-delete"
                      aria-label={
                        deletingTaskId === run.run_id
                          ? t('tiered.history.deleting')
                          : run.status === 'queued'
                            ? t('tiered.history.cancel')
                            : t('tiered.history.delete')
                      }
                      title={
                        deletingTaskId === run.run_id
                          ? t('tiered.history.deleting')
                          : run.status === 'queued'
                            ? t('tiered.history.cancel')
                            : t('tiered.history.delete')
                      }
                      disabled={deletingTaskId === run.run_id}
                      onClick={(event) => {
                        event.stopPropagation();
                        setConfirmTaskId(run.run_id);
                      }}
                      className={ROW_BUTTON}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  ) : (
                    // A running run: the stop button sits where the
                    // trash will once it has stopped. A click here stops
                    // the run (after a confirmation), never toggles the row.
                    <button
                      type="button"
                      data-testid="run-stop"
                      aria-label={
                        stoppingTaskIds.includes(run.run_id)
                          ? t('tiered.history.stopping')
                          : t('tiered.history.stop')
                      }
                      title={
                        stoppingTaskIds.includes(run.run_id)
                          ? t('tiered.history.stopping')
                          : t('tiered.history.stop')
                      }
                      disabled={stoppingTaskIds.includes(run.run_id)}
                      onClick={(event) => {
                        event.stopPropagation();
                        setConfirmStopTaskId(run.run_id);
                      }}
                      className={ROW_BUTTON}
                    >
                      <Square className="h-3.5 w-3.5 fill-current" />
                    </button>
                  )}
                </div>
                {deleteError && removedTaskId === run.run_id ? (
                  <p className="pb-2 text-xs text-caution" data-testid="run-delete-error">
                    {deleteError}
                  </p>
                ) : null}
                {stopError && stoppedTaskId === run.run_id ? (
                  <p className="pb-2 text-xs text-caution" data-testid="run-stop-error">
                    {stopError}
                  </p>
                ) : null}
                <Modal
                  isOpen={confirmStopTaskId === run.run_id}
                  onClose={() => setConfirmStopTaskId(null)}
                >
                  <div className={MODAL_BODY}>
                    <p>{t('tiered.history.stopAsk')}</p>
                    <div className="flex justify-end gap-4 pt-1">
                      <button
                        type="button"
                        className="cursor-pointer text-ink-3 hover:text-ink-1"
                        onClick={() => setConfirmStopTaskId(null)}
                      >
                        {t('tiered.history.keep')}
                      </button>
                      <button
                        type="button"
                        data-testid="run-stop-confirm"
                        className="cursor-pointer font-semibold text-negative hover:text-negative-hover"
                        onClick={() => {
                          setConfirmStopTaskId(null);
                          setStoppedTaskId(run.run_id);
                          onStop(run.run_id);
                        }}
                      >
                        {t('tiered.history.confirmStop')}
                      </button>
                    </div>
                  </div>
                </Modal>
                <Modal
                  isOpen={confirmTaskId === run.run_id}
                  onClose={() => setConfirmTaskId(null)}
                >
                  <div className={MODAL_BODY}>
                    <p>
                      {run.status === 'queued'
                        ? t('tiered.history.cancelAsk')
                        : t('tiered.history.deleteAsk')}
                    </p>
                    <div className="flex justify-end gap-4 pt-1">
                      <button
                        type="button"
                        className="cursor-pointer text-ink-3 hover:text-ink-1"
                        onClick={() => setConfirmTaskId(null)}
                      >
                        {t('tiered.history.keep')}
                      </button>
                      <button
                        type="button"
                        data-testid="run-delete-confirm"
                        className="cursor-pointer font-semibold text-negative hover:text-negative-hover"
                        onClick={() => {
                          setConfirmTaskId(null);
                          setRemovedTaskId(run.run_id);
                          onDelete(run.run_id);
                        }}
                      >
                        {run.status === 'queued'
                          ? t('tiered.history.confirmCancel')
                          : t('tiered.history.confirmDelete')}
                      </button>
                    </div>
                  </div>
                </Modal>
                <Modal
                  isOpen={staleNoteTaskId === run.run_id}
                  onClose={() => setStaleNoteTaskId(null)}
                >
                  <p className="text-sm text-caution" data-testid="stale-note">
                    {t('tiered.staleWarning')}
                  </p>
                </Modal>
                {isExpanded ? (
                  <div className="pb-5 pt-3">
                    {run.status === 'failed' ? (
                      <p className="text-sm text-negative">
                        {run.error ?? expandedError ?? t('tiered.error.title')}
                      </p>
                    ) : run.status === 'queued' ? (
                      <p className="text-sm text-ink-4">{t('tiered.queued')}</p>
                    ) : run.status === 'running' ? (
                      <p className="text-sm text-ink-4">
                        {stoppingTaskIds.includes(run.run_id)
                          ? t('tiered.stopping')
                          : t('tiered.running')}
                      </p>
                    ) : expandedResult ? (
                      <Report result={expandedResult} runId={run.run_id} />
                    ) : expandedError ? (
                      <p className="text-sm text-negative">{expandedError}</p>
                    ) : (
                      <p className="text-sm text-ink-4">{t('tiered.history.loading')}</p>
                    )}
                  </div>
                ) : null}
              </li>
            );
          })}
          </ul>
        </>
      )}

      <PageSelector
        page={page}
        pageCount={pageCount}
        onPage={onPage}
        labels={{
          first: t('tiered.history.first'),
          prev: t('tiered.history.prev'),
          next: t('tiered.history.next'),
          last: t('tiered.history.last'),
        }}
      />
    </div>
  );
};
