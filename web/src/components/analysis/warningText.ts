import { metricEntry } from '../../i18n/metricLabels';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';

// The backend records its warnings as engineer-speak ("unparseable
// level ideal_buy=…"). Each known shape is matched here and rewritten as a
// plain-English sentence via an i18n key, led by a fixed keyword — chosen
// per rule from the closed list below (owner decision 2026-07-24), never
// generated, mirroring the plan-warnings modal's id → keyword map. Unknown
// shapes keep their raw text (never invent a friendly sentence we can't
// back up) under the generic "Warning" keyword, so every note leads
// with a keyword (owner request 2026-08-09; "data note" renamed to
// "warning" everywhere, owner request 2026-08-25).

type Translate = (key: UiTextKey, params?: Record<string, string | number>) => string;

// The closed keyword list. Every note leads with one of these.
const KEY = {
  missingData: 'tiered.warning.key.missingData',
  fetchFailed: 'tiered.warning.key.fetchFailed',
  citations: 'tiered.warning.key.citations',
  aiReply: 'tiered.warning.key.aiReply',
  levels: 'tiered.warning.key.levels',
  outlook: 'tiered.warning.key.outlook',
  vote: 'tiered.warning.key.vote',
  debate: 'tiered.warning.key.deepAnalysis',
  riskCheck: 'tiered.warning.key.riskCheck',
  settings: 'tiered.warning.key.settings',
  newsCap: 'tiered.warning.key.newsCap',
  // The fallback for note shapes no rule recognizes.
  other: 'tiered.warning.key.other',
  // The plan card's warnings row shows these same facts under these same
  // keywords — the notes list must not word them differently.
  rewardRatio: 'tiered.warnKey.reward_below_goal',
  downtrend: 'tiered.warnKey.downtrend',
} as const satisfies Record<string, UiTextKey>;

// Level keys as they appear in adjustment warnings ("adjustment for entry …").
const LEVEL_LABEL_KEYS: Record<string, UiTextKey> = {
  entry: 'tiered.levels.entry',
  shares: 'tiered.levels.shares',
  stop_loss: 'tiered.levels.stopLoss',
  target: 'tiered.levels.target',
};

function hostOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

// Backend stage names → the role labels the vote tree already uses
// (owner request 2026-08-05: retry/invalid notes lead with the AI's
// role). Unknown stages fall back to the raw stage
// text — never invent a label.
const STAGE_ROLES: Record<string, (t: Translate) => string> = {
  'lister 1 grade sheet': (t) => t('tiered.tree.lister', { n: 1 }),
  'lister 2 grade sheet': (t) => t('tiered.tree.lister', { n: 2 }),
  'check round': (t) => t('tiered.role.checkRound'),
  'deciding round': (t) => t('tiered.role.decidingRound'),
  'report outline': (t) => t('tiered.role.reportOutline'),
  // News-screen stages can retry since 2026-08-25 (structured output
  // + pydantic-checked retry) and report through the same generic
  // "<stage> needed a retry" note.
  'news judge': (t) => t('tiered.role.newsJudge'),
  'news grouping': (t) => t('tiered.role.newsGrouping'),
  'news ranking': (t) => t('tiered.role.newsRanking'),
  'news summary': (t) => t('tiered.role.newsSummary'),
  // Stages that write reader-facing text check its language since
  // 2026-09-26 and report through the "<stage> needed a retry — reply
  // not in <language>" notes; these two had no role label before.
  'preliminary analysis': (t) => t('tiered.role.preliminaryAnalysis'),
  'plan review': (t) => t('tiered.role.planReview'),
  // The report outline's citation-fix rounds name their stage "summary".
  summary: (t) => t('tiered.role.reportOutline'),
};

// A citation-fix round reports as "<stage> citation fix" — the same role
// with a suffix, so the note names the role and says it was a fix.
const CITATION_FIX_SUFFIX = ' citation fix';

// The language a run was asked to write in, as the backend names it in a
// note ("reply not in Simplified Chinese") → the page's own word for it.
const LANGUAGE_NAME_KEYS: Record<string, UiTextKey> = {
  English: 'tiered.languageName.en',
  'Simplified Chinese': 'tiered.languageName.zh',
};

const levelLabel = (key: string, t: Translate): string =>
  LEVEL_LABEL_KEYS[key] ? t(LEVEL_LABEL_KEYS[key]) : key;

const stageRole = (stage: string, t: Translate): string => {
  if (stage.endsWith(CITATION_FIX_SUFFIX)) {
    const role = stageRole(stage.slice(0, -CITATION_FIX_SUFFIX.length), t);
    return t('tiered.role.citationFix', { role });
  }
  return STAGE_ROLES[stage] ? STAGE_ROLES[stage](t) : stage;
};

const languageLabel = (name: string, t: Translate): string =>
  LANGUAGE_NAME_KEYS[name] ? t(LANGUAGE_NAME_KEYS[name]) : name;

interface NoteRule {
  pattern: RegExp;
  keywordKey: UiTextKey;
  toText: (match: RegExpMatchArray, t: Translate) => string;
}

const NOTE_RULES: NoteRule[] = [
  {
    pattern: /^reward below goal: .*reward-to-risk at ([\d.]+), below your ([\d.]+)/,
    keywordKey: KEY.rewardRatio,
    toText: (m, t) =>
      t('tiered.rewardBelowGoal', { ratio: m[1], goal: m[2] }),
  },
  {
    pattern: /^trend warning: close .* is at or below the (?:50|60)-day average/,
    keywordKey: KEY.downtrend,
    toText: (_m, t) => t('tiered.warning.downtrend'),
  },
  {
    pattern: /^sma_(?:50|60) unavailable — trend check skipped$/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.trendCheckSkipped'),
  },
  {
    pattern: /^fetch failed for (\S+?):?(?:\s|$)/,
    keywordKey: KEY.fetchFailed,
    toText: (m, t) => t('tiered.warning.fetchFailed', { domain: hostOf(m[1]) }),
  },
  {
    pattern: /^EDGAR (?:fundamentals failed|returned no usable (?:annual|statement) facts)/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.fundamentalsUnavailable'),
  },
  {
    pattern: /^Yahoo returned no valuation ratios/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.valuationUnavailable'),
  },
  {
    pattern: /^FRED series (\S+) (?:failed|returned no data)/,
    keywordKey: KEY.missingData,
    toText: (m, t) => t('tiered.warning.macroUnavailable', { series: m[1] }),
  },
  {
    pattern: /^indicators lacking history/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.indicatorNoHistory'),
  },
  {
    pattern: /^macro fields lacking data/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.macroFieldMissing'),
  },
  {
    pattern: /^options open interest missing or zero/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.optionsOiMissing'),
  },
  {
    pattern: /^options volume missing or zero/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.optionsVolumeMissing'),
  },
  {
    pattern: /^Yahoo returned no insider transaction rows/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.insiderRowsMissing'),
  },
  {
    pattern: /^adjustment for unknown level\b/,
    keywordKey: KEY.levels,
    toText: (_m, t) => t('tiered.warning.adjustUnknownLevel'),
  },
  // A later round's proposal was rejected, so the earlier ACCEPTED one
  // for that level stands (2026-10-10) — not the formula's number.
  {
    pattern: /^adjustment for '?(\w+)'? rejected: .* — the earlier accepted value (.+) kept$/,
    keywordKey: KEY.levels,
    toText: (m, t) =>
      t('tiered.warning.adjustmentRejectedEarlierKept', {
        level: levelLabel(m[1], t),
        value: m[2],
      }),
  },
  {
    pattern: /^adjustment for '?(\w+)'?\b/,
    keywordKey: KEY.levels,
    toText: (m, t) =>
      t('tiered.warning.adjustmentRejected', {
        level: levelLabel(m[1], t),
      }),
  },
  {
    pattern: / — falling back to the ATR stop$/,
    keywordKey: KEY.levels,
    toText: (_m, t) => t('tiered.warning.stopFallback'),
  },
  {
    pattern: /^no ATR available to derive a volatility stop$/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.noAtrStop'),
  },
  {
    pattern: /^no usable ATR — no volatility stop, and no target without a stop$/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.noAtrStopTarget'),
  },
  {
    pattern: /^no usable entry price — cannot place a stop$/,
    keywordKey: KEY.levels,
    toText: (_m, t) => t('tiered.warning.noEntryNoStop'),
  },
  // --- deep-analysis warnings (tier 2) ---
  // The degrade notes said "invalid after retry" until 2026-10-12 and
  // "unusable" since (a failed LLM call degrades the same way now); the
  // cause is its own note, so stored runs of both shapes word alike.
  {
    pattern: /^lister ([12]) grade sheet (?:invalid after retry|unusable) — proceeding with/,
    keywordKey: KEY.vote,
    toText: (m, t) =>
      t('tiered.warning.listerDegradedRole', {
        role: stageRole(`lister ${m[1]} grade sheet`, t),
      }),
  },
  {
    pattern: /^both lister grade sheets (?:invalid after retry|unusable) — deep-analysis outlook voided$/,
    keywordKey: KEY.outlook,
    toText: (_m, t) => t('tiered.warning.sheetsVoided'),
  },
  {
    pattern: /^deep analysis produced no outlook \(re-run\)$/,
    keywordKey: KEY.outlook,
    toText: (_m, t) => t('tiered.warning.noOutlook'),
  },
  // --- preliminary-analysis warnings (tier 1) ---
  {
    pattern: /^preliminary analysis produced no outlook \(re-run\)$/,
    keywordKey: KEY.outlook,
    toText: (_m, t) => t('tiered.warning.preliminaryNoOutlook'),
  },
  {
    pattern: /^preliminary analysis LLM call failed/,
    keywordKey: KEY.aiReply,
    toText: (_m, t) => t('tiered.warning.preliminaryCallFailed'),
  },
  {
    pattern: /^preliminary analysis reply rejected: (.+)$/,
    keywordKey: KEY.aiReply,
    toText: (m, t) => t('tiered.warning.preliminaryReplyRejected', { problem: m[1] }),
  },
  {
    pattern: /^check round (?:invalid after retry|unusable) — vote items counted on/,
    keywordKey: KEY.vote,
    toText: (_m, t) => t('tiered.warning.checkDegraded'),
  },
  {
    pattern: /^deciding round (?:invalid after retry|unusable) — tied vote items excluded/,
    keywordKey: KEY.vote,
    toText: (_m, t) => t('tiered.warning.tiebreakDegraded'),
  },
  {
    pattern: /^vote item \S+: citations unfixable .* — struck from the list$/,
    keywordKey: KEY.citations,
    toText: (_m, t) => t('tiered.warning.struckBullet'),
  },
  {
    pattern: /^vote on \S+ discarded — citations unfixable/,
    keywordKey: KEY.citations,
    toText: (_m, t) => t('tiered.warning.voteDiscarded'),
  },
  {
    pattern: /^no deciding vote for \S+ — excluded as unresolved$/,
    keywordKey: KEY.vote,
    toText: (_m, t) => t('tiered.warning.unresolved'),
  },
  {
    pattern: /^every vote item was listed by both listers — check round skipped$/,
    keywordKey: KEY.vote,
    toText: (_m, t) => t('tiered.warning.allConfirmed'),
  },
  {
    pattern: / — the final score rests on a thin base$/,
    keywordKey: KEY.vote,
    toText: (_m, t) => t('tiered.warning.thinBase'),
  },
  {
    pattern: /citation-fix reply invalid — fix round lost$/,
    keywordKey: KEY.citations,
    toText: (_m, t) => t('tiered.warning.fixRoundLost'),
  },
  {
    pattern: /^summary citations unfixable — those values are shown without links$/,
    keywordKey: KEY.citations,
    toText: (_m, t) => t('tiered.warning.summaryLinksDropped'),
  },
  {
    pattern: /^(.+) needed a retry — first reply was invalid$/,
    keywordKey: KEY.aiReply,
    toText: (m, t) =>
      t('tiered.warning.stageRetriedRole', { role: stageRole(m[1], t) }),
  },
  // The language check (2026-09-26): a reply not written in the run's
  // language went back with a correction …
  {
    pattern: /^(.+) needed a retry — reply not in (.+)$/,
    keywordKey: KEY.aiReply,
    toText: (m, t) =>
      t('tiered.warning.stageWrongLanguageRetried', {
        role: stageRole(m[1], t),
        language: languageLabel(m[2], t),
      }),
  },
  // … and, when the retries ran out (or a retry did not parse at all,
  // 2026-10-10), the last parsed reply is shown as written.
  {
    pattern: /^(.+) reply not in (.+) after (\d+) retr(?:y|ies) — shown as written$/,
    keywordKey: KEY.aiReply,
    toText: (m, t) =>
      t('tiered.warning.stageWrongLanguageKept', {
        role: stageRole(m[1], t),
        language: languageLabel(m[2], t),
        retries: m[3],
      }),
  },
  // A failed CALL (timeout, 5xx) in one lister or vote round degrades
  // like an invalid reply there since 2026-10-10; the stage names itself.
  {
    pattern: /^(lister [12] grade sheet|check round|deciding round) LLM call failed: (.*)$/,
    keywordKey: KEY.aiReply,
    toText: (m, t) =>
      t('tiered.warning.stageCallFailed', { role: stageRole(m[1], t), error: m[2] }),
  },
  {
    pattern: /^(.+?)(?: was not JSON even after a retry$| invalid after retry: )/,
    keywordKey: KEY.aiReply,
    toText: (m, t) =>
      t('tiered.warning.stageInvalidRole', { role: stageRole(m[1], t) }),
  },
  {
    pattern: /^no surviving evidence to weigh/,
    keywordKey: KEY.debate,
    toText: (_m, t) => t('tiered.warning.emptyLedger'),
  },
  {
    pattern: /^(?:judge summary unparseable|summary LLM call failed: .*) — computed outlook stands$/,
    keywordKey: KEY.aiReply,
    toText: (_m, t) => t('tiered.warning.summaryFailed'),
  },
  {
    pattern: / is not a number — ignored$/,
    keywordKey: KEY.settings,
    toText: (_m, t) => t('tiered.warning.badSetting'),
  },

  // ---- Audit 2026-08-08 -------------------------------------------------
  // Everything below used to fall through and render as the backend's own
  // engineer text — Python exception reprs ("HTTPError(...)"), variable
  // names ("bars_loader", "sma_50 / sma_200 / support_1") and even a note
  // addressed to a developer ("extend FOMC_DECISION_DATES"). Appended in a
  // block so the older, more specific rules above always win first.

  // Fetch failures: each names the source in words and says what went blank.
  {
    pattern: /^bars_loader failed for/,
    keywordKey: KEY.fetchFailed,
    toText: (_m, t) => t('tiered.warning.barsLoadFailed'),
  },
  {
    pattern: /^Yahoo summary failed for/,
    keywordKey: KEY.fetchFailed,
    toText: (_m, t) => t('tiered.warning.yahooSummaryFailed'),
  },
  {
    pattern: /^institutional holders failed for/,
    keywordKey: KEY.fetchFailed,
    toText: (_m, t) => t('tiered.warning.holdersFailed'),
  },
  {
    pattern: /^insider transactions failed for/,
    keywordKey: KEY.fetchFailed,
    toText: (_m, t) => t('tiered.warning.insiderFetchFailed'),
  },
  {
    pattern: /^options chain failed for/,
    keywordKey: KEY.fetchFailed,
    toText: (_m, t) => t('tiered.warning.optionsFetchFailed'),
  },
  {
    pattern: /^earnings date lookup failed for/,
    keywordKey: KEY.fetchFailed,
    toText: (_m, t) => t('tiered.warning.earningsDateFailed'),
  },
  {
    pattern: /^earnings history failed for/,
    keywordKey: KEY.fetchFailed,
    toText: (_m, t) => t('tiered.warning.earningsHistoryFailed'),
  },
  {
    pattern: /^bars for earnings reaction failed/,
    keywordKey: KEY.fetchFailed,
    toText: (_m, t) => t('tiered.warning.reactionBarsFailed'),
  },
  {
    pattern: /^EPS estimate trend failed for/,
    keywordKey: KEY.fetchFailed,
    toText: (_m, t) => t('tiered.warning.epsTrendFailed'),
  },
  {
    pattern: /^EPS revision counts failed for/,
    keywordKey: KEY.fetchFailed,
    toText: (_m, t) => t('tiered.warning.epsRevisionsFailed'),
  },
  {
    pattern: /^FRED release calendar for (.+) failed:/,
    keywordKey: KEY.fetchFailed,
    toText: (m, t) => t('tiered.warning.releaseCalendarFailed', { label: m[1] }),
  },
  {
    pattern: /^benchmark index bars unavailable/,
    keywordKey: KEY.fetchFailed,
    toText: (_m, t) => t('tiered.warning.benchmarkBarsFailed'),
  },
  {
    // src/tiered_analysis/providers/technicals.py (review 2026-10-10, D5)
    pattern:
      /^benchmark index bars end (\S+), the stock's end (\S+) — market trend and relative strength measured through (\S+)$/,
    keywordKey: KEY.missingData,
    toText: (m, t) =>
      t('tiered.warning.benchmarkDateMismatch', { index: m[1], stock: m[2], through: m[3] }),
  },
  {
    pattern: /^sector ETF (\S+) bars unavailable/,
    keywordKey: KEY.fetchFailed,
    toText: (m, t) => t('tiered.warning.sectorBarsFailed', { ticker: m[1] }),
  },
  {
    // company_news.py: the whole fetch failed; the detail is the source's own error text.
    pattern: /^news headlines unavailable: ([\s\S]+)$/,
    keywordKey: KEY.fetchFailed,
    toText: (m, t) => t('tiered.warning.newsHeadlinesFailed', { detail: m[1] }),
  },
  // world_news.py: the feed stack (Google News RSS, the Yahoo news-search
  // backup, the on-disk pool of earlier fetches) and the screen's fuse.
  {
    pattern: /^world news: Google News failed \(([\s\S]*)\); used the Yahoo backup feed$/,
    keywordKey: KEY.fetchFailed,
    toText: (m, t) => t('tiered.warning.worldNewsBackupFeed', { detail: m[1] }),
  },
  {
    pattern: /^world news: the feed returned no articles$/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.worldNewsEmptyFeed'),
  },
  {
    pattern: /^world news fetch failed: ([\s\S]+)$/,
    keywordKey: KEY.fetchFailed,
    toText: (m, t) => t('tiered.warning.worldNewsFetchFailed', { detail: m[1] }),
  },
  {
    pattern: /^world news unavailable: no pooled articles$/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.worldNewsUnavailable'),
  },
  {
    pattern: /^showing (\d+) previously fetched article\(s\) instead$/,
    keywordKey: KEY.missingData,
    toText: (m, t) => t('tiered.warning.worldNewsFromPool', { count: m[1] }),
  },
  {
    pattern: /^(\d+) world news item\(s\) skipped \(missing headline, link, or date\)$/,
    keywordKey: KEY.missingData,
    toText: (m, t) => t('tiered.warning.worldNewsItemsSkipped', { count: m[1] }),
  },
  {
    pattern: /^busy world window: screening (\d+) of (\d+) article\(s\), spread evenly across the window's days$/,
    keywordKey: KEY.newsCap,
    toText: (m, t) => t('tiered.warning.worldNewsScreenCap', { screened: m[1], total: m[2] }),
  },
  {
    pattern: /^(\w+) provider crashed/,
    keywordKey: KEY.fetchFailed,
    toText: (m, t) => t('tiered.warning.providerCrashed', { dataReport: m[1] }),
  },
  {
    pattern: /^deep analysis LLM call failed/,
    keywordKey: KEY.aiReply,
    toText: (_m, t) => t('tiered.warning.deepAnalysisCallFailed'),
  },
  {
    pattern: /^plan review LLM call failed/,
    keywordKey: KEY.aiReply,
    toText: (_m, t) => t('tiered.warning.planReviewCallFailed'),
  },
  {
    pattern: /^plan review got no usable reply even after a fix round$/,
    keywordKey: KEY.aiReply,
    toText: (_m, t) => t('tiered.warning.planReviewNoReply'),
  },
  {
    pattern: /^plan review skipped:/,
    keywordKey: KEY.settings,
    toText: (_m, t) => t('tiered.warning.planReviewSkipped'),
  },

  // Thin or absent history.
  {
    pattern: /^insufficient history for \S+: (\d+) bars < (\d+) required/,
    keywordKey: KEY.missingData,
    toText: (m, t) => t('tiered.warning.insufficientHistory', { bars: m[1], min: m[2] }),
  },
  {
    pattern: /^only (\d+) daily bars \(<(\d+)\)/,
    keywordKey: KEY.missingData,
    toText: (m, t) => t('tiered.warning.shortDailyHistory', { bars: m[1], year: m[2] }),
  },
  {
    pattern: /^only (\d+) weekly bars \(<(\d+)\)/,
    keywordKey: KEY.missingData,
    toText: (m, t) => t('tiered.warning.shortWeeklyHistory', { bars: m[1], target: m[2] }),
  },
  {
    pattern: /^benchmark index not configured/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.benchmarkNotConfigured'),
  },
  {
    pattern: /^benchmark index history too short \((\d+) bars\)/,
    keywordKey: KEY.missingData,
    toText: (m, t) => t('tiered.warning.benchmarkShort', { bars: m[1] }),
  },
  {
    pattern: /^benchmark index history too short for the regime read/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.benchmarkShortRegime'),
  },

  // Options board shortfalls.
  {
    pattern: /^CBOE published no 30-day implied volatility/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.noImpliedVol'),
  },
  {
    pattern: /^CBOE published no stock price/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.noOptionsStockPrice'),
  },
  {
    pattern: /^next report date unknown/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.reportDateUnknown'),
  },
  {
    pattern: /^next report date unparseable/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.reportDateUnreadable'),
  },
  {
    pattern: /^no usable at-the-money quotes/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.noAtmQuotes'),
  },
  {
    pattern: /^no fetched option expiration falls after/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.noPostReportExpiry'),
  },
  {
    pattern: /^no listed options found for/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.noListedOptions'),
  },

  // Disclosure and fundamentals shortfalls.
  {
    pattern: /^Yahoo returned no short-interest fields/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.noShortInterest'),
  },
  {
    pattern: /^Yahoo returned no ownership fields/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.noOwnership'),
  },
  {
    pattern: /^no earnings history rows for/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.noEarningsHistory'),
  },
  {
    pattern: /^too few earnings reports inside the bar history \((\d+)\)/,
    keywordKey: KEY.missingData,
    toText: (m, t) => t('tiered.warning.tooFewReports', { count: m[1] }),
  },

  // Economy data.
  {
    pattern: /^FRED_API_KEY is not set/,
    keywordKey: KEY.settings,
    toText: (_m, t) => t('tiered.warning.fredKeyMissing'),
  },
  {
    pattern: /^no upcoming (.+) release date found/,
    keywordKey: KEY.missingData,
    toText: (m, t) => t('tiered.warning.noReleaseDate', { label: m[1] }),
  },
  {
    pattern: /^FOMC decision-date table exhausted/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.fomcTableExhausted'),
  },

  // Sector comparison.
  {
    pattern: /^sector unknown \(/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.sectorUnknown'),
  },
  {
    pattern: /^sector '(.+)' has no sector-ETF mapping/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.sectorNoEtf'),
  },
  {
    pattern: /^sector comparison needs the market benchmark returns/,
    keywordKey: KEY.missingData,
    toText: (_m, t) => t('tiered.warning.sectorNeedsBenchmark'),
  },
  {
    pattern: /^sector ETF (\S+) history too short \((\d+) bars\)/,
    keywordKey: KEY.missingData,
    toText: (m, t) => t('tiered.warning.sectorShort', { ticker: m[1], bars: m[2] }),
  },

  // Trade plan.
  {
    pattern: /^no close price —/,
    keywordKey: KEY.levels,
    toText: (_m, t) => t('tiered.warning.noClosePrice'),
  },
  {
    pattern: /^no structural support anchors/,
    keywordKey: KEY.levels,
    toText: (_m, t) => t('tiered.warning.noEntryAnchor'),
  },
  {
    pattern: /^technicals unavailable — deterministic levels/,
    keywordKey: KEY.levels,
    toText: (_m, t) => t('tiered.warning.noTechnicalsForLevels'),
  },
  {
    pattern: /^duplicate adjustment for '?(\w+)'?/,
    keywordKey: KEY.levels,
    toText: (m, t) =>
      t('tiered.warning.duplicateAdjust', { level: levelLabel(m[1], t) }),
  },
  {
    pattern: /^plan-review adjustment for '?(\w+)'? dropped/,
    keywordKey: KEY.citations,
    toText: (m, t) =>
      t('tiered.warning.planAdjustDropped', { level: levelLabel(m[1], t) }),
  },
  {
    pattern: /^plan-review reply problem/,
    keywordKey: KEY.aiReply,
    toText: (_m, t) => t('tiered.warning.planReplyProblem'),
  },
  {
    pattern: /^plan review did not converge/,
    keywordKey: KEY.riskCheck,
    toText: (_m, t) => t('tiered.warning.planNoConverge'),
  },

  // Outlook.
  {
    pattern: /^no gradable report fields collected/,
    keywordKey: KEY.outlook,
    toText: (_m, t) => t('tiered.warning.noGradableFields'),
  },
  {
    pattern: /^no collected evidence to vote on/,
    keywordKey: KEY.outlook,
    toText: (_m, t) => t('tiered.warning.noEvidenceToVote'),
  },

  // Settings.
  {
    pattern: /must be above 1 — using the default/,
    keywordKey: KEY.settings,
    toText: (_m, t) => t('tiered.warning.rewardRiskDefaulted'),
  },

  // News screen (news_screen.py, company and world cards alike). Every
  // stage fails soft — judge unrated-kept, grouping to singletons,
  // ranking to score order, summaries to the feed's words — so each
  // note describes a polish loss, never lost news.
  {
    pattern: /^news judge (?:LLM call failed: .*|returned no usable JSON) — all articles kept$/,
    keywordKey: KEY.aiReply,
    toText: (_m, t) => t('tiered.warning.newsJudgeFailed'),
  },
  {
    pattern: /^news judge gave no judgment for (\d+) article\(s\) — those kept$/,
    keywordKey: KEY.aiReply,
    toText: (m, t) => t('tiered.warning.newsJudgeMissing', { count: m[1] }),
  },
  {
    pattern: /^news judge gave an unreadable importance for (\d+) article\(s\) — those kept, judged again next run$/,
    keywordKey: KEY.aiReply,
    toText: (m, t) => t('tiered.warning.newsJudgeUnreadable', { count: m[1] }),
  },
  {
    pattern: /^news grouping (?:LLM call failed: .*|returned no usable JSON) — no grouping$/,
    keywordKey: KEY.aiReply,
    toText: (_m, t) => t('tiered.warning.newsGroupFailed'),
  },
  {
    pattern: /^news grouping left (\d+) article\(s\) ungrouped — kept as separate events$/,
    keywordKey: KEY.aiReply,
    toText: (m, t) => t('tiered.warning.newsGroupPartial', { count: m[1] }),
  },
  {
    pattern: /^news ranking (?:LLM call failed: .*|returned no usable JSON) — importance-score order kept$/,
    keywordKey: KEY.aiReply,
    toText: (_m, t) => t('tiered.warning.newsRankFailed'),
  },
  {
    pattern: /^news ranking left (\d+) event\(s\) unranked — appended in importance-score order$/,
    keywordKey: KEY.aiReply,
    toText: (m, t) => t('tiered.warning.newsRankPartial', { count: m[1] }),
  },
  {
    pattern: /^news summary (?:LLM call failed: .*|returned no usable JSON) — feed abstracts shown verbatim$/,
    keywordKey: KEY.aiReply,
    toText: (_m, t) => t('tiered.warning.newsSummaryFailed'),
  },
  {
    pattern: /^news summary missing for (\d+) article\(s\) — those show the feed abstract verbatim$/,
    keywordKey: KEY.aiReply,
    toText: (m, t) => t('tiered.warning.newsSummaryMissing', { count: m[1] }),
  },
  {
    pattern: /^busy news window: (\d+) event\(s\) ranked below the top (\d+) and trimmed$/,
    keywordKey: KEY.newsCap,
    toText: (m, t) => t('tiered.warning.newsTrimmed', { count: m[1], max: m[2] }),
  },
];

// ---- plan-note routing (owner request 2026-08-09) ----------------------
// Warnings the trade-plan machinery emits — the deterministic levels
// engine (levels.py, stops.py) and
// the plan review (plan_review.py). They describe the PLAN, not the
// analysis, so the plan card is their only home; on runs whose outlook
// renders no plan card they disappear with it instead of leaking onto
// the preliminary-analysis card.
const PLAN_NOTE_RES: RegExp[] = [
  /^reward below goal: /,
  /^trend warning: /,
  /^sma_(?:50|60) unavailable — trend check skipped$/,
  /^no close price —/,
  /^no structural support anchors/,
  /^no usable ATR — /,
  /^no ATR available to derive a volatility stop$/,
  / — falling back to the ATR stop$/,
  /^no usable entry price — cannot place a stop$/,
  /^technicals unavailable — deterministic levels/,
  /^adjustment for /,
  /^duplicate adjustment for /,
  /^plan-review /,
  /^plan review /,
];

// True when a backend run warning is about the trade plan (see the list
// above). Plan-review retries prefix their notes with "round N: ".
export function isPlanNote(raw: string): boolean {
  const text = raw.replace(/^round \d+: /, '');
  return PLAN_NOTE_RES.some((pattern) => pattern.test(text));
}

// ---- rich note slots (owner request 2026-08-23) -------------------------
// Some notes carry values that the field-notes modal renders live: a
// report-field name as a jump link to that field's row, or a day count
// with its own date-minus-date receipt. The slot data stays plain here
// (this module renders no JSX); FieldWarnings builds the elements.

/** Another report field, shown under its exact display name (its
    metricLabels `short`) as a link that jumps to its row. */
export interface NoteMetricLinkSlot {
  kind: 'metricLink';
  /** The metricLabels key whose `short` names the link. */
  term: string;
  /** Payload row paths to try in order (new format first). */
  paths: string[];
}

/** A "days until the next quarterly report" count, clickable to open
    its calculation receipt (report date − today). */
export interface NoteDaysReceiptSlot {
  kind: 'daysReceipt';
  days: number;
  /** ISO dates the receipt plugs in. */
  reportDate: string;
  today: string;
}

export type NoteSlot = NoteMetricLinkSlot | NoteDaysReceiptSlot;

export interface FriendlyNote {
  /** The fixed keyword the note leads with (already translated). */
  keyword: string;
  /** The plain-English sentence (already translated, slots resolved
      to their plain names/numbers). */
  text: string;
  /** Rich notes only: `text` with its {name} tokens still in place… */
  template?: string;
  /** …and how each token renders live. */
  slots?: Record<string, NoteSlot>;
}

interface RichRule {
  pattern: RegExp;
  keywordKey: UiTextKey;
  build: (
    match: RegExpMatchArray,
    t: Translate,
  ) => {
    templateKey: UiTextKey;
    params?: Record<string, string | number>;
    slots: Record<string, NoteSlot>;
  };
}

// Note shapes whose modal rendering carries live elements. Matched
// before NOTE_RULES; the older plain shapes stay there for stored runs.
const RICH_RULES: RichRule[] = [
  {
    // 2026-08-23 note format: the actual countdown plus both dates, so
    // the modal shows the real number of days with its receipt.
    pattern:
      /^next quarterly report is (\d+) days away \(report (\d{4}-\d{2}-\d{2}), today (\d{4}-\d{2}-\d{2})\) — more than (\d+) days out/,
    keywordKey: KEY.missingData,
    build: (m) => ({
      templateKey: 'tiered.warning.reportTooFarExact',
      params: { max: m[4] },
      slots: {
        days: {
          kind: 'daysReceipt',
          days: Number(m[1]),
          reportDate: m[2],
          today: m[3],
        },
      },
    }),
  },
  {
    pattern: /^implied report-day move missing — report-move ratio/,
    keywordKey: KEY.missingData,
    build: () => ({
      templateKey: 'tiered.warning.ratioMissingIngredient',
      slots: {
        field: {
          kind: 'metricLink',
          term: 'implied_report_move_pct',
          paths: ['positioning.options.implied_report_move_pct'],
        },
      },
    }),
  },
  {
    pattern: /^realized 4q average report-day move missing or zero — report-move ratio/,
    keywordKey: KEY.missingData,
    build: () => ({
      templateKey: 'tiered.warning.ratioMissingIngredient',
      slots: {
        field: {
          kind: 'metricLink',
          term: 'reaction_avg_abs_pct',
          paths: ['fundamentals.quarterly_report.reaction_avg_abs_pct'],
        },
      },
    }),
  },
];

// A slot's plain-text stand-in — what non-rich renderings (and copied
// text) show in place of the live element.
function slotText(slot: NoteSlot, language: UiLanguage): string {
  if (slot.kind === 'metricLink') {
    return `"${metricEntry(slot.term, language)?.short ?? slot.term}"`;
  }
  return String(slot.days);
}

function resolveSlots(
  template: string,
  slots: Record<string, NoteSlot>,
  language: UiLanguage,
): string {
  return template.replace(/\{(\w+)\}/g, (token, name: string) => {
    const slot = slots[name];
    return slot === undefined ? token : slotText(slot, language);
  });
}

// Keyword + plain-English rewrite of one backend warning. Unknown
// shapes keep their raw text under the generic "Warning" keyword.
export function friendlyWarning(
  raw: string,
  t: Translate,
  language: UiLanguage = 'en',
): FriendlyNote {
  const text = raw.replace(/^round \d+: /, '');
  for (const rule of RICH_RULES) {
    const match = text.match(rule.pattern);
    if (match) {
      const { templateKey, params, slots } = rule.build(match, t);
      const template = t(templateKey, params);
      return {
        keyword: t(rule.keywordKey),
        text: resolveSlots(template, slots, language),
        template,
        slots,
      };
    }
  }
  for (const rule of NOTE_RULES) {
    const match = text.match(rule.pattern);
    if (match) {
      return { keyword: t(rule.keywordKey), text: rule.toText(match, t) };
    }
  }
  return { keyword: t(KEY.other), text: raw };
}
