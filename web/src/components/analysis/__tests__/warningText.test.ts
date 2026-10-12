import { describe, expect, it } from 'vitest';
import { UI_TEXT, formatUiText, type UiTextKey } from '../../../i18n/uiText';
import { friendlyWarning } from '../warningText';

const t = (key: UiTextKey, params?: Record<string, string | number>) =>
  formatUiText(UI_TEXT.en[key], params);

describe('friendlyWarning — a failed company-news fetch', () => {
  it('says the report has no headlines and quotes the source, under the fetch-failed keyword', () => {
    const note = friendlyWarning(
      'news headlines unavailable: 422 Client Error: Unprocessable Entity for url: https://finnhub.io/api/v1/company-news?symbol=AAPL&token=<redacted>',
      t,
    );
    expect(note?.keyword).toBe(t('tiered.warning.key.fetchFailed'));
    expect(note?.text).toBe(
      'Company news could not be fetched, so this report has no headlines. The news source said: 422 Client Error: Unprocessable Entity for url: https://finnhub.io/api/v1/company-news?symbol=AAPL&token=<redacted>',
    );
  });
});

describe('friendlyWarning — review 2026-10-10 warning shapes', () => {
  it('a wrong-language reply kept after one retry that did not parse', () => {
    const note = friendlyWarning(
      'lister 1 grade sheet reply not in Simplified Chinese after 1 retry — shown as written',
      t,
    );
    expect(note?.keyword).toBe('Unusable LLM reply');
    expect(note?.text).toContain('Lister 1');
    expect(note?.text).toContain('1');
  });

  it('a failed call in one lister names the lister and the error', () => {
    const note = friendlyWarning('lister 2 grade sheet LLM call failed: timeout', t);
    expect(note?.keyword).toBe('Unusable LLM reply');
    expect(note?.text).toBe(
      'Lister 2 — the LLM call itself failed (timeout); the deep analysis went on without this step.',
    );
  });

  it('a benchmark ending on a different day names both dates and the shared one', () => {
    const note = friendlyWarning(
      'benchmark index bars end 2026-09-18, the stock\'s end 2026-09-19 — market trend and relative strength measured through 2026-09-18',
      t,
    );
    expect(note?.keyword).toBe('Missing data');
    expect(note?.text).toContain('ends on 2026-09-18');
    expect(note?.text).toContain('stock’s on 2026-09-19');
    expect(note?.text).toContain('(2026-09-18)');
  });

  it('a failed deciding round is not the whole-deep-analysis failure', () => {
    const note = friendlyWarning('deciding round LLM call failed: 502', t);
    expect(note?.text).toContain('Deciding vote');
    expect(note?.text).not.toContain('no outlook');
  });

  it('a rejected later proposal says the earlier accepted value was kept', () => {
    const note = friendlyWarning(
      'round 2: adjustment for target rejected: moves the level more than 1 × ATR (3) away from its base 108 — the earlier accepted value 110 kept',
      t,
    );
    expect(note?.keyword).toBe(t('tiered.warning.key.levels'));
    expect(note?.text).toBe(
      'The AI’s later suggestion for the Target broke the rules, so its earlier accepted value 110 was kept.',
    );
  });

  it('a plan-review reply nobody could read is an outage, not "no change helps"', () => {
    const note = friendlyWarning(
      'round 1: plan review got no usable reply even after a fix round',
      t,
    );
    expect(note?.keyword).toBe('Unusable LLM reply');
    expect(note?.text).toContain('could not be read');
  });

  it('an unreadable importance rating says the articles are rated again next run', () => {
    const note = friendlyWarning(
      'news judge gave an unreadable importance for 2 article(s) — those kept, judged again next run',
      t,
    );
    expect(note?.keyword).toBe('Unusable LLM reply');
    expect(note?.text).toContain('2');
    expect(note?.text).toContain('next run');
  });
});

describe('friendlyWarning — deep-analysis stage notes lead with the role', () => {
  it('a retried grade sheet names its lister', () => {
    const note = friendlyWarning(
      'lister 1 grade sheet needed a retry — first reply was invalid',
      t,
    );
    expect(note?.keyword).toBe('Unusable LLM reply');
    expect(note?.text).toBe('Lister 1 — the first reply was invalid; the retry succeeded.');
  });

  it('the two listers produce two distinguishable notes', () => {
    const second = friendlyWarning(
      'lister 2 grade sheet needed a retry — first reply was invalid',
      t,
    );
    expect(second?.text).toContain('Lister 2');
  });

  it('an invalid-after-retry sheet names its lister too', () => {
    const note = friendlyWarning(
      'lister 1 grade sheet invalid after retry: unknown grade keys: technicals.levels.resistance_1',
      t,
    );
    expect(note?.text).toBe('Lister 1 — the reply was still invalid after a retry.');
  });

  it('check and deciding rounds use their vote labels', () => {
    expect(
      friendlyWarning('check round needed a retry — first reply was invalid', t)?.text,
    ).toContain('Check vote');
    expect(
      friendlyWarning('deciding round was not JSON even after a retry', t)?.text,
    ).toContain('Deciding vote');
  });

  it('an unmapped stage keeps its raw name rather than inventing a label', () => {
    const note = friendlyWarning(
      'defender opening needed a retry — first reply was invalid',
      t,
    );
    expect(note?.text).toContain('defender opening');
  });
});

describe('friendlyWarning — v12 voided-run notes are translated', () => {
  it('both grade sheets failing translates (v12 wording)', () => {
    const note = friendlyWarning(
      'both lister grade sheets invalid after retry — deep-analysis outlook voided',
      t,
    );
    expect(note?.text).toBe(
      'Neither lister produced a usable grade sheet — the deep analysis was voided.',
    );
  });

  it('the 2026-10-12 "unusable" wording of the same notes words alike', () => {
    expect(
      friendlyWarning('both lister grade sheets unusable — deep-analysis outlook voided', t)?.text,
    ).toBe('Neither lister produced a usable grade sheet — the deep analysis was voided.');
    expect(
      friendlyWarning('check round unusable — vote items counted on their lister\'s vote alone', t)?.text,
    ).toContain('no usable result');
    expect(
      friendlyWarning('deciding round unusable — tied vote items excluded as unresolved', t)?.text,
    ).toContain('unresolved');
  });

  it('the no-outlook note translates with the re-run advice', () => {
    const note = friendlyWarning(
      'deep analysis produced no outlook (re-run)',
      t,
    );
    expect(note?.text).toContain('re-run');
  });

  it('one failed sheet names the failed lister', () => {
    const note = friendlyWarning(
      'lister 2 grade sheet invalid after retry — proceeding with the other sheet only',
      t,
    );
    expect(note?.text).toContain('Lister 2');
  });
});


// Audit 2026-08-08. Every string here was copied from the Python that
// emits it; each used to fall through friendlyWarning and render as raw
// engineer text. The point of the test is DRIFT: if a backend message is
// reworded and its rule is not, the note silently reverts to raw text
// under the generic keyword and nothing else fails. That is exactly how the trend
// rules rotted (they still said "60-day" long after the backend moved to
// the 50-day average), so the samples below are verbatim on purpose.
describe('friendlyWarning — rich notes carry live slots (2026-08-23)', () => {
  it('the far-report note exposes the real countdown with its receipt data', () => {
    const note = friendlyWarning(
      'next quarterly report is 68 days away (report 2026-10-30, today 2026-08-23) — ' +
        'more than 21 days out, option prices mostly reflect ordinary drift, not the ' +
        'report jump; implied report-day move omitted',
      t,
    );
    expect(note.keyword).toBe('Missing data');
    expect(note.text).toContain('68 days away');
    expect(note.text).toContain('more than 21');
    expect(note.template).toContain('{days}');
    expect(note.slots?.days).toEqual({
      kind: 'daysReceipt',
      days: 68,
      reportDate: '2026-10-30',
      today: '2026-08-23',
    });
  });

  it('a ratio blanked by the missing implied move links that exact field', () => {
    const note = friendlyWarning(
      'implied report-day move missing — report-move ratio (implied vs 4q avg) omitted',
      t,
    );
    expect(note.keyword).toBe('Missing data');
    // The plain text names the field by its exact report label.
    expect(note.text).toContain('"Implied quarterly report day price change magnitude"');
    expect(note.slots?.field).toEqual({
      kind: 'metricLink',
      term: 'implied_report_move_pct',
      paths: ['positioning.options.implied_report_move_pct'],
    });
  });

  it('a ratio blanked by the missing realized average links that exact field', () => {
    const note = friendlyWarning(
      'realized 4q average report-day move missing or zero — report-move ratio ' +
        '(implied vs 4q avg) omitted',
      t,
    );
    expect(note.text).toContain('"4q avg report day price change magnitude"');
    expect(note.slots?.field).toEqual({
      kind: 'metricLink',
      term: 'reaction_avg_abs_pct',
      paths: ['fundamentals.quarterly_report.reaction_avg_abs_pct'],
    });
  });
});

describe('friendlyWarning — every backend note reaches plain English', () => {
  const SAMPLES: Array<[string, string]> = [
    // src/tiered_analysis/levels.py — the rotted pair.
    [
      'trend warning: close 303.42 is at or below the 50-day average 310.1 (downtrend) — a pullback buy against the trend carries extra downside risk',
      'Downtrend',
    ],
    ['sma_50 unavailable — trend check skipped', 'Missing data'],
    ['no close price — deterministic levels cannot be computed', 'Price level problem'],
    [
      'no structural support anchors (sma_50 / sma_200 / support_1) — no entry base, so no deterministic levels',
      'Price level problem',
    ],
    ['technicals unavailable — deterministic levels cannot be computed', 'Price level problem'],
    ['duplicate adjustment for entry ignored (first proposal kept)', 'Price level problem'],
    ["adjustment for unknown level 'foo' ignored", 'Price level problem'],
    // src/tiered_analysis/providers/technicals.py
    ['bars_loader failed for AAPL: HTTPError()', 'Failed fetch'],
    ['insufficient history for AAPL: 9 bars < 15 required', 'Missing data'],
    [
      'only 120 daily bars (<253): the one-year fields cover the history that exists',
      'Missing data',
    ],
    [
      'only 24 weekly bars (<60): the weekly structure read is unreliable',
      'Missing data',
    ],
    ['benchmark index not configured for this market', 'Missing data'],
    ['benchmark index bars unavailable: HTTPError()', 'Failed fetch'],
    ['benchmark index history too short (30 bars)', 'Missing data'],
    ['benchmark index history too short for the regime read', 'Missing data'],
    // src/tiered_analysis/providers/positioning.py
    [
      'CBOE published no 30-day implied volatility — implied stock volatility omitted',
      'Missing data',
    ],
    ['next report date unknown — implied report-day move omitted', 'Missing data'],
    ['next report date unparseable — implied report-day move omitted', 'Missing data'],
    ['CBOE published no stock price — implied report-day move omitted', 'Missing data'],
    [
      'no usable at-the-money quotes on the post-report expiration — implied report-day move omitted',
      'Missing data',
    ],
    [
      'no fetched option expiration falls after the next report date — implied report-day move omitted',
      'Missing data',
    ],
    ['Yahoo summary failed for AAPL: HTTPError()', 'Failed fetch'],
    ['institutional holders failed for AAPL: HTTPError()', 'Failed fetch'],
    ['insider transactions failed for AAPL: HTTPError()', 'Failed fetch'],
    ['options chain failed for AAPL: HTTPError()', 'Failed fetch'],
    ['no listed options found for AAPL', 'Missing data'],
    ['earnings date lookup failed for AAPL: HTTPError()', 'Failed fetch'],
    ['Yahoo returned no short-interest fields for AAPL', 'Missing data'],
    ['Yahoo returned no ownership fields for AAPL', 'Missing data'],
    // src/tiered_analysis/providers/fundamentals_us.py
    ['earnings history failed for AAPL: HTTPError()', 'Failed fetch'],
    [
      'no earnings history rows for AAPL — the beat and report-day-move fields are blank',
      'Missing data',
    ],
    ['bars for earnings reaction failed: HTTPError()', 'Failed fetch'],
    [
      'too few earnings reports inside the bar history (2) for the earnings-day move',
      'Missing data',
    ],
    ['EPS estimate trend failed for AAPL: HTTPError()', 'Failed fetch'],
    // src/tiered_analysis/providers/macro_economy.py
    ['FRED_API_KEY is not set; get a free key at fred.stlouisfed.org', 'Invalid setting'],
    ['FRED release calendar for inflation data (CPI) failed: HTTPError()', 'Failed fetch'],
    ['no upcoming inflation data (CPI) release date found', 'Missing data'],
    [
      "FOMC decision-date table exhausted; extend FOMC_DECISION_DATES from the Fed's published calendar",
      'Missing data',
    ],
    // src/tiered_analysis/cross_fields.py
    [
      'sector unknown (fundamentals carries no sector label); sector comparison fields absent',
      'Missing data',
    ],
    [
      "sector 'Technology' has no sector-ETF mapping (US sectors only for now); sector comparison fields absent",
      'Missing data',
    ],
    [
      'sector comparison needs the market benchmark returns, which are absent; sector comparison fields absent',
      'Missing data',
    ],
    ['sector ETF XLK bars unavailable: HTTPError(); sector comparison fields absent', 'Failed fetch'],
    ['sector ETF XLK history too short (30 bars); sector comparison fields absent', 'Missing data'],
    // src/tiered_analysis/tiers.py + deep analysis.py + plan_review.py
    ['no collected evidence to vote on — no outlook (re-run)', 'No outlook'],
    ['deep analysis LLM call failed: RuntimeError()', 'Unusable LLM reply'],
    ['no gradable report fields collected — tier-2 outlook voided', 'No outlook'],
    [
      'plan-review adjustment for stop_loss dropped — citations unfixable: bad ref',
      'Invalid citation',
    ],
    ['plan-review reply problem: missing field', 'Unusable LLM reply'],
    ['plan review skipped: LlmConfigError()', 'Invalid setting'],
    ['plan review LLM call failed: RuntimeError()', 'Unusable LLM reply'],
    [
      'plan review did not converge: the adjusted plan still tripped risk checks after every round, so all adjustments were discarded and the computed plan stands',
      'Unfinished plan review',
    ],
    // src/tiered_analysis/integration.py + settings.py
    ['positioning provider crashed: RuntimeError()', 'Failed fetch'],
    ['TIERED_REWARD_RISK=0.5 must be above 1 — using the default 2.0', 'Invalid setting'],
  ];

  it.each(SAMPLES)('rewrites %s', (raw, keyword) => {
    const note = friendlyWarning(raw, t);
    expect(note, `no rule matched: ${raw}`).not.toBeNull();
    expect(note?.keyword).toBe(keyword);
    // No rewrite may leak a Python repr or a source identifier.
    expect(note?.text).not.toMatch(/Error\(|_[a-z]+_|\bsma_\d|HTTPError/);
  });

  it('a "round N:" prefix does not defeat the rules', () => {
    // plan_review.py prefixes retried rounds; ^-anchored patterns would
    // otherwise all miss.
    const note = friendlyWarning('round 2: plan-review reply problem: missing field', t);
    expect(note?.keyword).toBe('Unusable LLM reply');
  });

  it('an unknown shape keeps its raw text under the generic keyword', () => {
    const note = friendlyWarning('something nobody has ever written', t);
    expect(note.keyword).toBe('Unknown problem');
    expect(note.text).toBe('something nobody has ever written');
  });
});

describe('friendlyWarning — news-screen stage notes', () => {
  it('every news stage retry note names its role in plain English (2026-08-25)', () => {
    const roles: Array<[string, string]> = [
      ['news judge', 'News relevance judge'],
      ['news grouping', 'Same-story news grouping'],
      ['news ranking', 'News importance ranking'],
      ['news summary', 'News summary writer'],
    ];
    for (const [stage, role] of roles) {
      const note = friendlyWarning(
        `${stage} needed a retry — first reply was invalid`,
        t,
      );
      expect(note.keyword).toBe('Unusable LLM reply');
      expect(note.text).toBe(`${role} — the first reply was invalid; the retry succeeded.`);
    }
  });

  it('a grouping reply that was not JSON reads as a merge miss, not engineer-speak', () => {
    const note = friendlyWarning('news grouping returned no usable JSON — no grouping', t);
    expect(note.keyword).toBe('Unusable LLM reply');
    expect(note.text).toContain('merges articles covering the same story');
    expect(note.text).not.toContain('JSON');
  });

  it('a grouping call that threw lands on the same sentence', () => {
    const note = friendlyWarning(
      'news grouping LLM call failed: TimeoutError() — no grouping',
      t,
    );
    expect(note.text).toContain('merges articles covering the same story');
  });

  it('the busy-window trim carries its counts under the News cap keyword', () => {
    const note = friendlyWarning(
      'busy news window: 14 event(s) ranked below the top 20 and trimmed',
      t,
    );
    expect(note.keyword).toBe('Trimmed news');
    expect(note.text).toContain('14');
    expect(note.text).toContain('top 20');
  });

  it('judge, ranking, and summary failures all translate', () => {
    expect(
      friendlyWarning('news judge returned no usable JSON — all articles kept', t).text,
    ).toContain('every article was kept unrated');
    expect(
      friendlyWarning(
        'news ranking LLM call failed: boom — importance-score order kept',
        t,
      ).text,
    ).toContain('importance-score order');
    expect(
      friendlyWarning(
        'news summary returned no usable JSON — feed abstracts shown verbatim',
        t,
      ).text,
    ).toContain('news feed’s own wording');
  });

  it('partial-coverage notes carry their counts', () => {
    expect(
      friendlyWarning('news judge gave no judgment for 3 article(s) — those kept', t).text,
    ).toContain('3');
    expect(
      friendlyWarning(
        'news grouping left 2 article(s) ungrouped — kept as separate events',
        t,
      ).text,
    ).toContain('2');
    expect(
      friendlyWarning(
        'news ranking left 5 event(s) unranked — appended in importance-score order',
        t,
      ).text,
    ).toContain('5');
    expect(
      friendlyWarning(
        'news summary missing for 4 article(s) — those show the feed abstract verbatim',
        t,
      ).text,
    ).toContain('4');
  });
});

describe('friendlyWarning — replies not in the run’s language (2026-09-26)', () => {
  it('a reply the retry fixed names the role and the language', () => {
    const note = friendlyWarning(
      'preliminary analysis needed a retry — reply not in Simplified Chinese',
      t,
    );
    expect(note?.keyword).toBe('Unusable LLM reply');
    expect(note?.text).toBe(
      'Preliminary analysis — the first reply was not in Simplified Chinese; asking again fixed it.',
    );
  });

  it('a reply still wrong after the retries says it is shown as written', () => {
    const note = friendlyWarning(
      'report outline reply not in Simplified Chinese after 2 retries — shown as written',
      t,
    );
    expect(note?.keyword).toBe('Unusable LLM reply');
    expect(note?.text).toBe(
      'Report writer — the reply was still not in Simplified Chinese after asking again 2 times, so it is shown as written.',
    );
  });

  it('a citation-fix round names the role it was fixing for', () => {
    expect(
      friendlyWarning('lister 1 grade sheet citation fix needed a retry — reply not in English', t)?.text,
    ).toBe('Lister 1 (citation fix) — the first reply was not in English; asking again fixed it.');
    expect(
      friendlyWarning(
        'summary citation fix reply not in Simplified Chinese after 2 retries — shown as written',
        t,
      )?.text,
    ).toContain('Report writer (citation fix) —');
  });

  it('the plan review and the news summary lead with their roles too', () => {
    expect(
      friendlyWarning('plan review needed a retry — reply not in Simplified Chinese', t)?.text,
    ).toContain('Plan review —');
    expect(
      friendlyWarning('news summary needed a retry — reply not in Simplified Chinese', t)?.text,
    ).toContain('News summary writer —');
  });
});
