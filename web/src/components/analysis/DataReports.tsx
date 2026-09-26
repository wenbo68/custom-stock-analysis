import type { ReactNode } from 'react';
import type { TieredDataReport, TieredMetricFormula } from '../../api/tiered';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import {
  dedupeCitations,
  isMetricEnvelope,
  metricAnchorId,
  metricValue,
} from '../tiered/termHelpers';
import { MetricTerm } from '../tiered/terms';
import { formatMetricValue, slashDate } from './format';
import { EventsList } from './Events';
import { EVENTS_REPORTS, eventsWindowLabel } from './eventsData';
import { FieldWarnings, MetricValue } from './MetricFormula';
import { ALT_LINK } from './styles';
import { Card, SummaryText, WarningsButton } from './Ui';

const DATA_REPORT_LABEL_KEYS: Record<string, UiTextKey> = {
  technicals: 'tiered.dataReport.technicals',
  fundamentals: 'tiered.dataReport.fundamentals',
  macro_economy: 'tiered.dataReport.macro_economy',
  positioning: 'tiered.dataReport.positioning',
  company_news: 'tiered.dataReport.company_news',
  world_news: 'tiered.dataReport.world_news',
};

// Named sections for payloads the backend sends (partly) flat, so every
// number sits under a heading. The technicals map now serves STORED
// runs only: v2 runs (2026-07-27) ship nested groups of envelopes, so
// every v2 key flows through the nested-group path below and takes its
// section title from its own group key. The trailing Other section
// survives only as a crash-guard for future keys.
const DATA_REPORT_SECTIONS: Record<string, { titleKey: UiTextKey; keys: string[] }[]> = {
  technicals: [
    {
      titleKey: 'tiered.group.trend',
      keys: ['close', 'sma_20', 'sma_60', 'ema_12', 'ema_26', 'bias_20'],
    },
    { titleKey: 'tiered.group.momentum', keys: ['rsi_14', 'macd'] },
    {
      titleKey: 'tiered.group.volatility',
      keys: ['atr_14', 'volatility_pct', 'worst_day_pct_1y'],
    },
    {
      titleKey: 'tiered.group.structure',
      keys: [
        'swing_low_20', 'swing_high_20', 'swing_low_60', 'swing_high_60',
        'high_52w', 'low_52w',
      ],
    },
    { titleKey: 'tiered.group.volume', keys: ['avg_volume_20'] },
    { titleKey: 'tiered.group.meta', keys: ['bars_count'] },
  ],
  macro_economy: [{ titleKey: 'tiered.group.reportInfo', keys: ['region', 'as_of'] }],
  // The next earnings date rides in the fundamentals payload (plan-review
  // redesign) — give it a named section instead of the Other bucket.
  fundamentals: [
    {
      titleKey: 'tiered.group.earnings',
      keys: ['next_earnings_date', 'days_until_earnings'],
    },
  ],
};

// A nested display group — but never a v2 metric envelope, which is one
// metric (rendered as a single row), not a group of three.
function isGroup(values: unknown): values is Record<string, unknown> {
  return (
    values !== null &&
    typeof values === 'object' &&
    !Array.isArray(values) &&
    !isMetricEnvelope(values)
  );
}

interface PayloadSection {
  key: string;
  title: ReactNode;
  entries: [string, unknown][];
}

// Split a payload into titled sections: configured sections first (in their
// configured order), then any remaining nested group under its own name,
// then leftover flat keys under "Other".
function buildSections(
  dataReport: string,
  payload: Record<string, unknown>,
  t: (key: UiTextKey) => string,
): PayloadSection[] {
  const remaining = new Map(Object.entries(payload));
  const sections: PayloadSection[] = [];

  for (const config of DATA_REPORT_SECTIONS[dataReport] ?? []) {
    const entries: [string, unknown][] = [];
    for (const key of config.keys) {
      if (remaining.has(key)) {
        entries.push([key, remaining.get(key)]);
        remaining.delete(key);
      }
    }
    if (entries.length > 0) {
      sections.push({ key: config.titleKey, title: t(config.titleKey), entries });
    }
  }

  const leftoverFlat: [string, unknown][] = [];
  for (const [key, values] of remaining) {
    if (isGroup(values)) {
      sections.push({
        key,
        title: <MetricTerm term={key} underline={false} />,
        entries: [[key, values]],
      });
    } else {
      leftoverFlat.push([key, values]);
    }
  }
  if (leftoverFlat.length > 0) {
    sections.push({ key: 'other', title: t('tiered.group.other'), entries: leftoverFlat });
  }
  return sections;
}

interface MetricRowProps {
  anchorPath: string;
  term: string;
  value: unknown;
  /** How this number was computed (technicals v2 runs) — when present,
      the value is a button opening the formula receipt. */
  formula?: TieredMetricFormula | null;
  /** This run's backend notes about this field (from field_warnings) —
      rendered as a small exclamation mark after the value. */
  notes?: string[] | null;
  /** The value's observation date, shown dimmed after it (macro rows). */
  date?: unknown;
  /** The date's own payload path — it stays a citable evidence target
      (macro_economy.observation_dates.*), so it keeps its anchor id even
      though it no longer has a row of its own. */
  dateAnchorPath?: string;
}

// Every row stays a single line (owner request 2026-08-01): the value
// never wraps, and the label ellipsizes when the remaining space runs
// out — the tooltip's bold header always carries the full name.
const MetricRow = ({
  anchorPath, term, value, formula, notes, date, dateAnchorPath,
}: MetricRowProps) => (
  <div
    id={metricAnchorId(anchorPath)}
    className="flex scroll-mt-24 items-baseline justify-between gap-3 py-1"
  >
    <dt className="min-w-0 truncate text-xs">
      <MetricTerm term={term} underline={false} truncate />
    </dt>
    <dd className="shrink-0 whitespace-nowrap text-xs tabular-nums text-ink-2">
      {value == null ? (
        // Blank field: plain "n/a" — the reason lives behind the
        // exclamation mark beside it (owner request 2026-08-05).
        <span data-testid={`metric-blank-${term}`}>n/a</span>
      ) : formula ? (
        <MetricValue term={term} value={value} formula={formula} />
      ) : (
        formatMetricValue(term, value)
      )}
      {typeof date === 'string' ? (
        // The leading {' '} is a real space so copied text reads
        // "16.64 2026/07/22", not "16.642026/07/22" (owner report).
        <>
          {' '}
          <span
            id={dateAnchorPath ? metricAnchorId(dateAnchorPath) : undefined}
            className="ml-1 scroll-mt-24 text-ink-4"
          >
            {slashDate(date)}
          </span>
        </>
      ) : null}
      <FieldWarnings term={term} notes={notes ?? null} isBlank={value == null} />
    </dd>
  </div>
);

interface PayloadTableProps {
  dataReport: string;
  payload: Record<string, unknown>;
  /** "group.key" → receipt (technicals v2 runs); null elsewhere. */
  formulas: Record<string, TieredMetricFormula> | null;
  /** "group.key" → this run's notes about that field; null on old runs. */
  fieldNotes: Record<string, string[]> | null;
}

// The macro payload's per-series observation dates: not a display group
// of its own (owner decision 2026-07-24) — each date renders dimmed
// beside its metric's value instead ("value date").
const OBSERVATION_DATES_KEY = 'observation_dates';

// Every metric sits in a titled section; a hairline separates sections.
// Rows keep the same anchor ids as the main page so evidence links and
// formula inputs can scroll straight to their source here too.
const PayloadTable = ({
  dataReport, payload, formulas, fieldNotes,
}: PayloadTableProps) => {
  const { t } = useUiLanguage();
  const rawDates = payload[OBSERVATION_DATES_KEY];
  const dates = isGroup(rawDates) ? rawDates : null;
  const shownPayload = dates
    ? Object.fromEntries(
        Object.entries(payload).filter(([key]) => key !== OBSERVATION_DATES_KEY),
      )
    : payload;
  const sections = buildSections(dataReport, shownPayload, t);

  return (
    <div className="flex flex-col divide-y divide-border/60">
      {sections.map((section) => (
        <div key={section.key} className="py-3 first:pt-0 last:pb-0">
          <div className="mb-1 text-[11px] font-bold uppercase tracking-wider text-ink-4">
            {section.title}
          </div>
          <dl className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
            {section.entries.map(([key, values]) =>
              isGroup(values) ? (
                // v2 envelope leaves unwrap to their value; the anchor id
                // stays the envelope path (what citations reference).
                Object.entries(values).map(([subKey, value]) => (
                  <MetricRow
                    key={`${key}.${subKey}`}
                    anchorPath={`${dataReport}.${key}.${subKey}`}
                    term={subKey}
                    value={metricValue(value)}
                    formula={formulas?.[`${key}.${subKey}`] ?? null}
                    notes={fieldNotes?.[`${key}.${subKey}`] ?? null}
                    date={dates?.[subKey]}
                    dateAnchorPath={`${dataReport}.${OBSERVATION_DATES_KEY}.${subKey}`}
                  />
                ))
              ) : (
                <MetricRow
                  key={key}
                  anchorPath={`${dataReport}.${key}`}
                  term={key}
                  value={metricValue(values)}
                  formula={formulas?.[key] ?? null}
                  notes={fieldNotes?.[key] ?? null}
                  date={dates?.[key]}
                  dateAnchorPath={`${dataReport}.${OBSERVATION_DATES_KEY}.${key}`}
                />
              ),
            )}
          </dl>
        </div>
      ))}
    </div>
  );
};

interface DataReportCardProps {
  dataReport: TieredDataReport;
}

const DataReportCard = ({ dataReport }: DataReportCardProps) => {
  const { t } = useUiLanguage();
  const labelKey = DATA_REPORT_LABEL_KEYS[dataReport.name];
  const fieldNotes = dataReport.field_warnings ?? null;
  // Notes that sit beside their own field (field_warnings) no longer show
  // at the card level (owner request 2026-08-05). What remains — notes
  // the backend attached to no field, and every note on old stored runs
  // without field_warnings — keeps the card-level button so nothing is
  // silently lost. Unavailable dataReports have no rows for per-field
  // marks, so the red X also stays.
  const coveredNotes = new Set(Object.values(fieldNotes ?? {}).flat());
  const cardNotes = dataReport.warnings.filter((note) => !coveredNotes.has(note));
  const uniqueCitations = dedupeCitations(dataReport.citations);
  // Listed non-links first, links after; each keeps the [n] number of its
  // position in uniqueCitations, because that is what the summary's
  // inline [n] marks refer to. The events cards number their vote items the
  // same way, so their sources show their [n] too.
  const showSourceNumbers =
    dataReport.summary != null ||
    EVENTS_REPORTS.includes(dataReport.name);
  const listedCitations = uniqueCitations
    .map((citation, index) => ({ citation, number: index + 1 }))
    .sort((a, b) => Number(Boolean(a.citation.url)) - Number(Boolean(b.citation.url)));

  // The news cards' horizon sits beside the title (owner request
  // 2026-08-17): the company card's fixed lookback ("last 7 days") or
  // the world card's actual fetched span (its feed has no date range).
  const window =
    dataReport.payload && EVENTS_REPORTS.includes(dataReport.name)
      ? eventsWindowLabel(dataReport.payload)
      : null;

  return (
    <Card testId={`data-report-${dataReport.name}`}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="min-w-0 truncate font-semibold text-ink-2">
          {/* Unknown dataReports fall back to their raw name, humanized —
              payload identifiers never reach the UI with underscores. */}
          <span>
            {labelKey ? t(labelKey) : dataReport.name.replace(/_/g, ' ')}
          </span>
          {window != null ? (
            <span className="ml-2 text-xs font-normal text-ink-4">
              {window.kind === 'days'
                ? t('tiered.eventsWindow', { count: window.count })
                : window.oldest === window.newest
                  ? slashDate(window.newest)
                  : `${slashDate(window.oldest)} – ${slashDate(window.newest)}`}
            </span>
          ) : null}
        </h3>
        <WarningsButton notes={cardNotes} />
      </div>

      {dataReport.summary ? (
        <div className="mb-3">
          <SummaryText text={dataReport.summary} citations={uniqueCitations} />
        </div>
      ) : null}

      {dataReport.payload ? (
        EVENTS_REPORTS.includes(dataReport.name) ? (
          // Bullet lines with [n] source marks, not metric rows.
          <EventsList
            dataReport={dataReport.name}
            payload={dataReport.payload}
          />
        ) : (
          <PayloadTable
            dataReport={dataReport.name}
            payload={dataReport.payload}
            formulas={dataReport.formulas ?? null}
            fieldNotes={fieldNotes}
          />
        )
      ) : null}

      {listedCitations.length > 0 ? (
        <div className="mt-3 border-t border-border/60 pt-3">
          <div className="mb-1 text-xs font-semibold text-ink-4">
            {t('tiered.sources')}
          </div>
          <ul className="flex flex-col gap-1">
            {listedCitations.map(({ citation, number }) => (
              // id: the vote tree's "sentiment.citation:N" chips jump here
              // instead of leaving the page — the external link stays one
              // click away.
              <li
                key={number}
                id={`src-${dataReport.name}-${number}`}
                className="flex scroll-mt-24 gap-2 text-xs"
              >
                {showSourceNumbers ? (
                  <span className="shrink-0 text-ink-4">[{number}]</span>
                ) : null}
                {citation.url ? (
                  // News articles (they carry a headline) list as their URL
                  // — a link's destination stays visible, never hidden
                  // behind an AI-echoed headline. Backend-named sources
                  // (no headline) list as their descriptive name; the URL
                  // lives behind the link (owner decision 2026-07-24).
                  <a
                    href={citation.url}
                    target="_blank"
                    rel="noreferrer"
                    className={`truncate ${ALT_LINK}`}
                  >
                    {citation.title === null ? citation.source_name : citation.url}
                  </a>
                ) : (
                  <span className="truncate">{citation.source_name}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Card>
  );
};

interface DataReportsProps {
  dataReports: TieredDataReport[];
}

export const DataReports = ({ dataReports }: DataReportsProps) => (
  <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
    {dataReports.map((dataReport) => (
      <DataReportCard key={dataReport.name} dataReport={dataReport} />
    ))}
  </div>
);
