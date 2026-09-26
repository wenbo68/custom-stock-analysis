import { describe, expect, it } from 'vitest';
import {
  NO_FILTERS,
  PAGE_SIZE,
  hasAnyFilter,
  isValidDay,
  parseDay,
  toListQuery,
  toggled,
} from '../historyFilters';

describe('historyFilters', () => {
  it('turns empty filters into a bare page request', () => {
    expect(toListQuery(NO_FILTERS, 2)).toEqual({
      ticker: [],
      status: [],
      outlook: [],
      capital_min: undefined,
      capital_max: undefined,
      risk_pct_min: undefined,
      risk_pct_max: undefined,
      reward_ratio_min: undefined,
      reward_ratio_max: undefined,
      max_hold_weeks: [],
      tier: [],
      created_after: undefined,
      created_before: undefined,
      page: 2,
      page_size: PAGE_SIZE,
    });
  });

  it('converts what the user typed into what the server takes', () => {
    const query = toListQuery(
      {
        ...NO_FILTERS,
        tickers: ['AAPL'],
        statuses: ['done'],
        outlooks: ['none'],
        tiers: ['2'],
        maxHoldWeeks: ['1', '4'],
        capitalMin: '50000',
        riskPctMin: '0.5',
        riskPctMax: '2',
        rewardRatioMax: '3',
        dateMin: '2026/07/01',
        dateMax: '2026-07-31',
      },
      1,
    );
    expect(query.ticker).toEqual(['AAPL']);
    expect(query.tier).toEqual([2]);
    expect(query.max_hold_weeks).toEqual([1, 4]);
    expect(query.capital_min).toBe(50000);
    // risk is typed as a percent and sent as one (the server converts)
    expect(query.risk_pct_min).toBe(0.5);
    expect(query.risk_pct_max).toBe(2);
    expect(query.reward_ratio_max).toBe(3);
    // the date range is [start of dateMin, start of the day after
    // dateMax) in local time, sent as UTC instants
    expect(query.created_after).toBe(parseDay('2026/07/01').toISOString());
    expect(query.created_before).toBe(parseDay('2026-07-31', 1).toISOString());
  });

  it('knows whether anything is set', () => {
    expect(hasAnyFilter(NO_FILTERS)).toBe(false);
    expect(hasAnyFilter({ ...NO_FILTERS, dateMax: '2026/07/31' })).toBe(true);
    expect(hasAnyFilter({ ...NO_FILTERS, outlooks: ['bullish'] })).toBe(true);
  });

  it('toggles a value in and out of a list without mutating it', () => {
    const list = ['a'];
    expect(toggled(list, 'b')).toEqual(['a', 'b']);
    expect(toggled(list, 'a')).toEqual([]);
    expect(list).toEqual(['a']);
  });

  it('validates days in either spelling', () => {
    expect(isValidDay('2026/07/14')).toBe(true);
    expect(isValidDay('2026-07-14')).toBe(true);
    expect(isValidDay('yesterday')).toBe(false);
    expect(isValidDay('2026/13/45')).toBe(true); // rolls over, like Date
  });
});
