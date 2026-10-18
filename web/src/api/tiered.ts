import apiClient from './index';
import type { UiLanguage } from '../i18n/uiText';

// Types mirror the backend JSON verbatim (snake_case). DataReport payloads
// hold metric names like revenue_yoy_pct — do not camelize them.
export type TieredCitation = {
  source_name: string;
  url: string | null;
  title: string | null;
  snippet: string | null;
};

// Technicals v2 UI receipt (2026-07-28): how a derived payload metric was
// computed, keyed by "group.key" (e.g. "daily.rsi_14"). One-outcome
// formulas carry a `formula` string; rules with several possible outcomes
// carry `branches` — one {label, condition} line per outcome, the
// catch-all with condition null. The plugged-line style is told apart by
// inspecting the words: every input token appears → substitution (numbers
// plug in place); tokens absent → listed ("ingredient = value" pairs —
// rules whose ingredients are words, like ma_stack = up); empty inputs →
// words-only (aggregates over a whole series).
export type TieredMetricBranch = {
  label: string;
  /** null = the catch-all ("else") branch. */
  condition: string | null;
};

export type TieredMetricFormula = {
  formula?: string | null;
  branches?: TieredMetricBranch[] | null;
  inputs: Record<string, number | string>;
};

export type TieredDataReport = {
  /** Which report this is: technicals, fundamentals, positioning, macro_economy, company_news, world_news. */
  name: string;
  kind: 'numeric' | 'textual';
  counted: boolean;
  payload: Record<string, unknown> | null;
  /** Computation receipts keyed "group.key". Technicals ships them from
      2026-07-27, fundamentals from 2026-07-29; absent on the other
      data_reports and on old stored runs. */
  formulas?: Record<string, TieredMetricFormula> | null;
  summary: string | null;
  warnings: string[];
  /** The same warnings as `warnings`, keyed by the payload field
      ("group.key") each is about (2026-08-05). A warning absent from
      this map has no field to live on and stays a card-level warning.
      Absent on old stored runs. */
  field_warnings?: Record<string, string[]> | null;
  citations: TieredCitation[];
};

export type TieredLevels = {
  entry: number | null;
  stop_loss: number | null;
  target: number | null;
};

// v2 slice 3 audit trail: per-level formula base + validated AI adjustment.
// The plan-review redesign (2026-07-22) adds a "shares" entry in the same
// shape (base = count from the computed levels; adjusted_inputs = the
// final levels a mechanical recompute used).
// One adjustment reason: the flagged check it fixes (a fixed keyword id
// the UI translates) plus one cited sentence.
export type TieredLevelReason = {
  check: string;
  text: string;
  links?: TieredCitationLink[];
};

export type TieredLevelDetail = {
  base: number | null;
  formula: string | null;
  inputs: Record<string, number> | null;
  adjusted: number | null;
  reasons?: TieredLevelReason[] | null;
  evidence: string[];
  adjusted_inputs?: Record<string, number> | null;
  /** Shares only: the mechanical recompute from the adjusted levels,
   *  before any AI trim — the receipt's result line. */
  mechanical?: number | null;
  rejection: string | null;
  final: number | null;
};

// One round of the check-adjust cycle that ended with a risk check still
// firing. Present (non-empty) only when the review never converged and
// the computed plan was kept — the UI words it in the blue-keep modal.
export type TieredReviewFailure = {
  round: number;
  checks: string[];
};

export type TieredLevelsDetail = {
  levels: Record<string, TieredLevelDetail>;
  warnings: string[];
  review_failures?: TieredReviewFailure[] | null;
};

// One structured trade-plan warning: numbers only, the frontend words it.
export type TieredPlanWarning = {
  id: string;
  values: Record<string, unknown>;
};

// Per-column warning lists for the plan table's Warnings row.
export type TieredPlanWarnings = Record<string, TieredPlanWarning[]>;

// v4 judge grade for one validity axis: the 0-5 score plus, below 5, the
// exact offending sentence and why it is wrong (both null at 5/5 → N/A).
export type TieredAxisGrade = {
  score: number;
  quote?: string | null;
  why?: string | null;
};

// --- the vote tree (listers, checkers, the deciding vote) ---

// Inline citation. v6: text = the words underlined in the claim, value =
// the claimed number (mismatch marks a code-detected contradiction).
// v7: payload links carry value (the report's display string; the claim
// contains it verbatim) with text null; sentiment links carry text (the
// words resting on that news source) with value null.
export type TieredCitationLink = {
  text?: string | null;
  ref: string;
  value: number | string | null;
  mismatch?: boolean;
};

// One v8 vote on a vote item: the check round's second vote or the
// deciding round's tiebreaker. Reasons carry the same code-verified
// links the vote items use. v10 votes carry the voter's own importance
// rating of the vote item (1-3; 1-5 since v11); v11 adds one plain
// sentence saying why (score_reason).
export type TieredVote = {
  role: 'checker' | 'decider';
  validity: 'valid' | 'invalid';
  reason: string | null;
  links: TieredCitationLink[];
  score?: number;
  score_reason?: string | null;
};

// v11: one lister's own rating of a vote item they listed — which lister
// (1 or 2), the 1-5 importance score, and why.
export type TieredListerVote = {
  lister: number;
  score: number;
  score_reason?: string | null;
};

// One evidence item of the vote tree with everything that happened to it.
export type TieredVoteItem = {
  id: string;
  data_report: string;
  // Which way this one vote item leans; the run's outlook is counted from these.
  item_outlook: 'bullish' | 'bearish';
  claim: string;
  links?: TieredCitationLink[];
  struck?: boolean;
  problems?: string[];
  // How many listers listed it independently (2 = confirmed at birth).
  lister_count?: number;
  votes?: TieredVote[];
  // v10 weighted votes: the listers' own ratings (one or two), and the
  // final median of every voter's rating (null on struck vote items).
  // v11 adds lister_votes: the same ratings with the lister number and
  // the reason attached.
  lister_scores?: number[];
  lister_votes?: TieredListerVote[];
  score?: number | null;
  final_status?: 'counted' | 'excluded' | null;
  exclusion_reason?: string | null;
};

// Pool snapshot: per-data_report bullish/bearish counts plus the
// pool-wide totals and score. v6-v8 store a per-data_report score and an
// averaged overall score; v9 stores flat counting (10 × bullish/total)
// and no per-data_report score; v10 adds importance-score sums and a
// weighted score (10 × bullish score / total score).
export type TieredVotePool = {
  data_reports: Record<
    string,
    {
      bullish: number;
      bearish: number;
      total: number;
      score?: number | null;
      bullish_score_sum?: number;
      bearish_score_sum?: number;
      total_score_sum?: number;
    }
  >;
  bullish: number;
  bearish: number;
  total: number;
  bullish_score_sum?: number;
  bearish_score_sum?: number;
  total_score_sum?: number;
  score: number | null;
};

// Bull/bear deep analysis audit trail (tier-2 section). Four generations coexist
// in stored runs: the v2 judged shape (confidence, reasons, would_change_
// One bullet of the structured deep-analysis summary outline. Bullets carry the
// same code-verified {ref, value} links as the evidence list — cited
// values render as jumps to their report row. Children are sub-bullets
// one level deep with the same contract.
export type TieredSummaryChild = {
  text: string;
  links?: TieredCitationLink[] | null;
};
export type TieredSummaryBullet = {
  text: string;
  links?: TieredCitationLink[] | null;
  children?: TieredSummaryChild[] | null;
};

// The fixed report outline (owner decision 2026-07-24): the group set
// and order never change run to run — the AI only fills the bullets.
export type TieredSummaryStructure = {
  summary?: TieredSummaryBullet[] | null;
  technicals?: TieredSummaryBullet[] | null;
  fundamentals?: TieredSummaryBullet[] | null;
  positioning?: TieredSummaryBullet[] | null;
  macro_economy?: TieredSummaryBullet[] | null;
  // Company news joined the deep analysis 2026-08-16; absent on older runs.
  company_news?: TieredSummaryBullet[] | null;
  // World news (macro backdrop card) joined the same day; absent on
  // older runs.
  world_news?: TieredSummaryBullet[] | null;
};

// mind), the v3 scored shape (final_score, scoring, corrected bull/bear
// summaries), the v4 threaded shape (turn kinds, axis-grade comments),
// and the v5 tree (format: 5, items, score ledger) — every
// generation-specific field is optional.
export type TieredDeepAnalysisDetail = {
  // 5/6/7 on tree-format runs; absent on everything stored before.
  format?: number;
  // The server serves the record as an overview (2026-09-21): the items
  // are never in it — they are paged at GET /runs/{id}/vote_items —
  // only their count. `items` remains for a caller that already holds
  // the whole stored record.
  items?: TieredVoteItem[];
  item_count?: number;
  outlook: {
    outlook: TieredOutlook;
    summary: string;
    // The fixed-outline report the summary stage fills (summary + one
    // group per data_report); `summary` above is its flat-text rendering.
    summary_structure?: TieredSummaryStructure | null;
    final_score?: number | null;
    initial_score?: number | null;
    pools?: {
      initial: TieredVotePool;
      adjusted?: TieredVotePool;
      final: TieredVotePool;
    } | null;
  } | null;
  warnings: string[];
};

export type TieredOutlook = 'bullish' | 'neutral' | 'bearish' | 'no_outlook';
export type TieredAction = 'buy_now' | 'buy_later' | 'no_trade' | 'unknown';
export type TieredEarnings = {
  next_date: string | null;
  days_until: number | null;
  warning_days: number;
  is_near: boolean;
  note: string | null;
};

// The deepest tier's outlook in summary form — what the run ends on.
export type TieredFinal = {
  tier: number;
  outlook: TieredOutlook;
  action?: TieredAction;
  confidence: string | null;
  levels: TieredLevels;
};

export type TieredTierSection = {
  tier: number;
  outlook: TieredOutlook;
  confidence: string | null;
  score: number | null;
  levels: TieredLevels;
  summary: string | null;
  warnings: string[];
  detail?: TieredDeepAnalysisDetail;
};

// v2 slice 6: deterministic sizing block (share count or explicit refusal).
export type TieredSizing = {
  enabled: boolean;
  shares: number | null;
  position_value: number | null;
  risk_amount: number | null;
  loss_per_share: number | null;
  lot_size: number;
  reason_code: string | null;
  refusal_reason: string | null;
  warnings: string[];
  // Fee rate and the position cap were removed 2026-07-22 (they return
  // later as user inputs); old stored runs may still carry those keys.
  inputs: {
    capital: number | null;
    risk_pct: number | null;
    // Absent on runs stored before the reward filter existed.
    reward_ratio?: number | null;
    entry: number | null;
    stop_loss: number | null;
  };
};

export type TieredLlmUsage = {
  stages: Record<string, { calls: number; input_tokens: number; output_tokens: number }>;
  total: { calls: number; input_tokens: number; output_tokens: number };
  scope: string;
  // How many LLM exchanges the run's stored transcript holds (absent on
  // runs that made no call, and on runs stored before transcripts).
  transcript_entries?: number | null;
};

// Everything about one LLM call of a run except its text, in the
// transcript's own words: call_number, stage, llm, time, tokens.
export type TieredTranscriptCallFacts = {
  call_number: number;
  created_at: string | null;
  stage: string | null;
  llm: string | null;
  temperature: number | null;
  time_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  structured: string | null;
  error: string | null;
};

// One row of the transcript index (GET /runs/{run_id}/transcript): the
// facts plus how big the input and output are, so a reader can decide
// whether to open them. The text is one more call away.
export type TieredTranscriptCallSummary = TieredTranscriptCallFacts & {
  input_chars: number;
  output_chars: number;
};

// One call with its text (GET /runs/{run_id}/transcript/{call_number}).
export type TieredTranscriptCall = TieredTranscriptCallFacts & {
  input: string | null;
  output: string | null;
};

// One light row per data report, on every report whatever sections
// were asked for (2026-09-21): which reports exist and which went wrong,
// without the reports themselves.
export type TieredDataReportIndexEntry = {
  name: string;
  kind: string | null;
  counted: boolean;
  warnings: string[];
};

// The preliminary analysis's record on a tier-1 run: its 0-10 score.
export type TieredPreliminaryAnalysis = {
  format?: string;
  outlook?: { outlook: TieredOutlook; final_score: number } | null;
};

export type TieredResult = {
  ticker: string;
  market: string;
  // The tier the run was asked for: 1 (preliminary analysis) or 2 (deep analysis).
  tier: number;
  score: number | null;
  confidence: string | null;
  levels: TieredLevels;
  levels_detail?: TieredLevelsDetail | null;
  summary: string | null;
  warnings: string[];
  data_reports: TieredDataReport[];
  // Tier-1 runs: the preliminary analysis's record; null on tier-2 runs.
  preliminary_analysis?: TieredPreliminaryAnalysis | null;
  final?: TieredFinal | null;
  // Tier-2 runs: the deep-analysis section; null on tier-1 runs.
  deep_analysis?: TieredTierSection | null;
  sizing?: TieredSizing | null;
  llm_usage?: TieredLlmUsage | null;
  // Outlook redesign additions — absent on old stored runs.
  outlook?: TieredOutlook;
  action?: TieredAction;
  earnings?: TieredEarnings | null;
  // Plan review (2026-07-22): per-column trade-plan warnings.
  plan_warnings?: TieredPlanWarnings | null;
  // Max hold time in weeks the run was judged against (2026-08-08);
  // absent on old stored runs.
  max_hold_weeks?: number | null;
  data_report_index?: TieredDataReportIndexEntry[];
  // Stopped runs only (2026-10-19): the step that was running when the
  // user pressed stop — a data report's name, preliminary_analysis,
  // deep_analysis or trade_plan — and whether that step still finished
  // (a stop takes effect at the next checkpoint, so a quick card or a
  // one-call analysis may complete and be shown). The report holds only
  // the sections that finished: data_reports is partial, the analysis
  // is there when it finished, the plan (and the action it decides)
  // never is.
  stopped_stage?: string | null;
  stopped_stage_finished?: boolean;
};

// queued (2026-09-15): waiting for a free slot in the server's global run
// queue; it becomes running by itself. stopped (2026-10-19): the user
// stopped it part-way; its report holds what finished.
export type TieredRunStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'stopped';

// A history row speaks the run form's own words and order (2026-09-24):
// ticker, capital, risk_pct, reward_ratio, max_hold_weeks, tier — the
// same names the request takes (TieredRunRequest).
export type TieredRunSummary = {
  run_id: string;
  ticker: string;
  status: TieredRunStatus;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
  // Queued rows only: the run's place in the line, from 1.
  queue_position?: number | null;
  // The run's inputs, known from the moment it is created; null on runs
  // stored before a field existed. Capital is in the ticker's own
  // currency; risk is the percent the user typed (1 = 1%).
  capital?: number | null;
  risk_pct?: number | null;
  // The reward-to-risk goal the run planned toward (target = entry +
  // ratio × risk).
  reward_ratio?: number | null;
  // Max hold time in weeks the run was judged against.
  max_hold_weeks?: number | null;
  tier?: number | null;
  // Set once the run is done: shares mirrors the report card, 0 = sizing
  // ran but bought nothing, null = no sizing block (shown as a dash).
  outlook?: TieredOutlook | null;
  shares?: number | null;
};

// The parts of a stored report GET /runs/{run_id} can return
// (2026-09-21). `core` is the light headline and always comes back;
// `data_reports` (the data reports), `deep_analysis` (the deep-analysis record)
// and `plan` (the trade-plan receipt) are the heavy parts.
export type TieredReportSection = 'core' | 'data_reports' | 'deep_analysis' | 'plan';

export type TieredRun = TieredRunSummary & {
  // Which sections `result` holds.
  sections: TieredReportSection[];
  result: TieredResult | null;
};

// The run-list filters as the server takes them (GET /runs). Every
// field is optional and they combine with AND; a list matches any of
// its values. Ranges are inclusive and named after the row's fields;
// risk is a percent (1 = 1%), as typed; dates are ISO instants (after
// inclusive, before exclusive).
export type TieredRunListQuery = {
  ticker?: string[];
  status?: string[];
  outlook?: string[];
  capital_min?: number;
  capital_max?: number;
  risk_pct_min?: number;
  risk_pct_max?: number;
  reward_ratio_min?: number;
  reward_ratio_max?: number;
  max_hold_weeks?: number[];
  tier?: number[];
  created_after?: string;
  created_before?: string;
  page?: number;
  page_size?: number;
};

// One page of the run history, newest first.
export type TieredRunPage = {
  items: TieredRunSummary[];
  page: number;
  page_size: number;
  // Every match, not just this page.
  total: number;
  page_count: number;
};

// DELETE /runs/{id}: what the run was. `queued` means it was cancelled
// before it started.
export type TieredRunDeleted = {
  run_id: string;
  ticker: string;
  status: 'queued' | 'succeeded' | 'failed' | 'stopped';
};

// GET /runs/{id}/vote_items: one page of a deep run's vote items.
export type TieredVoteItemStatus = 'counted' | 'excluded';

export type TieredVoteItemQuery = {
  data_report?: string[];
  status?: TieredVoteItemStatus[];
  page?: number;
  page_size?: number;
};

export type TieredVoteItemPage = {
  items: TieredVoteItem[];
  page: number;
  page_size: number;
  total: number;
  page_count: number;
};

// The most vote items one page may hold (the server's cap).
export const VOTE_ITEMS_PAGE_MAX = 200;

// POST /runs/{run_id}/stop: the run's stop flag is up; it stays running
// until its current step finishes, then lands as stopped.
export type TieredRunStopRequested = {
  run_id: string;
  ticker: string;
};

// GET /status: what the server can do right now (2026-09-21).
export type TieredMarketClock = {
  market: string;
  timezone: string;
  local_time: string;
  session_open: string | null;
  session_close: string | null;
  runs_blocked: boolean;
  runs_allowed_from: string | null;
};

export type TieredServerStatus = {
  server_time: string;
  llm: { main_model: string | null; sub_model: string | null; api_key_set: boolean };
  data_sources: { finnhub: boolean; alphavantage: boolean; fred: boolean; sec_edgar: boolean };
  runs: { max_concurrent: number; running: number; queued: number };
  // What a run uses when a field is left out, in the form's order.
  defaults: {
    capital: number | null;
    risk_pct: number | null;
    reward_ratio: number;
    max_hold_weeks: number;
    tier: number;
  };
  transcript_retention_days: number;
  markets: TieredMarketClock[];
};

// The tiers a run can be asked for: 1 = preliminary analysis, 2 = deep
// analysis. Tier 3 is retired (outlook redesign).
export type TieredTier = 1 | 2;

// POST /analyze: the run form, field for field, in its order. The
// server fills the form defaults for whatever is left out. Risk is the
// percent the user typed (1 = 1%); run_anyway is the market-open-check override
// ("run anyway" after a 409 market-open rejection).
export type TieredRunRequest = {
  ticker: string;
  capital?: number;
  risk_pct?: number;
  reward_ratio?: number;
  max_hold_weeks?: number;
  tier?: TieredTier;
  run_anyway?: boolean;
  // The language the user chose for the app (2026-09-26): every
  // sentence the model writes for the report is in it. Left out, the
  // server runs in English.
  language?: UiLanguage;
};

export type TieredRunAccepted = {
  run_id: string;
  ticker: string;
  tier: number;
  status: TieredRunStatus;
};

// The 409 market-open rejection body (2026-08-11): which market blocked
// the run, plus today's session bounds as ISO datetimes carrying the
// market's own UTC offset (null on backends from before they were sent).
export type TieredMarketOpenGate = {
  market: string | null;
  sessionOpen: string | null;
  sessionClose: string | null;
};

// The 409 duplicate-run rejection body (2026-09-15): an unfinished run
// with the same ticker and inputs — the Start popup names it and the
// history expands it.
export type TieredDuplicateRun = {
  runId: string;
  status: 'queued' | 'running';
};

export const tieredApi = {
  // The request is the form's own fields, name for name (2026-09-24).
  start: async (request: TieredRunRequest): Promise<TieredRunAccepted> => {
    const response = await apiClient.post<TieredRunAccepted>('/api/v1/tiered/analyze', request);
    return response.data;
  },

  // One page of the history, filtered by the server. Repeated params
  // are sent as ?ticker=A&ticker=B (no [] suffix), as the backend reads them.
  listRuns: async (query: TieredRunListQuery = {}): Promise<TieredRunPage> => {
    const response = await apiClient.get<TieredRunPage>('/api/v1/tiered/runs', {
      params: query,
      paramsSerializer: { indexes: null },
    });
    return response.data;
  },

  // Every ticker ever run, A-Z — the ticker filter's choices.
  listTickers: async (): Promise<string[]> => {
    const response = await apiClient.get<{ items: string[] }>('/api/v1/tiered/runs/tickers');
    return response.data.items;
  },

  // One run with its report, whole (no sections named) or by section.
  getRun: async (runId: string, sections?: TieredReportSection[]): Promise<TieredRun> => {
    const response = await apiClient.get<TieredRun>(`/api/v1/tiered/runs/${runId}`, {
      params: sections && sections.length > 0 ? { section: sections } : undefined,
      paramsSerializer: { indexes: null },
    });
    return response.data;
  },

  // The run's LLM calls without their text (the index is small; the
  // text of every call together runs to half a megabyte).
  getTranscript: async (runId: string): Promise<TieredTranscriptCallSummary[]> => {
    const response = await apiClient.get<{ items: TieredTranscriptCallSummary[] }>(
      `/api/v1/tiered/runs/${runId}/transcript`,
    );
    return response.data.items;
  },

  // One call with its full input (the prompt) and raw output (the reply).
  getTranscriptCall: async (runId: string, callNumber: number): Promise<TieredTranscriptCall> => {
    const response = await apiClient.get<TieredTranscriptCall>(
      `/api/v1/tiered/runs/${runId}/transcript/${callNumber}`,
    );
    return response.data;
  },

  // One page of a deep run's vote items, filtered by the server.
  getVoteItems: async (
    runId: string,
    query: TieredVoteItemQuery = {},
  ): Promise<TieredVoteItemPage> => {
    const response = await apiClient.get<TieredVoteItemPage>(
      `/api/v1/tiered/runs/${runId}/vote_items`,
      { params: query, paramsSerializer: { indexes: null } },
    );
    return response.data;
  },

  // Every vote item of a deep run, in stored order — the vote tree shows
  // them all at once, so it pages through at the largest page size.
  getAllVoteItems: async (runId: string): Promise<TieredVoteItem[]> => {
    const first = await tieredApi.getVoteItems(runId, { page_size: VOTE_ITEMS_PAGE_MAX });
    const rest = await Promise.all(
      Array.from({ length: first.page_count - 1 }, (_, index) =>
        tieredApi.getVoteItems(runId, { page: index + 2, page_size: VOTE_ITEMS_PAGE_MAX }),
      ),
    );
    return [first, ...rest].flatMap((page) => page.items);
  },

  // Delete a run and its transcript; a queued run is thereby cancelled.
  // A running run is refused with a 409 whose detail.code is
  // run_in_progress.
  deleteRun: async (runId: string): Promise<TieredRunDeleted> => {
    const response = await apiClient.delete<TieredRunDeleted>(`/api/v1/tiered/runs/${runId}`);
    return response.data;
  },

  // Stop a running run part-way. The run ends at its next checkpoint
  // (a model call in flight finishes and counts) and lands as stopped
  // with the sections that finished. A run that is not running is
  // refused with a 409 whose detail.code is run_not_running.
  stopRun: async (runId: string): Promise<TieredRunStopRequested> => {
    const response = await apiClient.post<TieredRunStopRequested>(
      `/api/v1/tiered/runs/${runId}/stop`,
    );
    return response.data;
  },

  // What the server can do right now: model, data sources, run slots,
  // defaults, and each market's clock.
  getStatus: async (): Promise<TieredServerStatus> => {
    const response = await apiClient.get<TieredServerStatus>('/api/v1/tiered/status');
    return response.data;
  },
};
