import { useState, type ReactNode } from 'react';
import {
  tieredApi,
  type TieredTranscriptCall,
  type TieredTranscriptCallFacts,
  type TieredTranscriptCallSummary,
} from '../../api/tiered';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import { Tooltip } from '../common/Tooltip';
import { Card, FactFold } from './Ui';
import { parseCallError } from './transcriptError';

export interface TranscriptProps {
  /** The run whose LLM exchanges to show. */
  runId: string;
  /** The usage line ("This run used N LLM calls…") — it is the toggle. */
  label: ReactNode;
  /** Test seams; production reads the run's stored transcript. */
  loader?: (runId: string) => Promise<TieredTranscriptCallSummary[]>;
  callLoader?: (runId: string, callNumber: number) => Promise<TieredTranscriptCall>;
}

type LoadState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; items: TieredTranscriptCallSummary[] };

// The run's AI exchanges folded under the usage line itself (owner
// decision 2026-09-17: one line to click, not a second "view transcript"
// link below it). Two-step loading (2026-09-21): opening the line fetches
// the index — one small row of facts per call — and each call's prompt
// and reply are fetched the first time either fold is opened, since the
// text of every call together runs to half a megabyte and most readers
// never open one. Exists so a "returned no usable JSON" warning is
// diagnosable from the page instead of a re-run.
export const Transcript = ({
  runId,
  label,
  loader = tieredApi.getTranscript,
  callLoader = tieredApi.getTranscriptCall,
}: TranscriptProps) => {
  const { t } = useUiLanguage();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<LoadState>({ kind: 'idle' });

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (!next || state.kind === 'ready' || state.kind === 'loading') {
      return;
    }
    setState({ kind: 'loading' });
    try {
      const items = await loader(runId);
      setState({ kind: 'ready', items });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setState({ kind: 'error', message });
    }
  };

  return (
    <UsageLine label={label} help={t('tiered.help.llmUsage')} open={open} onToggle={() => void toggle()}>
      {open ? (
        // The same card surface as the report and analysis cards (owner
        // request 2026-09-18), not the history backdrop.
        <Card testId="transcript" className="mt-2 flex flex-col gap-4">
          {state.kind === 'loading' ? (
            <p className="text-ink-4">{t('tiered.transcript.loading')}</p>
          ) : null}
          {state.kind === 'error' ? (
            <p className="text-caution">
              {t('tiered.transcript.error', { error: state.message })}
            </p>
          ) : null}
          {state.kind === 'ready' && state.items.length === 0 ? (
            <p className="text-ink-4">{t('tiered.transcript.empty')}</p>
          ) : null}
          {state.kind === 'ready'
            ? state.items.map((item) => (
                <TranscriptCall
                  key={item.call_number}
                  item={item}
                  load={() => callLoader(runId, item.call_number)}
                />
              ))
            : null}
        </Card>
      ) : null}
    </UsageLine>
  );
};

export interface UsageLineProps {
  /** "This run used N LLM calls (M tokens)", or the chat's "This step used N tokens". */
  label: ReactNode;
  /** The help popup's text. */
  help: string;
  open: boolean;
  onToggle: () => void;
  testId?: string;
  /** What the line opens, rendered under it (the caller shows it only when open). */
  children?: ReactNode;
}

// The token usage line — one small quiet line that opens what it
// counts. The run page and the chat page render this same component
// so the two lines look identical (owner request 2026-09-23).
export const UsageLine = ({ label, help, open, onToggle, testId, children }: UsageLineProps) => (
  <div className="text-xs">
    {/* The help popup wraps the button rather than sitting inside it,
        so the line is a single tab stop: hover or focus shows the help,
        click/Enter opens the transcript. */}
    <Tooltip content={<span className="block max-w-[16rem] whitespace-pre-line">{help}</span>}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        data-testid={testId}
        className="text-left text-ink-5 hover:text-ink-2"
      >
        {label}
      </button>
    </Tooltip>
    {children}
  </div>
);

// What a call was for, in the page's language: the backend's stage
// identifier ("company_news", "deep_analysis") → the name the page
// already gives that data report or analysis step. An identifier
// without a page name falls back to the identifier read as words.
const STAGE_NAME_KEYS: Record<string, UiTextKey> = {
  technicals: 'tiered.dataReport.technicals',
  fundamentals: 'tiered.dataReport.fundamentals',
  macro_economy: 'tiered.dataReport.macro_economy',
  positioning: 'tiered.dataReport.positioning',
  company_news: 'tiered.dataReport.company_news',
  world_news: 'tiered.dataReport.world_news',
  preliminary_analysis: 'tiered.role.preliminaryAnalysis',
  deep_analysis: 'tiered.deepAnalysis.title',
  trade_plan: 'tiered.tradePlan.title',
};

const stageName = (stage: string | null, t: (key: UiTextKey) => string): string => {
  if (stage == null) {
    return '—';
  }
  const key = STAGE_NAME_KEYS[stage];
  return key ? t(key) : stage.replace(/_/g, ' ');
};

// The status fact (owner format 2026-10-19): "succeeded" in green, or
// "failed" in red followed by the provider's error facts as
// `{"code": 503, "status": "UNAVAILABLE", "message": "…"}` — the values
// in amber, the punctuation and keys in the value's usual color.
const CallStatus = ({ error }: { error: string | null }) => {
  const { t } = useUiLanguage();
  if (error == null) {
    return <span className="font-semibold text-positive">{t('tiered.transcript.statusSucceeded')}</span>;
  }
  const facts = parseCallError(error);
  return (
    <span className="font-semibold text-ink-1">
      <span className="text-negative">{t('tiered.transcript.statusFailed')}</span>
      {' - {'}
      {facts.map(([key, value], index) => (
        <span key={key}>
          {index > 0 ? ', ' : ''}
          {`"${key}": `}
          <span className="text-caution [overflow-wrap:anywhere]">{JSON.stringify(value)}</span>
        </span>
      ))}
      {'}'}
    </span>
  );
};

type CallState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; call: TieredTranscriptCall };

// One exchange: "LLM call N" (or a caller's own title), then fact
// lines (what it was for, the model, time) in the same quiet-label /
// bright-value styling as the outlook and score facts, and two more
// lines in that same styling that open: "input: N tokens ▸" is the
// prompt, "output: N tokens ▸" is the reply (owner request 2026-09-24
// — no tokens fact, no titled folds with their own backdrop). Both
// folded by default; opened, the whole text shows on the fold surface,
// no inner scroll box (owner requests 2026-09-18). The text arrives
// when either first opens. Shared with the chat page, which shows one
// of these under a reply's token line (2026-09-23).
export const TranscriptCall = ({
  item,
  load,
  title,
  missing,
  foldSurface,
  showTitle = true,
  showStage = true,
}: {
  item: TieredTranscriptCallFacts;
  load: () => Promise<TieredTranscriptCall>;
  title?: string;
  /** Set when no transcript was kept: both folds show this instead of loading. */
  missing?: string;
  /** Classes on an opened prompt's or reply's box (backdrop, indent); the alt page's inset when unset. */
  foldSurface?: string;
  /** Off where the title says nothing new — the chat, where every call is the one under its reply. */
  showTitle?: boolean;
  /** Off where the stage fact never varies — the chat, where every call's stage is "chat" (owner request 2026-09-24). */
  showStage?: boolean;
}) => {
  const { t } = useUiLanguage();
  const [call, setCall] = useState<CallState>({ kind: 'idle' });
  const input = item.input_tokens ?? 0;
  const output = item.output_tokens ?? 0;
  // The status sits between the model and the time (owner order 2026-10-19).
  const facts: [string, ReactNode][] = [
    ...(showStage ? [[t('tiered.transcript.for'), stageName(item.stage, t)] as [string, ReactNode]] : []),
    [t('tiered.transcript.llm'), item.llm ?? '—'],
    [t('tiered.transcript.status'), <CallStatus error={item.error ?? null} />],
    [t('tiered.transcript.time'), item.time_ms == null ? '—' : `${item.time_ms}ms`],
  ];

  const ensureLoaded = (opened: boolean) => {
    if (!opened || call.kind !== 'idle' || missing) {
      return;
    }
    setCall({ kind: 'loading' });
    void load().then(
      (loaded) => setCall({ kind: 'ready', call: loaded }),
      (error: unknown) =>
        setCall({
          kind: 'error',
          message: error instanceof Error ? error.message : String(error),
        }),
    );
  };

  // The fold body for one of the two texts, by load state.
  const text = (pick: (loaded: TieredTranscriptCall) => string | null, empty: string) => {
    if (missing) {
      return missing;
    }
    if (call.kind === 'ready') {
      return pick(call.call) ?? empty;
    }
    if (call.kind === 'error') {
      return t('tiered.transcript.callError', { error: call.message });
    }
    return t('tiered.transcript.callLoading');
  };

  return (
    <article className="flex min-w-0 flex-col gap-2 border-t border-border pt-4 first:border-t-0 first:pt-0">
      <div className="flex flex-col gap-1">
        {showTitle ? (
          <p className="font-semibold text-ink-2">{title ?? t('tiered.transcript.call', { n: item.call_number })}</p>
        ) : null}
        <div className="flex flex-col gap-0.5" data-testid="transcript-facts">
          {facts.map(([label, value]) => (
            <span key={label} className="text-ink-4">
              {label}
              {': '}
              {typeof value === 'string' ? (
                <span className="font-semibold text-ink-1">{value}</span>
              ) : (
                value
              )}
            </span>
          ))}
          <FactFold
            label={t('tiered.transcript.input')}
            value={t('tiered.transcript.tokenCount', { n: input })}
            onToggle={ensureLoaded}
            testId="transcript-input"
            surfaceClassName={foldSurface}
          >
            <pre className="min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere] text-[11px] text-ink-3">
              {text((loaded) => loaded.input, '')}
            </pre>
          </FactFold>
          <FactFold
            label={t('tiered.transcript.output')}
            value={t('tiered.transcript.tokenCount', { n: output })}
            onToggle={ensureLoaded}
            testId="transcript-output"
            surfaceClassName={foldSurface}
          >
            <pre className="min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere] text-[11px] text-ink-2">
              {text((loaded) => loaded.output, t('tiered.transcript.noReply'))}
            </pre>
          </FactFold>
        </div>
      </div>
    </article>
  );
};
