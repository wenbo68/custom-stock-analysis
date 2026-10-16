import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { chatApi, type ChatMessage, type ChatPendingCall } from '../../api/chat';
import type { TieredTranscriptCall } from '../../api/tiered';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { TranscriptCall, UsageLine } from '../analysis/Transcript';
import { FactFold } from '../analysis/Ui';
import { ChatMarkdown } from './ChatMarkdown';
import { resultError, sizeText } from './chatFormat';
import { CHAT_SURFACE_1 } from './chatSurfaces';

export type TranscriptLoader = (conversationId: string, seq: number) => Promise<TieredTranscriptCall>;

export interface ChatThreadProps {
  conversationId: string;
  messages: ChatMessage[];
  /** The tool call waiting for the user's yes or no, if any. */
  pending: ChatPendingCall | null;
  /** A turn is in flight: the bot is thinking or running a tool. */
  working: boolean;
  onConfirm: (approved: boolean) => void;
  /** Test seam; production reads the reply's stored transcript. */
  transcriptLoader?: TranscriptLoader;
  /** Extra classes on the root — the page makes it the scroll box. */
  className?: string;
  /** Classes on the content inside the scroll box: its cap, centering and insets. */
  contentClassName?: string;
  /** Handed the root (the scroll box) when it mounts, null when it goes,
   *  so the page can measure it — the width its scrollbar takes. */
  onScrollBox?: (element: HTMLDivElement | null) => void;
}

// The conversation, oldest first: the user's lines as quiet right-hand
// blocks, and every step the bot took — each LLM reply and each tool
// call — as bare text under a step line, no backdrop and no width cap
// (owner request 2026-09-24, replacing the 2026-09-23 cards). Steps
// count from 1 after each of the user's lines, and the line says what
// the step was: "Step 1: LLM decided to call a tool", "Step 2: tool
// call", "Step 3: LLM decided to say something". A reply that asks for
// several tools is followed by one tool step per call, in the order
// they ran (owner decision 2026-10-12: separate steps, not one batch).
//
// Every LLM call is one bot reply, and only LLM calls cost tokens
// (owner decision 2026-09-23): each reply ends with its token line,
// which opens the call's transcript — the exact prompt and reply — in
// the run pages' own format, under it; a reply that only asked for
// tools says so in words, since it has no text of its own. A tool step
// costs nothing and ends with a plain "This step used 0 tokens" line
// that opens nothing (owner request 2026-09-23; no rules between
// steps). While the bot works, three pulsing dots stand where its
// reply will be. A tool call held for the user's yes is the next tool
// step already, with a "decision: approve | decline" line in place of
// its output (owner request 2026-09-24), and every tool step carries a
// "status" line — waiting, processing, succeeded or failed — in the run
// history's status colors (owner request 2026-09-24).
//
// The user's lines sit against the right edge, capped at 85% of the
// width, so they read as the other voice; the bot's steps run the full
// width from the left. A long unbroken word (a pasted token, a URL)
// breaks inside itself anywhere on the thread rather than widening it
// (owner bug report 2026-09-23).
//
// A summary row (2026-10-13) is a bot step too — "LLM summarized the
// conversation" — and nothing but its step line and its token line
// (owner request 2026-10-14): the summary text is in the transcript
// the token line opens. A failed one says so in red and leaves the
// model seeing everything. A /compact the user typed shows as the
// user's own line before it, like any message.
//
// A side question (/btw, 2026-10-16) is the user's line with a "/btw"
// mark in front, and its answer a bot step — "LLM answered the side
// question" — with a caution line saying the LLM will not see the
// exchange in later turns (the server leaves both rows out of every
// later request). Everything else about the step is as for a reply.
//
// The root is the scroll box (the page bounds its height): whenever
// the conversation changes or grows, it scrolls to its own bottom, so
// nothing else on the page moves.
export const ChatThread = ({
  conversationId,
  messages,
  pending,
  working,
  onConfirm,
  transcriptLoader = chatApi.getTranscript,
  className,
  contentClassName,
  onScrollBox,
}: ChatThreadProps) => {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const setRoot = useCallback(
    (element: HTMLDivElement | null) => {
      rootRef.current = element;
      onScrollBox?.(element);
    },
    [onScrollBox],
  );

  // The answer the user clicked on the held call: while the server is
  // taking it (`working`, same call), the decision line reads
  // "approved" or "declined" and the status line "processing". Once the
  // request ends — the call ran, or it failed and the call is held
  // again — or another call is held, the click no longer applies and
  // the question is asked afresh.
  const [clicked, setClicked] = useState<{ callId: string; approved: boolean } | null>(null);
  const chosen = working && clicked != null && clicked.callId === pending?.call_id ? clicked.approved : null;
  const decide = (approved: boolean) => {
    if (pending) {
      setClicked({ callId: pending.call_id, approved });
    }
    onConfirm(approved);
  };

  // Tool rows only carry the call id; the arguments live on the
  // assistant row that made the call.
  const argsByCall = useMemo(() => {
    const map: Record<string, Record<string, unknown>> = {};
    for (const message of messages) {
      for (const call of message.tool_calls ?? []) {
        map[call.id] = call.arguments;
      }
    }
    return map;
  }, [messages]);

  // The rows shown as steps: a call the user's stop answered instead of
  // ran is no step — the stopped line that follows names it as the step
  // that was about to run (2026-10-12).
  const shown = useMemo(() => messages.filter((message) => !isSkippedCall(message)), [messages]);

  // Each bot step's number: 1, 2, 3… after every line of the user's
  // (0 for the user's own line; the "stopped" line is no step and
  // keeps the count where it was).
  const stepNumbers = useMemo(
    () =>
      shown.reduce<number[]>((numbers, message) => {
        const previous = numbers.at(-1) ?? 0;
        return [...numbers, message.role === 'user' ? 0 : message.role === 'stopped' ? previous : previous + 1];
      }, []),
    [shown],
  );

  useEffect(() => {
    // Land at the newest line, scrolling only this box — never the page.
    const root = rootRef.current;
    if (root) {
      root.scrollTop = root.scrollHeight;
    }
  }, [conversationId, messages.length, pending, working]);

  return (
    <div
      ref={setRoot}
      className={cn('min-w-0 [overflow-wrap:anywhere]', className)}
      data-testid="chat-thread"
    >
      {/* The scroll box runs the column's full width so a wheel or drag
          anywhere beside the text scrolls it; the text itself is capped
          and centered (owner request 2026-09-26). */}
      <div className={cn('flex min-w-0 flex-col gap-4', contentClassName)} data-testid="chat-thread-content">
        {shown.map((message, index) => (
          <MessageRow
            key={message.seq}
            message={message}
            step={stepNumbers[index]}
            args={argsByCall}
            loadTranscript={() => transcriptLoader(conversationId, message.seq)}
            stopped={message.role === 'stopped' ? describeStop(messages, message) : null}
          />
        ))}
        {pending ? (
          <ToolStep
            testId="chat-pending"
            step={(stepNumbers.at(-1) ?? 0) + 1}
            name={pending.name}
            inputs={pending.input}
            decision={chosen == null ? 'ask' : chosen ? 'approved' : 'declined'}
            status={working ? 'processing' : 'waiting'}
            onDecide={working ? undefined : decide}
          />
        ) : null}
        {working && !pending ? <TypingDots /> : null}
      </div>
    </div>
  );
};

// The bot's reply-to-be: three dots pulsing in turn. (Also the
// command note's "still measuring" sign, under its own test id.)
export const TypingDots = ({ testId = 'chat-working' }: { testId?: string }) => (
  <p className="flex items-center gap-1 py-1" data-testid={testId} aria-label="…">
    {[0, 150, 300].map((delay) => (
      <span
        key={delay}
        className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-4"
        style={{ animationDelay: `${delay}ms` }}
      />
    ))}
  </p>
);

// A token line that opens nothing: a step's cost as plain text, in the
// same size and color as the clickable one.
const PlainUsage = ({ text }: { text: string }) => (
  <div className="text-xs">
    <p className="text-ink-5" data-testid="chat-usage">
      {text}
    </p>
  </div>
);

// The step line every bot step opens with: a size up from the reply
// text and the brightest gray on the page, so it reads as a heading
// over the step and not as one more line of it (owner request
// 2026-09-24). Everything under it is indented one step in, and what a
// fold under that opens is indented one more (owner request
// 2026-09-24): the token line's transcript, then an input's text.
const StepLine = ({ text }: { text: string }) => <p className="text-base font-semibold text-ink-1">{text}</p>;
const STEP_BODY = 'flex min-w-0 flex-col gap-2 pl-4';
const FOLD_INDENT = 'pl-4';
/** The box an opened input/output sits in: level-1 backdrop, one indent in from its line. */
const FOLD_CONTENT = cn(CHAT_SURFACE_1, 'ml-4');
// A fact line: quiet label, bright value — the transcript's styling.
const FACT_LABEL = 'text-ink-4';
const FACT_VALUE = 'font-semibold text-ink-1';
const FOLD_TEXT = 'min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere] text-[11px] text-ink-3';

const MessageRow = ({
  message,
  step,
  args,
  loadTranscript,
  stopped,
}: {
  message: ChatMessage;
  /** The bot step's number since the user's last line; 0 for the user's own line. */
  step: number;
  args: Record<string, Record<string, unknown>>;
  loadTranscript: () => Promise<TieredTranscriptCall>;
  /** Stopped rows: what the stop landed on and what would have followed. */
  stopped?: StopFacts | null;
}) => {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end" data-testid="chat-user">
        <p className={cn('min-w-0 max-w-[85%] whitespace-pre-wrap rounded px-4 py-2.5 text-sm leading-relaxed text-ink-1', CHAT_SURFACE_1)}>
          {message.side_question ? (
            <>
              <span className="font-mono text-xs font-semibold text-caution" data-testid="chat-side-question-mark">
                /btw
              </span>{' '}
            </>
          ) : null}
          {message.text}
        </p>
      </div>
    );
  }
  if (message.role === 'stopped') {
    return <StoppedLine step={step} facts={stopped ?? { skipped: [], last: false }} />;
  }
  if (message.role === 'summary') {
    return <SummaryRow message={message} step={step} loadTranscript={loadTranscript} />;
  }
  if (message.role === 'tool') {
    return (
      <ToolStep
        step={step}
        name={message.name ?? ''}
        // The inputs with every default filled in, when the backend
        // recorded them (2026-09-24); for older rows, and when the
        // model's arguments never parsed, what the model sent.
        inputs={message.input ?? args[message.tool_call_id ?? ''] ?? {}}
        output={{
          text: typeof message.output === 'string' ? message.output : JSON.stringify(message.output, null, 2),
          chars: message.output_chars,
          truncated: message.truncated === true,
        }}
        decision={message.approved == null ? null : message.approved ? 'approved' : 'declined'}
        status={resultError(message.output) == null ? 'succeeded' : 'failed'}
      />
    );
  }
  return <ReplyRow message={message} step={step} loadTranscript={loadTranscript} />;
};

// A tool row the user's stop answered instead of ran: the server stores
// it so the model sees no open call, but the page shows it only through
// the stopped line's words.
const isSkippedCall = (message: ChatMessage): boolean =>
  message.role === 'tool' && resultError(message.output) === 'stopped';

/** What a stopped row stands for: the steps that were about to run. */
interface StopFacts {
  /** The names of the calls the stop skipped, in the order they would have run. */
  skipped: string[];
  /** The stop landed after the turn's last step (a final reply, or a requested summary): nothing was cut. */
  last: boolean;
}

// The skipped calls are read off the rows: the tool rows right before
// the stopped row. Whether the step was the last is the server's word
// (the row's `late`), never read off the row before it — the page used
// to take an assistant reply with no tool calls as the sign, and so
// called a requested summary "about to let the LLM decide" when the
// summary was the whole turn (owner bug report 2026-10-14).
const describeStop = (messages: ChatMessage[], stopped: ChatMessage): StopFacts => {
  const skipped: string[] = [];
  for (let index = messages.indexOf(stopped) - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!isSkippedCall(message)) {
      break;
    }
    skipped.unshift(message.name ?? '');
  }
  return { skipped, last: stopped.late === true };
};

// The line that ends a turn the user stopped: quiet, centered, in the
// caution color — a fact about the conversation, not one of its voices
// (2026-10-12). It names the step the stop landed on (`step`: the last
// one shown, which the server let finish) and what the next step would
// have been: the calls the model had asked for that never ran, each as
// the step it would have been — and nothing beyond those (owner
// decision 2026-10-12: no guessing past what the model asked for); or,
// when every call had run, the LLM call that always follows a finished
// batch; or, when the server says the stop landed after the last step
// (`late`: a final reply, or a requested summary), that it was the
// last step. The model sees the same row as a user line saying the
// reply was stopped (or that it had already finished), so it does not
// pick the old work back up.
const StoppedLine = ({ step, facts }: { step: number; facts: StopFacts }) => {
  const { t } = useUiLanguage();
  const next = facts.last
    ? t('chat.stopped.last')
    : facts.skipped.length === 0
      ? t('chat.stopped.nextLlm', { n: step + 1 })
      : null;
  const sentences = [
    t('chat.stopped.during', { n: step }),
    ...facts.skipped.map((tool, index) => t('chat.stopped.nextTool', { n: step + index + 1, tool })),
    ...(next ? [next] : []),
  ];
  return (
    <p className="py-1 text-center text-xs text-caution" data-testid="chat-stopped">
      {sentences.join(' ')}
    </p>
  );
};

// One LLM call: its step line — "LLM decided to call N tools" when it
// asked for tools, "LLM decided to say something" when it answered,
// "LLM call failed" when it errored — then what it said, if anything
// (a tool-only reply names no tools: the tool step right after it
// does, owner request 2026-09-24); then its token line, which opens
// the call's transcript under it — without the "LLM call" title or the
// "for: chat" fact, which never vary here (owner request 2026-09-24).
// A reply from before the app kept transcripts opens too — its facts
// show, and its folds say the text was not kept (owner request
// 2026-09-23).
const ReplyRow = ({
  message,
  step,
  loadTranscript,
}: {
  message: ChatMessage;
  step: number;
  loadTranscript: () => Promise<TieredTranscriptCall>;
}) => {
  const { t } = useUiLanguage();
  const [open, setOpen] = useState(false);
  const usage = message.usage;
  const hasUsage = usage != null && (usage.input_tokens != null || usage.output_tokens != null);
  const hasTranscript = message.transcript_chars != null;
  const canOpen = hasUsage || hasTranscript;
  // "This step used N tokens", in the same words, size and color as the
  // run page's "This run used N LLM calls (M tokens)" line (owner
  // request 2026-09-23); the in/out split is on the card it opens.
  const usageText = hasUsage
    ? t('chat.usage', { tokens: (usage.input_tokens ?? 0) + (usage.output_tokens ?? 0) })
    : t('chat.step.noUsage');
  const stepText = message.error
    ? t('chat.step.failed', { n: step })
    : message.side_question
      ? t('chat.step.sideQuestion', { n: step })
      : (message.tool_calls ?? []).length > 0
        ? t('chat.step.tool', { n: step })
        : t('chat.step.say', { n: step });
  return (
    <section data-testid="chat-assistant" className="flex min-w-0 flex-col gap-2">
      <StepLine text={stepText} />
      <div className={STEP_BODY}>
        {message.error ? (
          <p className="text-sm text-negative">{message.text}</p>
        ) : message.text ? (
          <div className="text-sm leading-relaxed text-ink-2">
            <ChatMarkdown text={message.text} />
          </div>
        ) : null}
        {message.side_question ? (
          <p className="text-xs text-caution" data-testid="chat-side-question-note">
            {t('chat.sideQuestion.note')}
          </p>
        ) : null}
        {message.notice === 'tool_call_limit' ? (
          <p className="text-xs text-caution">{t('chat.notice.toolCallLimit')}</p>
        ) : null}
        {message.notice === 'wrong_language' ? (
          <p className="text-xs text-caution">{t('chat.notice.wrongLanguage')}</p>
        ) : null}
        {canOpen ? (
          <UsageLine
            label={usageText}
            help={t('chat.help.usage')}
            open={open}
            onToggle={() => setOpen((was) => !was)}
            testId="chat-usage"
          >
            {open ? (
              <div data-testid="chat-transcript" className={cn('mt-3 flex min-w-0 flex-col text-xs', FOLD_INDENT)}>
                <TranscriptCall
                  showTitle={false}
                  showStage={false}
                  item={{
                    call_number: message.seq,
                    created_at: message.created_at,
                    stage: message.side_question ? 'side_question' : 'chat',
                    llm: message.llm ?? null,
                    temperature: null,
                    time_ms: message.time_ms ?? null,
                    input_tokens: usage?.input_tokens ?? null,
                    output_tokens: usage?.output_tokens ?? null,
                    structured: null,
                    error: message.error ?? null,
                  }}
                  load={loadTranscript}
                  missing={hasTranscript ? undefined : t('chat.transcript.missing')}
                  foldSurface={FOLD_CONTENT}
                />
              </div>
            ) : null}
          </UsageLine>
        ) : null}
      </div>
    </section>
  );
};

// One summary call (2026-10-13): the step line says the LLM summarized
// the conversation (or that the summary failed), a caution line names
// the messages the summary stands for and that the model now sees it
// in their place, then the summary itself and its token line opening
// the call's transcript. A failed summary shows its error in red and
// says the model still sees every message.
const SummaryRow = ({
  message,
  step,
  loadTranscript,
}: {
  message: ChatMessage;
  step: number;
  loadTranscript: () => Promise<TieredTranscriptCall>;
}) => {
  const { t } = useUiLanguage();
  const [open, setOpen] = useState(false);
  const usage = message.usage;
  const hasUsage = usage != null && (usage.input_tokens != null || usage.output_tokens != null);
  const canOpen = hasUsage || message.transcript_chars != null;
  return (
    <section data-testid="chat-summary" className="flex min-w-0 flex-col gap-2">
      <StepLine text={message.error ? t('chat.step.summaryFailed', { n: step }) : t('chat.step.summary', { n: step })} />
      <div className={STEP_BODY}>
        {message.error ? (
          <>
            <p className="text-sm text-negative">{message.error}</p>
            <p className="text-xs text-caution">{t('chat.summary.failed')}</p>
          </>
        ) : null}
        {canOpen ? (
          <UsageLine
            label={hasUsage ? t('chat.usage', { tokens: (usage.input_tokens ?? 0) + (usage.output_tokens ?? 0) }) : t('chat.step.noUsage')}
            help={t('chat.help.usage')}
            open={open}
            onToggle={() => setOpen((was) => !was)}
            testId="chat-usage"
          >
            {open ? (
              <div data-testid="chat-transcript" className={cn('mt-3 flex min-w-0 flex-col text-xs', FOLD_INDENT)}>
                <TranscriptCall
                  showTitle={false}
                  showStage={false}
                  item={{
                    call_number: message.seq,
                    created_at: message.created_at,
                    stage: 'summary',
                    llm: message.llm ?? null,
                    temperature: null,
                    time_ms: message.time_ms ?? null,
                    input_tokens: usage?.input_tokens ?? null,
                    output_tokens: usage?.output_tokens ?? null,
                    structured: null,
                    error: message.error ?? null,
                  }}
                  load={loadTranscript}
                  foldSurface={FOLD_CONTENT}
                />
              </div>
            ) : null}
          </UsageLine>
        ) : null}
      </div>
    </section>
  );
};

type Decision = 'ask' | 'approved' | 'declined';

const DECISION_TEXT = {
  approved: 'chat.tool.approved',
  declined: 'chat.tool.declined',
} as const;

// Approve/approved in the outlook palette's green, decline/declined in
// its red (styles.ts OUTLOOK_TEXT: bullish emerald-300, bearish red-300).
const DECISION_COLOR: Record<Decision, string> = {
  ask: '',
  approved: 'text-positive',
  declined: 'text-negative',
};

// Where the tool call stands: waiting for the user's answer, processing
// (the answer is with the server, or the tool is running), done, or
// failed (the tool answered with an error). Colored as the run history
// colors a run's status (RunHistory.tsx: queued amber-300, running
// sky-300, succeeded emerald-300, failed red-300) — owner request 2026-09-24.
type Status = 'waiting' | 'processing' | 'succeeded' | 'failed';

const STATUS_TEXT: Record<Status, `chat.tool.status.${Status}`> = {
  waiting: 'chat.tool.status.waiting',
  processing: 'chat.tool.status.processing',
  succeeded: 'chat.tool.status.succeeded',
  failed: 'chat.tool.status.failed',
};

const STATUS_COLOR: Record<Status, string> = {
  waiting: 'text-caution',
  processing: 'text-info',
  succeeded: 'text-positive',
  failed: 'text-negative',
};

// One tool call, in the same shape as an LLM call's transcript (owner
// request 2026-09-23): its step line, then the name fact line in the
// quiet-label / bright-value styling, then two more lines in that same
// styling that open: "input: 12 B ▸" is the inputs — every default
// filled in, as the tool ran them — and "output: 1.4 KB ▸" is what
// came back (owner request 2026-09-24 — no time or output-size facts,
// no titled folds with their own backdrop). Opened, the whole text
// shows on the fold surface, no inner scroll box. Last, the step's
// token line: always 0, and not a button.
//
// A call held for the user's yes is this same step before its output
// exists (owner request 2026-09-24, replacing the question card): a
// "decision: approve | decline" line above the input, which turns into
// the clicked word — "approved" or "declined" — the moment one is
// clicked; the finished row keeps that word. A tool that needed no
// permission has no decision line. Under the decision (or, without
// one, under the name) sits "status": waiting while the call is held,
// processing once the answer is on its way, then succeeded or failed
// (owner request 2026-09-24). A failure has no line of its own: the
// red status says it failed and the output fold holds the error code
// and message (owner request 2026-09-25).
const ToolStep = ({
  step,
  name,
  inputs,
  output,
  decision,
  status,
  onDecide,
  testId = 'chat-tool',
}: {
  step: number;
  name: string;
  inputs: Record<string, unknown>;
  /** Absent while the call is still held: nothing has come back yet. */
  output?: { text: string; chars: number | null | undefined; truncated: boolean };
  decision: Decision | null;
  status: Status;
  /** Absent while the answer is with the server: the buttons still show, but do nothing. */
  onDecide?: (approved: boolean) => void;
  testId?: string;
}) => {
  const { t } = useUiLanguage();
  const inputText = JSON.stringify(inputs, null, 2);
  return (
    <section data-testid={testId} className="flex min-w-0 flex-col gap-2 text-xs">
      <StepLine text={t('chat.step.toolCall', { n: step })} />
      <div className={STEP_BODY}>
        <div className="flex flex-col gap-0.5">
          <span className={FACT_LABEL}>
            {t('chat.tool.name')}
            {': '}
            <span className={FACT_VALUE}>{name}</span>
          </span>
          {decision ? <DecisionLine decision={decision} onDecide={onDecide} /> : null}
          <span className={FACT_LABEL} data-testid="chat-tool-status">
            {t('chat.tool.status')}
            {': '}
            <span className={cn(FACT_VALUE, STATUS_COLOR[status])}>{t(STATUS_TEXT[status])}</span>
          </span>
          <FactFold
            label={t('chat.tool.input')}
            value={sizeText(inputText.length)}
            testId="chat-tool-input"
            surfaceClassName={FOLD_CONTENT}
          >
            <pre className={FOLD_TEXT}>{inputText}</pre>
          </FactFold>
          {output ? (
            <FactFold
              label={t('chat.tool.output')}
              value={sizeText(output.chars)}
              testId="chat-tool-output"
              surfaceClassName={FOLD_CONTENT}
            >
              {output.truncated ? <p className="text-caution">{t('chat.tool.truncated')}</p> : null}
              <pre className={FOLD_TEXT}>{output.text}</pre>
            </FactFold>
          ) : null}
        </div>
        {output ? <PlainUsage text={t('chat.usage', { tokens: 0 })} /> : null}
      </div>
    </section>
  );
};

// "decision: approve | decline" while the call waits, then the answer
// given, in the fact line's own styling. Approve is green and decline
// is red — the outlook palette's bullish and bearish text colors (owner
// request 2026-09-24) — and the settled word keeps the color of the
// answer given. The two answers are buttons inside one bold span:
// index.css resets a button's font to its parent's, so the weight has
// to come from the span around them. Without an `onDecide` (the answer
// is already with the server) the buttons are disabled.
const DecisionLine = ({ decision, onDecide }: { decision: Decision; onDecide?: (approved: boolean) => void }) => {
  const { t } = useUiLanguage();
  return (
    <span className={FACT_LABEL} data-testid="chat-tool-decision">
      {t('chat.tool.decision')}
      {': '}
      {decision === 'ask' ? (
        <span className="font-semibold">
          <button
            type="button"
            data-testid="chat-pending-yes"
            disabled={onDecide == null}
            onClick={() => onDecide?.(true)}
            className={cn('cursor-pointer hover:text-positive-hover disabled:cursor-default', DECISION_COLOR.approved)}
          >
            {t('chat.tool.approve')}
          </button>
          <span className="mx-1.5 text-ink-5">|</span>
          <button
            type="button"
            data-testid="chat-pending-no"
            disabled={onDecide == null}
            onClick={() => onDecide?.(false)}
            className={cn('cursor-pointer hover:text-negative-hover disabled:cursor-default', DECISION_COLOR.declined)}
          >
            {t('chat.tool.decline')}
          </button>
        </span>
      ) : (
        <span className={cn(FACT_VALUE, DECISION_COLOR[decision])}>{t(DECISION_TEXT[decision])}</span>
      )}
    </span>
  );
};
