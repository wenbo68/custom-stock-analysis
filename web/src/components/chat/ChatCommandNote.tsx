import type { ChatContextUsage } from '../../api/chat';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { CHAT_COMMANDS } from './commands';
import { CHAT_SURFACE_1 } from './chatSurfaces';
import { TypingDots } from './ChatThread';

// What a page-side command answers with (owner request 2026-10-13):
// /help lists the commands, /context sizes the next request against
// the model's max. The answer is a quiet panel under the message box
// (owner request 2026-10-15: part of the box, not of the thread), in
// the fact-line styling of a tool step — quiet label, bright value —
// and it is the page's, not the conversation's: nothing is stored, the
// model never sees it, and the next message or command replaces it.
// A /context still being measured is the pulsing dots alone, the same
// sign as a reply still being written (owner request 2026-10-15: the
// server takes a moment, unlike /help).
export type ChatNote = { kind: 'help' } | { kind: 'context'; usage: ChatContextUsage | null };

const FACT_LABEL = 'text-ink-4';
const FACT_VALUE = 'font-semibold text-ink-1';

const tokens = (n: number): string => n.toLocaleString('en-US');

export const ChatCommandNote = ({ note }: { note: ChatNote }) => {
  return (
    <section className={cn('flex min-w-0 flex-col gap-2 rounded px-4 py-3 text-xs', CHAT_SURFACE_1)} data-testid={`chat-note-${note.kind}`}>
      {note.kind === 'help' ? <HelpLines /> : <ContextLines usage={note.usage} />}
    </section>
  );
};

const HelpLines = () => {
  const { t } = useUiLanguage();
  return (
    <>
      <p className="text-sm font-semibold text-ink-1">{t('chat.command.help.title')}</p>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1">
        {CHAT_COMMANDS.map((command) => (
          <div key={command.name} className="contents">
            <dt className={cn('font-mono', FACT_VALUE)}>
              /{command.name}
              {command.argumentKey ? <span className={cn('font-normal', FACT_LABEL)}> &lt;{t(command.argumentKey)}&gt;</span> : null}
            </dt>
            <dd className={FACT_LABEL}>{t(command.descriptionKey)}</dd>
          </div>
        ))}
      </dl>
    </>
  );
};

// Three lines, as sums (owner request 2026-10-15): the model; the
// window as "window - reserved = max", where the reserve is whatever
// the max leaves of the window — the table's output limit, or half the
// window when no usable output limit is known (src/chat/context.py);
// and the usage as "used (percent) = instructions + tools +
// conversation". The bar under the title fills to the used share and
// marks the line past which the bot summarizes by itself.
const ContextLines = ({ usage }: { usage: ChatContextUsage | null }) => {
  const { t } = useUiLanguage();
  if (!usage) {
    return <TypingDots testId="chat-note-waiting" />;
  }
  const lines: [string, string][] = [
    [t('chat.context.llm'), usage.llm ?? t('chat.context.noLlm')],
    [
      t('chat.context.window'),
      t('chat.context.windowValue', {
        window: tokens(usage.window),
        reserved: tokens(usage.window - usage.max_tokens),
        max: tokens(usage.max_tokens),
      }),
    ],
    [
      t('chat.context.usage'),
      t('chat.context.usageValue', {
        used: tokens(usage.used_tokens),
        percent: usage.percent.toFixed(1),
        system: tokens(usage.system_prompt_tokens),
        tools: tokens(usage.tools_tokens),
        conversation: tokens(usage.conversation_tokens),
      }),
    ],
  ];
  return (
    <>
      <p className="text-sm font-semibold text-ink-1">{t('chat.context.title')}</p>
      <ContextBar percent={usage.percent} compactAt={usage.compact_at_percent} />
      <dl className="flex flex-col gap-1">
        {lines.map(([label, value]) => (
          <div key={label} className="flex flex-wrap gap-x-2">
            <dt className={FACT_LABEL}>{label}:</dt>
            <dd className={cn('min-w-0', FACT_VALUE)}>{value}</dd>
          </div>
        ))}
      </dl>
    </>
  );
};

// A bar: the used share filled in the page's info color until the
// summary line, in the caution color past it; a tick marks the line.
const ContextBar = ({ percent, compactAt }: { percent: number; compactAt: number }) => (
  <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-surface-2" data-testid="chat-context-bar" aria-hidden="true">
    <div
      className={cn('h-full rounded-full', percent >= compactAt ? 'bg-caution' : 'bg-info')}
      style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
    />
    <div className="absolute inset-y-0 w-px bg-ink-4" style={{ left: `${Math.min(100, compactAt)}%` }} />
  </div>
);
