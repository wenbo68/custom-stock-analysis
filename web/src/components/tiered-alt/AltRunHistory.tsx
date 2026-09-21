import { useState } from 'react';
import type { TieredResult, TieredRunSummary } from '../../api/tiered';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import { cn } from '../../utils/cn';
import { isFromPreviousDay, plainNumber, queuePosition, riskPctText } from './altFormat';
import { ALT_COLOR, OUTLOOK_TEXT } from './altStyles';
import { AltPageSelector, AltPairField, AltPill, AltPillRow, AltSelect } from './AltFields';
import { AltResult } from './AltResult';
import { AltModal, MODAL_BODY } from './AltUi';
import { hasAnyFilter, isValidDay, toggled, type HistoryFilters } from './historyFilters';

// Status (where the run is: queued, running, done, failed) and outlook
// (what the finished analysis says) are separate columns (owner request
// 2026-09-17). Only a real opinion counts as an outlook: a run with none
// (unfinished, failed, or the judge produced nothing) shows a dash —
// and the outlook filter offers that dash too (owner request 2026-09-18).
const FILTER_STATUSES = ['queued', 'running', 'done', 'failed'] as const;
const OUTLOOK_WORDS = ['bullish', 'neutral', 'bearish'] as const;
// The server's name for "rows with no opinion" in the outlook filter.
const NO_OUTLOOK = 'none';
const FILTER_OUTLOOKS = [...OUTLOOK_WORDS, NO_OUTLOOK] as const;
const FILTER_TIERS = ['1', '2'] as const;
// Max hold choices in weeks — same values the run form offers.
const FILTER_HOLDS = ['1', '2', '3', '4'] as const;

// The filters share the run form's 6-per-row grid (owner request
// 2026-08-09): ticker, capital, risk, reward, max hold and tier on the
// first line; status, outlook and date on the second (shares dropped,
// owner request 2026-08-16).
const FILTER_GRID =
  'grid w-full grid-cols-2 gap-2 text-sm sm:grid-cols-6 sm:gap-3 md:gap-4';
// The column-name header and every run row share this template, so each
// value sits under its column name.
const ROW_GRID =
  'grid w-full grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3 lg:grid-cols-4 lg:gap-4 xl:grid-cols-9';

// Filter colors follow the shared palette in field order; a range's Min
// and Max share one color (ALT_COLOR).
const TONE = {
  ticker: ALT_COLOR[1],
  capital: ALT_COLOR[2],
  risk: ALT_COLOR[3],
  reward: ALT_COLOR[4],
  hold: ALT_COLOR[5],
  tier: ALT_COLOR[6],
  status: ALT_COLOR[7],
  outlook: ALT_COLOR[8],
  date: ALT_COLOR[9],
};

// The run list's column names, in row order.
const HEADER_KEYS = [
  'tiered.altHistory.h.ticker',
  'tiered.altHistory.h.capital',
  'tiered.altHistory.h.risk',
  'tiered.altHistory.h.reward',
  'tiered.altHistory.h.hold',
  'tiered.altHistory.h.tier',
  'tiered.altHistory.h.status',
  'tiered.altHistory.h.outlook',
  'tiered.altHistory.h.date',
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
  if (!run.created_at) {
    return null;
  }
  const date = new Date(run.created_at.endsWith('Z') ? run.created_at : `${run.created_at}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

// yyyy/mm/dd, hh:mm in the viewer's local time, 24-hour clock.
function formatTime(run: TieredRunSummary): string {
  const date = runTime(run);
  if (!date) {
    return '—';
  }
  const pad = (part: number) => String(part).padStart(2, '0');
  return (
    `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())}, ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

// The run's risk input as the percent the user typed ('1%'), or a dash.
function riskCell(run: TieredRunSummary): string {
  return run.risk_fraction == null ? '—' : `${riskPctText(run.risk_fraction)}%`;
}

// The run's reward-to-risk goal as the multiple the user typed ('2×').
function rewardCell(run: TieredRunSummary): string {
  return run.reward_risk == null ? '—' : `${plainNumber(run.reward_risk)}×`;
}

// The row's outlook (null until the run is done).
function runOutlook(run: TieredRunSummary): string {
  return run.outlook ?? 'unknown';
}

// Whether the row has an outlook worth a word (see OUTLOOK_WORDS).
function hasOutlook(run: TieredRunSummary): boolean {
  return run.status === 'done' && (OUTLOOK_WORDS as readonly string[]).includes(runOutlook(run));
}

// The outlook filter's option text: the outlook word, or the dash.
function outlookOptionLabel(value: string, t: (key: UiTextKey) => string): string {
  return value === NO_OUTLOOK ? '—' : t(`tiered.outlook.${value}` as UiTextKey);
}

// The history row's date color (owner request 2026-09-18): green when
// the finished report is good to use, amber when it is from a previous
// trading day (clicking it says so), gray while there is no report.
function dateTone(run: TieredRunSummary): 'fresh' | 'stale' | 'none' {
  if (run.status !== 'done') {
    return 'none';
  }
  const time = runTime(run);
  return time && isFromPreviousDay(time) ? 'stale' : 'fresh';
}

export interface AltRunHistoryProps {
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
  onToggle: (taskId: string) => void;
  /** Remove the run (a queued one is thereby cancelled); the page asks the server. */
  onDelete: (taskId: string) => void;
  /** The run whose removal is in flight, if any. */
  deletingTaskId: string | null;
  /** Why the last removal failed, shown under the expanded row. */
  deleteError: string | null;
}

// Whether the row offers removal: a running run cannot be stopped.
const isRemovable = (run: TieredRunSummary): boolean => run.status !== 'running';

// Section 2: run history. Filters at the top apply the moment something is
// entered or picked — no search button — and show as removable pills
// (ticker, tier, status and outlook take several values at once). The
// page owns the filter and page state and asks the server for one page
// at a time (2026-09-21); this component only draws it. Below, one row
// per run (10 per page), each fact sitting directly under its filter:
// ticker, capital, risk, reward, max hold, tier, status, outlook, date.
// Clicking a row expands the full report inline. A freshly started run
// appears at the top as Queued or Running with a dash for its outlook,
// and turns into a Done row with its outlook when it finishes.
export const AltRunHistory = ({
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
}: AltRunHistoryProps) => {
  const { t, language } = useUiLanguage();
  // The run whose amber date was clicked — its previous-day note is open.
  const [staleNoteTaskId, setStaleNoteTaskId] = useState<string | null>(null);
  // The run whose remove button was clicked — its confirmation is open.
  const [confirmTaskId, setConfirmTaskId] = useState<string | null>(null);

  const hasFilters = hasAnyFilter(filters);

  // Pills in filter order: ticker, capital, risk, reward, max hold, tier,
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
    ['riskMin', TONE.risk, 'tiered.pill.riskMin'],
    ['riskMax', TONE.risk, 'tiered.pill.riskMax'],
    ['rewardMin', TONE.reward, 'tiered.pill.rewardMin'],
    ['rewardMax', TONE.reward, 'tiered.pill.rewardMax'],
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
  filters.holds.forEach((hold) => {
    pills.push({
      key: `hold-${hold}`,
      tone: TONE.hold,
      label: t('tiered.pill.hold', { value: hold }),
      onRemove: () => onFilters({ holds: toggled(filters.holds, hold) }),
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
        <AltSelect
          label={t('tiered.altForm.ticker')}
          tone={filters.tickers.length > 0 ? TONE.ticker : undefined}
          options={tickers.map((value) => ({ value, label: value }))}
          selected={filters.tickers}
          placeholder={t('tiered.altFilter.tickerPh')}
          multi
          onCommit={(value) => onFilters({ tickers: toggled(filters.tickers, value) })}
        />
        <AltPairField
          label={t('tiered.altFilter.capital')}
          tone={filters.capitalMin || filters.capitalMax ? TONE.capital : undefined}
          start={{
            placeholder: t('tiered.altFilter.min'),
            inputMode: 'decimal',
            validate: isPositiveNumber,
            onCommit: (value) => onFilters({ capitalMin: value }),
          }}
          end={{
            placeholder: t('tiered.altFilter.max'),
            inputMode: 'decimal',
            validate: isPositiveNumber,
            onCommit: (value) => onFilters({ capitalMax: value }),
          }}
        />
        <AltPairField
          label={t('tiered.altFilter.risk')}
          tone={filters.riskMin || filters.riskMax ? TONE.risk : undefined}
          start={{
            placeholder: t('tiered.altFilter.min'),
            inputMode: 'decimal',
            validate: isRiskPct,
            onCommit: (value) => onFilters({ riskMin: value }),
          }}
          end={{
            placeholder: t('tiered.altFilter.max'),
            inputMode: 'decimal',
            validate: isRiskPct,
            onCommit: (value) => onFilters({ riskMax: value }),
          }}
        />
        <AltPairField
          label={t('tiered.altFilter.reward')}
          tone={filters.rewardMin || filters.rewardMax ? TONE.reward : undefined}
          start={{
            placeholder: t('tiered.altFilter.min'),
            inputMode: 'decimal',
            validate: isPositiveNumber,
            onCommit: (value) => onFilters({ rewardMin: value }),
          }}
          end={{
            placeholder: t('tiered.altFilter.max'),
            inputMode: 'decimal',
            validate: isPositiveNumber,
            onCommit: (value) => onFilters({ rewardMax: value }),
          }}
        />
        <AltSelect
          label={t('tiered.altForm.hold')}
          tone={filters.holds.length > 0 ? TONE.hold : undefined}
          options={FILTER_HOLDS.map((value) => ({ value, label: value }))}
          selected={filters.holds}
          placeholder={t('tiered.altFilter.holdPh')}
          multi
          onCommit={(value) => onFilters({ holds: toggled(filters.holds, value) })}
        />
        <AltSelect
          label={t('tiered.altFilter.tier')}
          tone={filters.tiers.length > 0 ? TONE.tier : undefined}
          options={FILTER_TIERS.map((value) => ({
            value,
            label: t(`tiered.altForm.tierOption${value}` as UiTextKey),
          }))}
          selected={filters.tiers}
          placeholder={t('tiered.altFilter.tierPh')}
          multi
          onCommit={(value) => onFilters({ tiers: toggled(filters.tiers, value) })}
        />
        <AltSelect
          label={t('tiered.altFilter.status')}
          tone={filters.statuses.length > 0 ? TONE.status : undefined}
          options={FILTER_STATUSES.map((value) => ({
            value,
            label: t(`tiered.status.${value}` as UiTextKey),
          }))}
          selected={filters.statuses}
          placeholder={t('tiered.altFilter.statusPh')}
          multi
          onCommit={(value) => onFilters({ statuses: toggled(filters.statuses, value) })}
        />
        <AltSelect
          label={t('tiered.altFilter.outlook')}
          tone={filters.outlooks.length > 0 ? TONE.outlook : undefined}
          options={FILTER_OUTLOOKS.map((value) => ({
            value,
            label: outlookOptionLabel(value, t),
          }))}
          selected={filters.outlooks}
          placeholder={t('tiered.altFilter.outlookPh')}
          multi
          onCommit={(value) => onFilters({ outlooks: toggled(filters.outlooks, value) })}
        />
        <AltPairField
          label={t('tiered.altFilter.date')}
          tone={filters.dateMin || filters.dateMax ? TONE.date : undefined}
          start={{
            placeholder: t('tiered.altFilter.min'),
            validate: isValidDay,
            onCommit: (value) => onFilters({ dateMin: value }),
          }}
          end={{
            placeholder: t('tiered.altFilter.max'),
            validate: isValidDay,
            onCommit: (value) => onFilters({ dateMax: value }),
          }}
        />
      </div>

      {/* the row keeps its height when empty so pills cause no layout shift */}
      <AltPillRow>
        {pills.map((pill) => (
          <AltPill key={pill.key} tone={pill.tone} onRemove={pill.onRemove}>
            {pill.label}
          </AltPill>
        ))}
      </AltPillRow>

      {runs.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-600">
          {hasFilters ? t('tiered.altHistory.none') : t('tiered.empty')}
        </p>
      ) : (
        <>
          {/* Column names, so each row value reads without guessing. */}
          <div
            data-testid="alt-history-header"
            className={cn(ROW_GRID, 'border-b border-gray-800 pb-1.5')}
          >
            {HEADER_KEYS.map((key) => (
              <span key={key} className="text-xs font-semibold text-gray-500">
                {t(key)}
              </span>
            ))}
          </div>
          <ul className="flex flex-col divide-y divide-gray-800">
          {runs.map((run) => {
            const isExpanded = run.task_id === expandedTaskId;
            return (
              <li key={run.task_id}>
                <button
                  type="button"
                  onClick={() => onToggle(run.task_id)}
                  className={cn(
                    ROW_GRID,
                    'cursor-pointer items-center rounded py-2.5 text-start text-sm hover:bg-gray-800/60',
                    isExpanded ? 'bg-gray-800/40' : '',
                  )}
                >
                  <span className="truncate font-semibold text-gray-300">{run.stock_code}</span>
                  <span
                    id={`alt-run-${run.task_id}-capital`}
                    className="text-xs tabular-nums text-gray-400"
                  >
                    {run.capital == null ? '—' : plainNumber(run.capital)}
                  </span>
                  <span
                    id={`alt-run-${run.task_id}-risk`}
                    className="text-xs tabular-nums text-gray-400"
                  >
                    {riskCell(run)}
                  </span>
                  <span
                    id={`alt-run-${run.task_id}-reward`}
                    className="text-xs tabular-nums text-gray-400"
                  >
                    {rewardCell(run)}
                  </span>
                  <span className="text-xs tabular-nums text-gray-400">
                    {run.hold_weeks == null
                      ? '—'
                      : t('tiered.altHistory.hold', { value: run.hold_weeks })}
                  </span>
                  <span className="text-xs text-gray-400">
                    {run.tier == null ? '—' : t('tiered.altHistory.tier', { value: run.tier })}
                  </span>
                  {run.status === 'queued' ? (
                    <span className="text-xs text-amber-300">
                      {run.queue_ahead == null
                        ? t('tiered.status.queued')
                        : t('tiered.status.queuedAt', {
                            position: queuePosition(run.queue_ahead, language),
                          })}
                    </span>
                  ) : run.status === 'running' ? (
                    <span className="text-xs text-sky-300">{t('tiered.status.running')}</span>
                  ) : run.status === 'failed' ? (
                    <span className="text-xs text-red-300">{t('tiered.status.failed')}</span>
                  ) : (
                    <span className="text-xs text-emerald-300">{t('tiered.status.done')}</span>
                  )}
                  {hasOutlook(run) ? (
                    <span className={cn('text-xs', OUTLOOK_TEXT[runOutlook(run)])}>
                      {t(`tiered.outlook.${runOutlook(run)}` as UiTextKey)}
                    </span>
                  ) : (
                    <span className="text-xs text-gray-400">—</span>
                  )}
                  {dateTone(run) === 'stale' ? (
                    // A span, not a button: the whole row is already a
                    // button, and a click here must not toggle it.
                    <span
                      role="button"
                      data-testid="alt-run-date-stale"
                      title={t('tiered.alt.staleNote')}
                      className="cursor-pointer truncate text-xs tabular-nums text-amber-300 hover:text-amber-200"
                      onClick={(event) => {
                        event.stopPropagation();
                        setStaleNoteTaskId(run.task_id);
                      }}
                    >
                      {formatTime(run)}
                    </span>
                  ) : (
                    <span
                      className={cn(
                        'truncate text-xs tabular-nums',
                        dateTone(run) === 'fresh' ? 'text-emerald-300' : 'text-gray-400',
                      )}
                    >
                      {formatTime(run)}
                    </span>
                  )}
                </button>
                <AltModal
                  isOpen={staleNoteTaskId === run.task_id}
                  onClose={() => setStaleNoteTaskId(null)}
                >
                  <p className="text-sm text-amber-300" data-testid="alt-stale-note">
                    {t('tiered.alt.staleNote')}
                  </p>
                </AltModal>
                {isExpanded ? (
                  <div className="pb-5 pt-3">
                    {isRemovable(run) ? (
                      // Removal lives inside the expanded row (2026-09-21):
                      // one quiet link at the top, a confirmation popup, and
                      // the reason under it if the server refused.
                      <div className="mb-3 flex flex-col items-end gap-1">
                        <button
                          type="button"
                          data-testid="alt-run-remove"
                          disabled={deletingTaskId === run.task_id}
                          onClick={() => setConfirmTaskId(run.task_id)}
                          className="cursor-pointer text-xs text-gray-500 hover:text-red-300 disabled:cursor-default disabled:hover:text-gray-500"
                        >
                          {deletingTaskId === run.task_id
                            ? t('tiered.altHistory.deleting')
                            : run.status === 'queued'
                              ? t('tiered.altHistory.cancel')
                              : t('tiered.altHistory.delete')}
                        </button>
                        {deleteError ? (
                          <p className="text-xs text-amber-300" data-testid="alt-run-remove-error">
                            {deleteError}
                          </p>
                        ) : null}
                        <AltModal
                          isOpen={confirmTaskId === run.task_id}
                          onClose={() => setConfirmTaskId(null)}
                        >
                          <div className={MODAL_BODY}>
                            <p>
                              {run.status === 'queued'
                                ? t('tiered.altHistory.cancelAsk')
                                : t('tiered.altHistory.deleteAsk')}
                            </p>
                            <div className="flex justify-end gap-4 pt-1">
                              <button
                                type="button"
                                className="cursor-pointer text-gray-400 hover:text-gray-200"
                                onClick={() => setConfirmTaskId(null)}
                              >
                                {t('tiered.altHistory.keep')}
                              </button>
                              <button
                                type="button"
                                data-testid="alt-run-remove-confirm"
                                className="cursor-pointer font-semibold text-red-300 hover:text-red-200"
                                onClick={() => {
                                  setConfirmTaskId(null);
                                  onDelete(run.task_id);
                                }}
                              >
                                {run.status === 'queued'
                                  ? t('tiered.altHistory.confirmCancel')
                                  : t('tiered.altHistory.confirmDelete')}
                              </button>
                            </div>
                          </div>
                        </AltModal>
                      </div>
                    ) : null}
                    {run.status === 'failed' ? (
                      <p className="text-sm text-red-300">
                        {run.error ?? expandedError ?? t('tiered.error.title')}
                      </p>
                    ) : run.status === 'queued' ? (
                      <p className="text-sm text-gray-500">{t('tiered.queued')}</p>
                    ) : run.status === 'running' ? (
                      <p className="text-sm text-gray-500">{t('tiered.running')}</p>
                    ) : expandedResult ? (
                      <AltResult result={expandedResult} taskId={run.task_id} />
                    ) : expandedError ? (
                      <p className="text-sm text-red-300">{expandedError}</p>
                    ) : (
                      <p className="text-sm text-gray-500">{t('tiered.altHistory.loading')}</p>
                    )}
                  </div>
                ) : null}
              </li>
            );
          })}
          </ul>
        </>
      )}

      <AltPageSelector
        page={page}
        pageCount={pageCount}
        onPage={onPage}
        labels={{
          first: t('tiered.altHistory.first'),
          prev: t('tiered.altHistory.prev'),
          next: t('tiered.altHistory.next'),
          last: t('tiered.altHistory.last'),
        }}
      />
    </div>
  );
};
