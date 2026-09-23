import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { chatApi, type ChatMessage, type ChatPendingCall } from '../../api/chat';
import type { TieredTranscriptCall } from '../../api/tiered';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { Tooltip } from '../common/Tooltip';
import { AltTranscriptCall } from '../tiered-alt/AltTranscript';
import { AltCard, AltFold } from '../tiered-alt/AltUi';
import { ChatMarkdown } from './ChatMarkdown';
import { pendingQuestion, resultError, sizeText } from './chatFormat';

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
}

// The conversation, oldest first: the user's lines as quiet right-hand
// blocks, the bot's replies as plain text, and between them the trace —
// one folded line per tool call showing what was asked and what came
// back — so the reader can always check what the bot looked at.
//
// Every model call is one bot reply, and only model calls cost tokens
// (owner decision 2026-09-23): each reply ends with its token line; a
// reply that only asked for tools says so in words, since it has no
// text of its own; tool rows and the yes/no card cost nothing and carry
// no token line. A rule closes every step — a model call or a tool
// call — except the last, so the steps stand apart. The token line
// opens the call's transcript — the exact prompt and reply — in the
// run pages' own format. The question for a held action sits at the
// end with its two answers.
export const ChatThread = ({
  conversationId,
  messages,
  pending,
  working,
  onConfirm,
  transcriptLoader = chatApi.getTranscript,
}: ChatThreadProps) => {
  const { t } = useUiLanguage();
  const endRef = useRef<HTMLDivElement | null>(null);

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

  useEffect(() => {
    // Keep the newest line in view. (The test DOM has no scrolling.)
    endRef.current?.scrollIntoView?.({ block: 'end' });
  }, [messages.length, pending, working]);

  return (
    <div className="flex flex-col gap-4" data-testid="chat-thread">
      {messages.map((message, index) => (
        <Fragment key={message.seq}>
          <MessageRow
            message={message}
            args={argsByCall}
            loadTranscript={() => transcriptLoader(conversationId, message.seq)}
          />
          {/* A rule closes every step — a model call or a tool call — except the last. */}
          {message.role !== 'user' && index < messages.length - 1 ? (
            <hr className="border-gray-700" data-testid="chat-step-end" />
          ) : null}
        </Fragment>
      ))}
      {pending ? <PendingCard call={pending} working={working} onConfirm={onConfirm} /> : null}
      {working && !pending ? (
        <p className="text-xs text-gray-500" data-testid="chat-working">
          {t('chat.composer.sending')}
        </p>
      ) : null}
      <div ref={endRef} />
    </div>
  );
};

const MessageRow = ({
  message,
  args,
  loadTranscript,
}: {
  message: ChatMessage;
  args: Record<string, Record<string, unknown>>;
  loadTranscript: () => Promise<TieredTranscriptCall>;
}) => {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end" data-testid="chat-user">
        <p className="max-w-[85%] whitespace-pre-wrap rounded bg-gray-800 px-4 py-2.5 text-sm leading-relaxed text-gray-200">
          {message.text}
        </p>
      </div>
    );
  }
  if (message.role === 'tool') {
    return <ToolRow message={message} args={args[message.tool_call_id ?? ''] ?? {}} />;
  }
  return <ReplyRow message={message} loadTranscript={loadTranscript} />;
};

// One LLM call: what it said, or which tools it chose; then its token
// line, which opens the call's transcript.
const ReplyRow = ({
  message,
  loadTranscript,
}: {
  message: ChatMessage;
  loadTranscript: () => Promise<TieredTranscriptCall>;
}) => {
  const { t } = useUiLanguage();
  const [open, setOpen] = useState(false);
  const usage = message.usage;
  const hasUsage = usage != null && (usage.prompt_tokens != null || usage.completion_tokens != null);
  const hasTranscript = message.transcript_chars != null;
  // "This step used N tokens", in the same words, size and color as the
  // run page's "This run used N LLM calls (M tokens)" line (owner
  // request 2026-09-23); the in/out split is on the card it opens.
  const usageText = hasUsage
    ? t('chat.usage', { tokens: (usage.prompt_tokens ?? 0) + (usage.completion_tokens ?? 0) })
    : t('chat.round.noUsage');
  const chosen = (message.tool_calls ?? []).map((call) => call.name).join(', ');
  return (
    <div className="flex flex-col gap-1" data-testid="chat-assistant">
      {message.error ? (
        <p className="text-sm text-red-300">{message.text}</p>
      ) : message.text ? (
        <div className="text-sm leading-relaxed text-gray-300">
          <ChatMarkdown text={message.text} />
        </div>
      ) : null}
      {chosen ? (
        <p className="text-sm text-gray-400" data-testid="chat-tool-choice">
          {t('chat.round.toolChoice', { names: chosen })}
        </p>
      ) : null}
      {message.notice === 'step_cap' ? (
        <p className="text-xs text-amber-300">{t('chat.notice.stepCap')}</p>
      ) : null}
      {hasTranscript ? (
        <Tooltip
          content={<span className="block max-w-[16rem] whitespace-pre-line">{t('chat.help.usage')}</span>}
        >
          <button
            type="button"
            onClick={() => setOpen((was) => !was)}
            aria-expanded={open}
            className="self-start text-left text-xs text-gray-600 hover:text-gray-300"
            data-testid="chat-usage"
          >
            {usageText}
          </button>
        </Tooltip>
      ) : hasUsage ? (
        <p className="text-xs text-gray-600" data-testid="chat-usage">
          {usageText}
        </p>
      ) : null}
      {open ? (
        <AltCard testId="chat-transcript" className="mt-1 text-xs">
          <AltTranscriptCall
            title={t('chat.round.transcript')}
            item={{
              seq: message.seq,
              created_at: message.created_at,
              stage: 'chat',
              model: message.model ?? null,
              temperature: null,
              duration_ms: message.duration_ms ?? null,
              prompt_tokens: usage?.prompt_tokens ?? null,
              completion_tokens: usage?.completion_tokens ?? null,
              structured: null,
              error: message.error ?? null,
            }}
            load={loadTranscript}
          />
        </AltCard>
      ) : null}
    </div>
  );
};

// One tool call on the same card, in the same shape, as a model call's
// transcript (owner request 2026-09-23): the title, then fact lines
// (name, time, how much came back) in the quiet-label
// / bright-value styling, the user's answer when it waited for one, and
// Input and Output folded — shown whole when opened, no inner scroll box.
const ToolRow = ({ message, args }: { message: ChatMessage; args: Record<string, unknown> }) => {
  const { t } = useUiLanguage();
  const name = message.tool_name ?? '';
  const error = resultError(message.result);
  const facts: [string, string][] = [
    [t('chat.tool.name'), name],
    [t('chat.tool.time'), message.duration_ms == null ? '—' : `${message.duration_ms}ms`],
    [t('chat.tool.outputSize'), sizeText(message.result_chars)],
  ];
  return (
    <AltCard testId="chat-tool" className="flex min-w-0 flex-col gap-2 text-xs">
      <p className="font-semibold text-gray-300">{t('chat.tool.title')}</p>
      <p className="flex flex-col gap-0.5">
        {facts.map(([label, value]) => (
          <span key={label} className="text-gray-500">
            {label}
            {': '}
            <span className="font-semibold text-gray-200">{value}</span>
          </span>
        ))}
      </p>
      {error ? <p className="text-amber-300">{t('chat.tool.error', { name, error })}</p> : null}
      {message.approved != null ? (
        <p className={cn(message.approved ? 'text-emerald-300' : 'text-gray-500')}>
          {message.approved ? t('chat.tool.approved') : t('chat.tool.declined')}
        </p>
      ) : null}
      {Object.keys(args).length > 0 ? (
        <AltFold title={t('chat.tool.input')} className="">
          <pre className="min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere] text-[11px] text-gray-400">
            {JSON.stringify(args, null, 2)}
          </pre>
        </AltFold>
      ) : null}
      <AltFold title={t('chat.tool.output')} className="">
        {message.truncated ? <p className="text-amber-300">{t('chat.tool.truncated')}</p> : null}
        <pre className="min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere] text-[11px] text-gray-400">
          {typeof message.result === 'string' ? message.result : JSON.stringify(message.result, null, 2)}
        </pre>
      </AltFold>
    </AltCard>
  );
};

const YES_TONE: Record<'start' | 'delete' | 'read', string> = {
  start: 'text-blue-300 hover:text-blue-200',
  delete: 'text-red-300 hover:text-red-200',
  read: 'text-amber-300 hover:text-amber-200',
};

const PendingCard = ({
  call,
  working,
  onConfirm,
}: {
  call: ChatPendingCall;
  working: boolean;
  onConfirm: (approved: boolean) => void;
}) => {
  const { t } = useUiLanguage();
  const asked = pendingQuestion(call, t);
  return (
    <div className="flex flex-col gap-3 rounded bg-gray-800 px-4 py-3 text-sm text-gray-200" data-testid="chat-pending">
      <p className="leading-relaxed">{asked.question}</p>
      <div className="flex items-center gap-4 text-xs font-semibold">
        <button
          type="button"
          data-testid="chat-pending-yes"
          disabled={working}
          onClick={() => onConfirm(true)}
          className={cn('cursor-pointer disabled:cursor-default disabled:opacity-50', YES_TONE[asked.tone])}
        >
          {working ? t('chat.confirm.working') : asked.yes}
        </button>
        <button
          type="button"
          data-testid="chat-pending-no"
          disabled={working}
          onClick={() => onConfirm(false)}
          className="cursor-pointer text-gray-400 hover:text-gray-200 disabled:cursor-default disabled:opacity-50"
        >
          {t('chat.confirm.no')}
        </button>
      </div>
    </div>
  );
};
