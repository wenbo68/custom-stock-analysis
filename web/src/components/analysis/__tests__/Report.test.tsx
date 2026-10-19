import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type {
  TieredDeepAnalysisDetail,
  TieredVoteItem,
  TieredLevelsDetail,
  TieredResult,
  TieredTierSection,
} from '../../../api/tiered';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { Report } from '../Report';

const LEVELS = { entry: 96, stop_loss: 90, target: 108 };

// Consistent with LEVELS: entry and target were adjusted by the AI, the
// stop kept its computed base.
const LEVELS_DETAIL: TieredLevelsDetail = {
  levels: {
    entry: {
      // The stored prose phrase — the UI must expand it into the actual
      // support values, never show the words.
      base: 95,
      formula: 'min(close, max(support candidates))',
      inputs: { close: 100, sma_50: 95, support_1: 92 },
      adjusted: 96,
      reasons: [{ check: 'downtrend', text: 'Momentum supports paying up a little.' }],
      evidence: ['technicals.sma_20'],
      rejection: null,
      final: 96,
    },
    stop_loss: {
      base: 90,
      formula: 'ideal_entry − 2 × atr_14',
      inputs: { ideal_entry: 95, atr_14: 2.5, multiplier: 2 },
      adjusted: null,
      evidence: [],
      rejection: null,
      final: 90,
    },
    target: {
      // Resistance-capped shape: the prose tail must expand into the
      // actual resistance values.
      base: 105,
      formula: 'min(ideal_entry + 2 × (ideal_entry − stop_loss), nearest overhead resistance)',
      inputs: {
        ideal_entry: 95, stop_loss: 90, geometric_target: 105,
        resistance_1: 105, high_1y: 110,
      },
      adjusted: 108,
      reasons: [{ check: 'stop_vs_support', text: 'Growth supports a higher target.' }],
      evidence: [],
      rejection: null,
      final: 108,
    },
  },
  warnings: [],
};

function makeDimension(name: string): TieredResult['data_reports'][number] {
  return {
    name,
    kind: 'numeric',
    counted: true,
    payload: { close: 100 },
    summary: null,
    warnings: [],
    citations: [],
  };
}

function makeSection(tier: number, outlook: TieredTierSection['outlook']): TieredTierSection {
  return {
    tier,
    outlook,
    confidence: null,
    score: null,
    levels: LEVELS,
    summary: null,
    warnings: [],
  };
}

// A finished deep run in the current shape: bullish outlook, a plan
// review, and a v9 evidence-vote deep analysis.
function makeResult(): TieredResult {
  return {
    ticker: 'AAPL',
    market: 'us',
    tier: 2,
    score: 72,
    confidence: null,
    levels: LEVELS,
    levels_detail: LEVELS_DETAIL,
    summary: null,
    warnings: [],
    data_reports: ['technicals', 'fundamentals', 'macro_economy', 'positioning'].map(makeDimension),
    outlook: 'bullish',
    action: 'buy_now',
    earnings: null,
    deep_analysis: { ...makeSection(2, 'bullish'), detail: makeTreeDebateV9() },
    sizing: {
      enabled: true,
      shares: 166,
      position_value: 15936,
      risk_amount: 996,
      loss_per_share: 6,
      lot_size: 1,
      reason_code: null,
      refusal_reason: null,
      warnings: [],
      inputs: {
        capital: 100000,
        risk_pct: 1,
        entry: 96,
        stop_loss: 90,
      },
    },
  };
}

// A v9 evidence-vote audit trail: arrows and marks, majority votes.
// T1 listed by both listers (confirmed 2-0); T2 outvoted 1-2 (checker
// + deciding vote against, crossed out); T3 struck by the code citation
// check (crossed out); S1 counted 2-0 with a trailing [2] source link.
// Final pool: 1 bullish of 2 → flat score 10 × 1/2 = 5.00 → hold.
function makeTreeDebateV9(): TieredDeepAnalysisDetail {
  return {
    format: 11,
    items: [
      {
        id: 'T1',
        data_report: 'technicals',
        item_outlook: 'bullish',
        claim: 'The 14-day RSI (71.20) is above 70.',
        links: [{ ref: 'technicals.rsi_14', value: '71.20' }],
        struck: false,
        problems: [],
        lister_count: 2,
        votes: [],
        final_status: 'counted',
        exclusion_reason: null,
      },
      {
        id: 'T2',
        data_report: 'technicals',
        item_outlook: 'bearish',
        claim: 'The closing price (100) is below the 105 resistance.',
        links: [{ ref: 'technicals.close', value: '100' }],
        struck: false,
        problems: [],
        lister_count: 1,
        votes: [
          {
            role: 'checker',
            validity: 'invalid',
            reason: 'A single close below one level is not a trend.',
            links: [],
          },
          {
            role: 'decider',
            validity: 'invalid',
            reason: 'The objection maxHoldWeeks.',
            links: [],
          },
        ],
        final_status: 'excluded',
        exclusion_reason: 'outvoted',
      },
      {
        id: 'T3',
        data_report: 'technicals',
        item_outlook: 'bullish',
        claim: 'The technical score (999) is strong.',
        links: [{ ref: 'technicals.score', value: '999' }],
        struck: true,
        problems: ["item T3 link 'technicals.score': claimed value '999' must be copied exactly as the report displays it: '68'"],
        lister_count: 1,
        votes: [],
        final_status: 'excluded',
        exclusion_reason: 'citation_failed',
      },
      {
        id: 'S1',
        data_report: 'positioning',
        item_outlook: 'bearish',
        claim: 'The deal is not closed yet.',
        links: [{ ref: 'citation:2', value: null }],
        struck: false,
        problems: [],
        lister_count: 1,
        votes: [
          {
            role: 'checker',
            validity: 'valid',
            reason: 'Supported by the source.',
            links: [{ ref: 'citation:2', value: null }],
          },
        ],
        final_status: 'counted',
        exclusion_reason: null,
      },
    ],
    outlook: {
      outlook: 'neutral',
      summary: 'Only balanced evidence survived.',
      final_score: 5.0,
      initial_score: 3.33,
      pools: {
        initial: {
          data_reports: {
            technicals: { bullish: 1, bearish: 1, total: 2 },
            positioning: { bullish: 0, bearish: 1, total: 1 },
          },
          bullish: 1,
          bearish: 2,
          total: 3,
          score: 3.33,
        },
        final: {
          data_reports: {
            technicals: { bullish: 1, bearish: 0, total: 1 },
            positioning: { bullish: 0, bearish: 1, total: 1 },
          },
          bullish: 1,
          bearish: 1,
          total: 2,
          bullish_score_sum: 1,
          bearish_score_sum: 1,
          total_score_sum: 2,
          score: 5.0,
        },
      },
    },
    warnings: [],
  };
}

// The vote tree fetches its items when its fold opens (2026-09-21);
// here they come from the fixture's own record.
function renderResult(
  result: TieredResult,
  loader: (runId: string) => Promise<TieredVoteItem[]> = async () =>
    result.deep_analysis?.detail?.items ?? [],
) {
  render(
    <MemoryRouter>
      <UiLanguageProvider>
        <Report result={result} runId="task-9" debateItemsLoader={loader} />
      </UiLanguageProvider>
    </MemoryRouter>,
  );
}

// Open the vote tree's fold and wait for its items.
async function openTree() {
  fireEvent.click(screen.getByText(/Vote items|投票项/));
  await waitFor(() =>
    expect(screen.getByTestId('vote-tree').querySelector('[data-testid^="tree-item-"]')).not.toBeNull(),
  );
}

describe('Report', () => {
  it('makes the usage line itself the transcript toggle, with an exact token sum', () => {
    const withTranscript: TieredResult = {
      ...makeResult(),
      llm_usage: {
        stages: {},
        total: { calls: 28, input_tokens: 170000, output_tokens: 5049 },
        scope: 'tiered',
        transcript_entries: 28,
      },
    };
    renderResult(withTranscript);
    const toggle = screen.getByRole('button', { name: /28 .*175049/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    // No "~": the figure is a sum of exact per-call counts.
    expect(toggle.textContent).not.toContain('~');
    expect(toggle.textContent).not.toContain('约');
    // No second link under the line.
    expect(screen.queryByText(/View AI transcript|查看 AI 对话记录/)).not.toBeInTheDocument();
  });

  it('shows the usage line as plain text when the run kept no transcript', () => {
    const noTranscript: TieredResult = {
      ...makeResult(),
      llm_usage: {
        stages: {},
        total: { calls: 3, input_tokens: 100, output_tokens: 20 },
        scope: 'tiered',
      },
    };
    renderResult(noTranscript);
    expect(screen.getByText(/3 .*120/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /3 .*120/ })).not.toBeInTheDocument();
  });

  // Stopped runs (2026-10-19): the report holds only the sections that
  // finished, a banner names the step the stop landed in, and the plan
  // (and the action it decides) never shows.
  it('a run stopped during the data reports shows the finished cards and nothing else', () => {
    const result: TieredResult = {
      ...makeResult(),
      tier: 1,
      stopped_stage: 'positioning',
      data_reports: ['technicals', 'fundamentals'].map(makeDimension),
      outlook: undefined,
      action: undefined,
      deep_analysis: null,
      preliminary_analysis: null,
      levels: { entry: null, stop_loss: null, target: null },
      levels_detail: null,
      sizing: null,
      llm_usage: null,
    };
    renderResult(result);
    const banner = screen.getByTestId('stopped-banner');
    expect(banner).toHaveTextContent(/You stopped during Positioning\. Positioning did not finish and is not shown\.|仓位/);
    expect(screen.getByTestId('data-report-technicals')).toBeInTheDocument();
    expect(screen.getByTestId('data-report-fundamentals')).toBeInTheDocument();
    expect(screen.queryByTestId('data-report-positioning')).not.toBeInTheDocument();
    expect(screen.queryByTestId('preliminary-analysis')).not.toBeInTheDocument();
    expect(screen.queryByTestId('deep_analysis')).not.toBeInTheDocument();
    expect(screen.queryByTestId('plan')).not.toBeInTheDocument();
    expect(screen.queryByText(/初步分析|Preliminary analysis/)).not.toBeInTheDocument();
  });

  it('a running run shows the cards that landed and a skeleton where the next one goes', () => {
    const result: TieredResult = {
      ...makeResult(),
      tier: 1,
      running_stage: 'positioning',
      stages: ['technicals', 'fundamentals', 'positioning', 'macro_economy', 'preliminary_analysis', 'trade_plan'],
      data_reports: ['technicals', 'fundamentals'].map(makeDimension),
      outlook: undefined,
      action: undefined,
      deep_analysis: null,
      preliminary_analysis: null,
      levels: { entry: null, stop_loss: null, target: null },
      levels_detail: null,
      sizing: null,
      llm_usage: null,
    };
    renderResult(result);
    // The skeleton sits in the data-reports grid, after the finished
    // cards, named for the report on its way; no progress line.
    const skeleton = screen.getByTestId('skeleton-positioning');
    expect(skeleton).toHaveTextContent(/Positioning|仓位/);
    expect(skeleton).toHaveAttribute('aria-busy', 'true');
    // A numeric report: metric rows in two columns, like the real card.
    expect(screen.getByTestId('skeleton-positioning-columns')).toBeInTheDocument();
    expect(
      screen.getByTestId('data-report-fundamentals').compareDocumentPosition(skeleton) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.queryByText(/Working on|Still to come|正在进行|尚未开始/)).not.toBeInTheDocument();
    expect(screen.getByTestId('data-report-technicals')).toBeInTheDocument();
    expect(screen.getByTestId('data-report-fundamentals')).toBeInTheDocument();
    expect(screen.queryByTestId('data-report-positioning')).not.toBeInTheDocument();
    expect(screen.queryByTestId('preliminary-analysis')).not.toBeInTheDocument();
    expect(screen.queryByTestId('deep_analysis')).not.toBeInTheDocument();
    expect(screen.queryByTestId('plan')).not.toBeInTheDocument();
    expect(screen.queryByTestId('stopped-banner')).not.toBeInTheDocument();
  });

  it('a run fetching a news report shows a one-column skeleton', () => {
    const result: TieredResult = {
      ...makeResult(),
      tier: 1,
      running_stage: 'company_news',
      stages: ['technicals', 'company_news', 'preliminary_analysis', 'trade_plan'],
      data_reports: ['technicals'].map(makeDimension),
      outlook: undefined,
      action: undefined,
      deep_analysis: null,
      preliminary_analysis: null,
      levels_detail: null,
      sizing: null,
      llm_usage: null,
    };
    renderResult(result);
    expect(screen.getByTestId('skeleton-company_news')).toHaveTextContent(/Company news|公司新闻/);
    expect(screen.queryByTestId('skeleton-company_news-columns')).not.toBeInTheDocument();
  });

  it('a run working on its analysis shows the analysis block as a skeleton', () => {
    const result: TieredResult = {
      ...makeResult(),
      tier: 1,
      running_stage: 'preliminary_analysis',
      stages: ['technicals', 'preliminary_analysis', 'trade_plan'],
      data_reports: ['technicals'].map(makeDimension),
      outlook: undefined,
      action: undefined,
      deep_analysis: null,
      preliminary_analysis: null,
      levels_detail: null,
      sizing: null,
      llm_usage: null,
    };
    renderResult(result);
    expect(screen.getByText(/^Preliminary analysis$|^初步分析$/)).toBeInTheDocument();
    expect(screen.getByTestId('skeleton-preliminary_analysis')).toBeInTheDocument();
    expect(screen.queryByTestId('preliminary-analysis')).not.toBeInTheDocument();
    expect(screen.queryByTestId('plan')).not.toBeInTheDocument();
    expect(screen.queryByText(/^Trade plan$|^交易计划$/)).not.toBeInTheDocument();
  });

  it('a run working on its trade plan shows the finished analysis and a plan skeleton under it', () => {
    const result: TieredResult = {
      ...makeResult(),
      tier: 2,
      running_stage: 'trade_plan',
      stages: ['technicals', 'deep_analysis', 'trade_plan'],
      data_reports: ['technicals'].map(makeDimension),
      outlook: 'bullish',
      action: undefined,
      levels_detail: null,
      sizing: null,
      llm_usage: null,
    };
    renderResult(result);
    const analysis = screen.getByTestId('deep_analysis');
    const skeleton = screen.getByTestId('skeleton-trade_plan');
    expect(analysis.compareDocumentPosition(skeleton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText(/^Trade plan$|^交易计划$/)).toBeInTheDocument();
    expect(screen.queryByTestId('plan')).not.toBeInTheDocument();
    // The action waits for the plan review.
    expect(screen.queryByText(/Buy now|Buy later|No trade|现在买入|稍后买入|不交易/)).not.toBeInTheDocument();
  });

  it('a run stopped before any card finished says so and shows no data-reports block', () => {
    const result: TieredResult = {
      ...makeResult(),
      stopped_stage: 'technicals',
      data_reports: [],
      outlook: undefined,
      deep_analysis: null,
      levels_detail: null,
      sizing: null,
    };
    renderResult(result);
    expect(screen.getByTestId('stopped-banner')).toHaveTextContent(/Technicals did not finish|技术面/);
    expect(screen.queryByText(/数据报告|Data reports/)).not.toBeInTheDocument();
  });

  it('a run stopped at the trade plan keeps its analysis but shows no action and no plan', () => {
    // Stop was pressed during the deep analysis, which still finished;
    // the stop took effect at the trade plan.
    const result: TieredResult = {
      ...makeResult(),
      stopped_stage: 'deep_analysis',
      stopped_stage_finished: true,
      action: undefined,
      levels_detail: null,
      sizing: null,
    };
    renderResult(result);
    expect(screen.getByTestId('stopped-banner')).toHaveTextContent(
      /You stopped during Deep analysis\. Deep analysis finished and is shown\.|深度分析/,
    );
    expect(screen.getByTestId('deep_analysis')).toBeInTheDocument();
    expect(screen.getByText(/^(看多|Bullish)$/)).toBeInTheDocument();
    expect(screen.queryByText(/^(Action|操作)$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Buy now|Buy later|No trade|Re-run|立即买入|稍后买入/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('plan')).not.toBeInTheDocument();
  });

  it('keeps the blocks in the fixed order with their titles above the cards', () => {
    renderResult(makeResult());
    const wanted = ['data-report-technicals', 'deep_analysis', 'plan'];
    const ids = Array.from(document.querySelectorAll('[data-testid]'))
      .map((el) => el.getAttribute('data-testid') ?? '')
      .filter((id) => wanted.includes(id));
    expect(ids).toEqual(wanted);
    expect(screen.getByText(/数据报告|Data reports/)).toBeInTheDocument();
    // Card titles carry no tier prefix (owner decision 2026-07-21), and
    // the retired tier-1 and tier-3 cards never render.
    expect(screen.getByText(/^(深度分析|Deep analysis)$/)).toBeInTheDocument();
    expect(screen.queryByText(/初步分析|Preliminary analysis/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('preliminary-analysis')).not.toBeInTheDocument();
    expect(screen.queryByTestId('tier3')).not.toBeInTheDocument();
  });

  it('shows the plan levels as a computed/adjusted table', () => {
    renderResult(makeResult());
    // computed row on top, one clickable base per level — no backup
    // entry column anywhere (retired)
    expect(screen.getByTestId('level-computed-entry')).toHaveTextContent('95');
    expect(screen.queryByTestId('level-computed-secondary_entry')).not.toBeInTheDocument();
    expect(screen.getByTestId('level-computed-stop_loss')).toHaveTextContent('90');
    expect(screen.getByTestId('level-computed-target')).toHaveTextContent('105');
    // adjusted row: moved levels show the new number, untouched ones "keep"
    expect(screen.getByTestId('level-adjusted-entry')).toHaveTextContent('96');
    expect(screen.getByTestId('level-adjusted-target')).toHaveTextContent('108');
    expect(screen.getAllByTestId(/level-keep-/)).toHaveLength(1);
    // the old explainer texts around the levels are gone
    expect(screen.queryByText(/价格参考位|Price levels/)).not.toBeInTheDocument();
    expect(screen.queryByText(/资金管理|money-management/)).not.toBeInTheDocument();
  });

  it('clicking a computed level opens its formula with every number linked to a source', () => {
    window.localStorage.setItem('uiLanguage', 'en');
    renderResult(makeResult());
    fireEvent.click(screen.getByTestId('level-computed-stop_loss'));
    const dialog = screen.getByRole('dialog');
    // Title is two styled parts now: the subject, then the kind tag.
    expect(within(dialog).getByRole('heading')).toHaveTextContent(
      /(止损\s*公式|Stop loss\s*formula)/,
    );
    // the formula in words — report-exact variable names, never raw tokens
    expect(within(dialog).getByTestId('formula-words').textContent).toBe(
      'entry − 2 × 14d ATR',
    );
    // the entry came from the computed entry cell, the ATR from technicals
    expect(within(dialog).getByRole('button', { name: 'entry' })).toHaveTextContent('95');
    expect(within(dialog).getByRole('button', { name: '14d ATR' })).toHaveTextContent('2.50');
    expect(within(dialog).getByText('= 90')).toBeInTheDocument();
  });

  it('expands the prose input groups: pivot supports, nearest resistance', () => {
    window.localStorage.setItem('uiLanguage', 'en');
    const deep = makeResult();
    deep.levels_detail = {
      levels: {
        entry: {
          base: 170,
          formula: 'min(close, max(support candidates))',
          inputs: { close: 171, sma_50: 168, sma_200: 150, support_1: 169.5, round_level: 170 },
          adjusted: null, evidence: [], rejection: null, final: 170,
        },
        stop_loss: {
          base: 165.96,
          formula: 'ideal_entry − 2 × atr_14',
          inputs: { ideal_entry: 170, atr_14: 2.02, multiplier: 2 },
          adjusted: null, evidence: [], rejection: null, final: 165.96,
        },
        target: {
          base: 173.35,
          formula: 'min(ideal_entry + 2 × (ideal_entry − stop_loss), nearest overhead resistance)',
          inputs: {
            ideal_entry: 170, stop_loss: 165.96, geometric_target: 178.08,
            resistance_1: 173.35, high_1y: 180,
          },
          adjusted: null, evidence: [], rejection: null, final: 173.35,
        },
      },
      warnings: [],
    };
    renderResult(deep);

    fireEvent.click(screen.getByTestId('level-computed-entry'));
    let dialog = screen.getByRole('dialog');
    expect(within(dialog).getByTestId('formula-words').textContent).toBe(
      'min(Closing price, max(50d SMA, 200d SMA, Nearest support, Round level))',
    );
    expect(within(dialog).getByRole('button', { name: '50d SMA' })).toHaveTextContent('168');
    expect(within(dialog).getByRole('button', { name: 'Nearest support' })).toHaveTextContent(
      '169.50',
    );
    fireEvent.keyDown(window, { key: 'Escape' });

    fireEvent.click(screen.getByTestId('level-computed-target'));
    dialog = screen.getByRole('dialog');
    // the prose tail expands into the run's actual resistance inputs…
    expect(within(dialog).getByTestId('formula-words').textContent).toBe(
      'min(entry + 2 × (entry − stop loss), nearest of (Nearest resistance, 1y highest price))',
    );
    expect(within(dialog).queryByText(/overhead resistance/)).not.toBeInTheDocument();
    // …and each plugged number links to its technicals row
    expect(within(dialog).getByRole('button', { name: 'Nearest resistance' })).toHaveTextContent(
      '173.35',
    );
    expect(within(dialog).getByRole('button', { name: '1y highest price' })).toHaveTextContent(
      '180',
    );
    expect(within(dialog).getByText('= 173.35')).toBeInTheDocument();
  });

  it('clicking an adjusted level opens the AI reason with its references, nothing else', () => {
    renderResult(makeResult());
    fireEvent.click(screen.getByTestId('level-adjusted-entry'));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Momentum supports paying up a little.')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'technicals.sma_20' })).toBeInTheDocument();
    // the inputs table and the reference explainer were removed
    expect(within(dialog).queryByText(/^(输入项|Inputs)$/)).not.toBeInTheDocument();
  });


  it('renders no shares-computation card (retired 2026-07-22)', () => {
    renderResult(makeResult());
    expect(screen.queryByTestId('shares-computation')).not.toBeInTheDocument();
    expect(screen.queryByTestId('shares-formula')).not.toBeInTheDocument();
  });

  it('lists non-link sources above link sources under one Sources title', () => {
    const result = makeResult();
    result.data_reports[1].citations = [
      { source_name: 'SEC EDGAR', title: 'SEC EDGAR companyfacts', url: 'https://sec.gov/x', snippet: null },
      { source_name: 'Yahoo Finance summary (yfinance)', title: null, url: null, snippet: null },
    ];
    renderResult(result);
    const card = screen.getByTestId('data-report-fundamentals');
    expect(within(card).getByText(/^(来源|Sources)$/)).toBeInTheDocument();
    const items = within(card).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('Yahoo Finance summary (yfinance)');
    // link sources are listed as their URL, not their headline
    expect(items[1]).toHaveTextContent('https://sec.gov/x');
    expect(items[1]).not.toHaveTextContent('SEC EDGAR companyfacts');
  });

  it('inlines each macro observation date beside its value, keeping the date anchor', () => {
    const result = makeResult();
    result.data_reports[2].payload = {
      region: 'us',
      as_of: '2026-07-24',
      markets: { vix: 16.64 },
      observation_dates: { vix: '2026-07-22' },
    };
    renderResult(result);
    // The value row carries its date, and the date keeps the citable
    // anchor id (macro_economy.observation_dates.vix) evidence links jump to
    // — the dates group no longer renders as a section of its own.
    const row = document.getElementById('tiered-metric-macro_economy-markets-vix');
    // Dates render in the page's slashed style (owner request 2026-08-16).
    expect(row).toHaveTextContent('16.64 2026/07/22');
    const date = document.getElementById('tiered-metric-macro_economy-observation_dates-vix');
    expect(date).toHaveTextContent('2026/07/22');
    expect(row?.contains(date)).toBe(true);
  });

  it('renders a v2 envelope payload as one row per metric with group titles', () => {
    const result = makeResult();
    // technicals v2 (2026-07-27): nested groups of {name, explanation,
    // value} envelopes.
    result.data_reports[0].payload = {
      price: {
        close: { name: 'closing price', explanation: 'anchor', value: 157.79 },
      },
      daily: {
        trend: { name: 'daily trend', explanation: 'combined', value: 'bullish' },
        rsi_14: { name: 'RSI (14d)', explanation: 'momentum', value: 61.42 },
      },
    };
    renderResult(result);
    const card = screen.getByTestId('data-report-technicals');
    // One row per envelope, unwrapped to its value — the prose keys
    // (name/explanation) must not render as rows of their own.
    const close = document.getElementById('tiered-metric-technicals-price-close');
    expect(close).toHaveTextContent('157.79');
    const trend = document.getElementById('tiered-metric-technicals-daily-trend');
    expect(trend).toHaveTextContent('bullish');
    expect(within(card).queryByText('anchor')).not.toBeInTheDocument();
    expect(within(card).queryByText('combined')).not.toBeInTheDocument();
    // Group keys become section titles via the metric vocabulary.
    expect(within(card).getByText(/股票价格|Stock price/)).toBeInTheDocument();
    expect(within(card).getByText(/日线时间框架|Daily timeframe/)).toBeInTheDocument();
    // No Other bucket: every v2 group renders under its own name.
    expect(within(card).queryByText(/^(其他|Other)$/)).not.toBeInTheDocument();
  });

  it('tucks data notes behind an exclamation mark that opens a plain-English modal', () => {
    const result = {
      ...makeResult(),
      warnings: [
        'judge summary unparseable — computed outlook stands',
        'some brand-new warning shape the frontend has never seen',
      ],
    };
    renderResult(result);
    // Nothing inline — the notes only exist behind the mark.
    expect(screen.queryByText(/judge summary unparseable/)).not.toBeInTheDocument();
    fireEvent.click(within(screen.getByTestId('deep_analysis')).getByTestId('warnings-button'));
    // Known shape → fixed keyword + friendly sentence; the raw backend
    // text is no longer shown (owner decision 2026-07-24).
    expect(screen.getByText(/Unusable LLM reply|LLM 回复无效/)).toBeInTheDocument();
    expect(screen.queryByText(/judge summary unparseable/)).not.toBeInTheDocument();
    // Unknown shape → raw text unchanged under the generic keyword.
    expect(
      screen.getByText('some brand-new warning shape the frontend has never seen'),
    ).toBeInTheDocument();
  });
});

describe('Report evidence vote tree', () => {
  async function renderTreeV9() {
    const deep = makeResult();
    deep.deep_analysis!.detail = makeTreeDebateV9();
    deep.deep_analysis!.summary = 'Only balanced evidence survived.';
    renderResult(deep);
    await openTree();
  }

  it('fetches the items the first time the fold opens, and says so if that fails', async () => {
    const deep = makeResult();
    const loader = vi.fn().mockResolvedValue(makeTreeDebateV9().items);
    renderResult(deep, loader);
    expect(loader).not.toHaveBeenCalled();
    expect(screen.queryByTestId('tree-item-T1')).not.toBeInTheDocument();
    await openTree();
    expect(loader).toHaveBeenCalledTimes(1);
    expect(loader).toHaveBeenCalledWith('task-9');
    // Closing and reopening does not fetch again.
    fireEvent.click(screen.getByText(/Vote items|投票项/));
    fireEvent.click(screen.getByText(/Vote items|投票项/));
    expect(loader).toHaveBeenCalledTimes(1);

    cleanup();
    renderResult(deep, vi.fn().mockRejectedValue(new Error('network down')));
    fireEvent.click(screen.getByText(/Vote items|投票项/));
    await waitFor(() => expect(screen.getByText(/network down/)).toBeInTheDocument());
  });

  it('tucks the whole vote record into a Transcript foldable with the how-it-works list on top', async () => {
    await renderTreeV9();
    expect(screen.getByText(/Vote items|投票项/)).toBeInTheDocument();
    const explain = screen.getByTestId('tree-explain');
    expect(explain).toHaveTextContent(/How this works|规则说明/);
    // The list explains that mark-less vote items came from both AIs.
    expect(explain).toHaveTextContent(/carries no check marks|没有任何检查标记/);
    expect(explain).toHaveTextContent(/deciding vote|决胜票/);
  });

  it('shows colored item-outlook words and counts them in the section headers', async () => {
    await renderTreeV9();
    const t1 = screen.getByTestId('tree-item-T1');
    expect(within(t1).getByText(/bullish|看多/)).toHaveClass('text-positive');
    const t2 = screen.getByTestId('tree-item-T2');
    expect(within(t2).getByText(/bearish|看空/)).toHaveClass('text-negative');
    // Headers count only the surviving vote items: technicals 1 bullish, 0 bearish.
    expect(screen.getByTestId('vote-tree')).toHaveTextContent(/1 bullish, 0 bearish|1 看多, 0 看空/);
  });

  it('a vote item from both listers carries no marks; single-lister vote items carry ✓/✗ marks', async () => {
    await renderTreeV9();
    expect(
      within(screen.getByTestId('tree-item-T1')).queryAllByRole('button', { name: /✓|✗/ }),
    ).toHaveLength(0);
    expect(
      within(screen.getByTestId('tree-item-T2')).getAllByRole('button', { name: '✗' }),
    ).toHaveLength(2);
    expect(
      within(screen.getByTestId('tree-item-S1')).getByRole('button', { name: '✓' }),
    ).toBeInTheDocument();
  });

  it('clicking the code ✗ on a struck vote item shows the citation errors', async () => {
    await renderTreeV9();
    fireEvent.click(
      within(screen.getByTestId('tree-item-T3')).getByRole('button', { name: '✗' }),
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent(/code check result|代码检查结果/);
    expect(dialog).toHaveTextContent('must be copied exactly');
  });

  it('crosses out every vote item that is not in the final score, with no pills or steps', async () => {
    await renderTreeV9();
    expect(
      screen.getByTestId('tree-item-T2').querySelector('.line-through'),
    ).not.toBeNull();
    expect(
      screen.getByTestId('tree-item-T3').querySelector('.line-through'),
    ).not.toBeNull();
    expect(
      screen.getByTestId('tree-item-T1').querySelector('.line-through'),
    ).toBeNull();
    expect(screen.queryByTestId('tree-step-1')).not.toBeInTheDocument();
    expect(screen.queryByText(/^counted$|^excluded$/)).not.toBeInTheDocument();
  });

  it('opens the flat formula from the header score; no outlook-bands block', async () => {
    await renderTreeV9();
    // The arithmetic no longer sits inside the transcript fold.
    expect(screen.queryByTestId('tree-scores')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('deep-analysis-score'));
    const scores = screen.getByTestId('tree-scores');
    expect(scores).toHaveTextContent(/final outlook score: |最终展望分: /);
    expect(screen.getByTestId('tree-final-formula')).toHaveTextContent('= 10 × 1 / 2');
    expect(scores).toHaveTextContent('= 5.00');
    expect(scores).not.toHaveTextContent(/below 4 sell|低于 4 卖出/);
    expect(screen.queryByTestId('tree-outlook')).not.toBeInTheDocument();
  });

  it('wraps long claims with a hanging indent (two-column grid rows)', async () => {
    await renderTreeV9();
    expect(screen.getByTestId('tree-item-T1').className).toContain('grid');
  });
});

// The format-2 risk vote: T1 confirmed by both AIs, T2 outvoted 1-2,
// P1 (plan group) confirmed by a ✓ check vote, S1 struck by code.
