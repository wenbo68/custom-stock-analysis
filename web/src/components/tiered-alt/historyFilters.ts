import type { TieredRunListQuery } from '../../api/tiered';

// The run history's filters (2026-09-21: applied by the server, one page
// at a time — this module only holds the filter state and turns it into
// the list query). Text fields keep what the user typed; the query
// converts (risk % → fraction, local day → UTC instant).
export interface HistoryFilters {
  tickers: string[];
  capitalMin: string | null;
  capitalMax: string | null;
  riskMin: string | null;
  riskMax: string | null;
  rewardMin: string | null;
  rewardMax: string | null;
  holds: string[];
  tiers: string[];
  statuses: string[];
  outlooks: string[];
  dateMin: string | null;
  dateMax: string | null;
}

export const NO_FILTERS: HistoryFilters = {
  tickers: [],
  capitalMin: null,
  capitalMax: null,
  riskMin: null,
  riskMax: null,
  rewardMin: null,
  rewardMax: null,
  holds: [],
  tiers: [],
  statuses: [],
  outlooks: [],
  dateMin: null,
  dateMax: null,
};

// Rows per history page — the page size the list query asks for.
export const PAGE_SIZE = 10;

// Add the value if absent, remove it if present — how multi-value filters
// clear from the dropdown as well as from the pill.
export function toggled(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

export function hasAnyFilter(filters: HistoryFilters): boolean {
  return (
    filters.tickers.length > 0 ||
    filters.holds.length > 0 ||
    filters.tiers.length > 0 ||
    filters.statuses.length > 0 ||
    filters.outlooks.length > 0 ||
    filters.capitalMin !== null ||
    filters.capitalMax !== null ||
    filters.riskMin !== null ||
    filters.riskMax !== null ||
    filters.rewardMin !== null ||
    filters.rewardMax !== null ||
    filters.dateMin !== null ||
    filters.dateMax !== null
  );
}

// Accepts 2026/07/14 or 2026-07-14; day boundaries are the viewer's local time.
const DAY_RE = /^\d{4}[/-]\d{2}[/-]\d{2}$/;

export function parseDay(raw: string, plusDays = 0): Date {
  const [year, month, day] = raw.split(/[/-]/).map(Number);
  return new Date(year, month - 1, day + plusDays);
}

export const isValidDay = (raw: string): boolean => {
  if (!DAY_RE.test(raw)) {
    return false;
  }
  return !Number.isNaN(parseDay(raw).getTime());
};

const numberOrUndefined = (raw: string | null): number | undefined => {
  if (raw === null || raw === '') {
    return undefined;
  }
  const value = Number(raw);
  return Number.isFinite(value) ? value : undefined;
};

const percentToFraction = (raw: string | null): number | undefined => {
  const value = numberOrUndefined(raw);
  return value === undefined ? undefined : value / 100;
};

const dayToInstant = (raw: string | null, plusDays = 0): string | undefined =>
  raw && isValidDay(raw) ? parseDay(raw, plusDays).toISOString() : undefined;

// The list query for one page of the history under these filters.
// The date range is [start of dateMin, start of the day after dateMax)
// in the viewer's local time, sent as UTC instants.
export function toListQuery(filters: HistoryFilters, page: number): TieredRunListQuery {
  return {
    ticker: filters.tickers,
    status: filters.statuses,
    outlook: filters.outlooks,
    tier: filters.tiers.map(Number),
    hold_weeks: filters.holds.map(Number),
    capital_min: numberOrUndefined(filters.capitalMin),
    capital_max: numberOrUndefined(filters.capitalMax),
    risk_min: percentToFraction(filters.riskMin),
    risk_max: percentToFraction(filters.riskMax),
    reward_min: numberOrUndefined(filters.rewardMin),
    reward_max: numberOrUndefined(filters.rewardMax),
    created_after: dayToInstant(filters.dateMin),
    created_before: dayToInstant(filters.dateMax, 1),
    page,
    page_size: PAGE_SIZE,
  };
}
