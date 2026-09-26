import { useCallback, useEffect, useState, type CSSProperties } from 'react';
import axios from 'axios';
import { chatApi, type ChatConversation, type ChatConversationSummary } from '../api/chat';
import { ChatComposer } from '../components/chat/ChatComposer';
import { ChatSidebar } from '../components/chat/ChatSidebar';
import { ChatThread } from '../components/chat/ChatThread';
import { HeaderControls } from '../components/common/HeaderControls';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { useElementHeight } from '../hooks/useElementHeight';
import { cn } from '../utils/cn';

// The chat page, laid out like a chat app: the left panel — the
// history — runs the window's full height against its left edge; the
// conversation takes all the rest, with no backdrop behind it (owner
// requests 2026-09-23 and 2026-09-26). The conversation's scroll box
// spans that whole space, so a wheel or drag anywhere beside the text
// scrolls it, while the text and bubbles are capped at CHAT_MAX_WIDTH —
// the width they had inside the analysis page's column on a 1440px
// window — and centered. Two things float over the scroll box, each on
// a shade that darkens whatever scrolls beneath it and reaches only a
// little way past its edges: the message box over its bottom (owner
// request 2026-09-26), and the mode, language and color menus — the
// same buttons as the analysis page's header — in its top right corner
// (owner request 2026-09-27). The text keeps a
// top inset the size of the menus' band and a bottom inset the size of
// the message box's dock, so its first and last lines can still scroll
// clear of them. On a phone the panel is a short band above the chat. The page fills the window and never scrolls as a whole;
// the list and the conversation each scroll on their own, and opening
// a conversation lands at its bottom. A conversation is only created on the first
// message, so visiting the page never leaves empty rows behind.
//
// Sending shows the user's line at once and three pulsing dots where
// the reply will be; the server's answer — the whole conversation —
// then replaces both, so the page never has to merge partial updates.
// Each yes/no to a held action is one such request too.
//
// Steps arrive one by one (owner request 2026-09-25): while the request
// runs, the page peeks at the conversation every TURN_POLL_MS — the
// server stores each step the moment it finishes — and shows every step
// stored so far, dots after the last one. A peek never shows a held
// call: its buttons could not be answered until the request returns,
// so the request's own answer brings it (a moment later) and the dots
// stay until then. A peek that fails changes nothing.
const TURN_POLL_MS = 800;

// The text's cap: the analysis page's 1280px column less its 32px side
// paddings, the 256px history and the 16px gap.
const CHAT_MAX_WIDTH = 'max-w-[59rem]';
/** The text's frame inside the scroll box: capped, centered, inset from the edges. */
const CHAT_FRAME = cn('mx-auto w-full px-4', CHAT_MAX_WIDTH);
// The shade under a floating control: a dark mat behind it and a soft
// dark halo reaching a little way past its edges, so the text scrolling
// beneath is dimmed there and only there (owner request 2026-09-27: no
// strip across the whole width).
const FLOAT_SHADE = 'rounded-2xl bg-background/85 shadow-[0_0_40px_28px_hsl(var(--background)/0.85)]';

// Peek at the conversation on a timer until stopped, handing each longer
// version to `apply`. Returns the stop function; a peek in flight when
// stopped is dropped, so nothing lands after the request's own answer.
const peekWhileWorking = (id: string, apply: (fresh: ChatConversation) => void): (() => void) => {
  let live = true;
  let inFlight = false;
  const timer = window.setInterval(async () => {
    if (inFlight) {
      return;
    }
    inFlight = true;
    try {
      const fresh = await chatApi.getConversation(id);
      if (live) {
        apply({ ...fresh, pending: null });
      }
    } catch {
      // The turn's own answer — or its error — is what the page reports.
    } finally {
      inFlight = false;
    }
  }, TURN_POLL_MS);
  return () => {
    live = false;
    window.clearInterval(timer);
  };
};

const ChatPage = () => {
  const { language, t } = useUiLanguage();
  const [conversations, setConversations] = useState<ChatConversationSummary[]>([]);
  const [conversation, setConversation] = useState<ChatConversation | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The band the menus float in and the dock the message box floats
  // in; their heights are the text's top and bottom insets.
  const [band, setBand] = useState<HTMLDivElement | null>(null);
  const bandHeight = useElementHeight(band);
  const [dock, setDock] = useState<HTMLDivElement | null>(null);
  const dockHeight = useElementHeight(dock);

  const refreshList = useCallback(async () => {
    try {
      setConversations(await chatApi.listConversations());
    } catch (listError) {
      setError(describe(listError, t));
    }
  }, [t]);

  useEffect(() => {
    void refreshList();
  }, [refreshList]);

  const open = useCallback(
    async (id: string) => {
      setError(null);
      try {
        setConversation(await chatApi.getConversation(id));
      } catch (openError) {
        setError(describe(openError, t));
      }
    },
    [t],
  );

  const startNew = () => {
    setConversation(null);
    setError(null);
  };

  // One turn against `target`: the server's answer replaces the shown
  // conversation. On failure, the server may have stored part of the
  // turn (the user's line, a tool's result); show what it has.
  const applyTurn = async (target: ChatConversation, turn: () => Promise<ChatConversation>) => {
    setWorking(true);
    setError(null);
    // Only a longer conversation is news; the same length is what the
    // page already shows (the user's own line, added before sending).
    const stopPeeking = peekWhileWorking(target.id, (fresh) =>
      setConversation((shown) => (shown?.id === fresh.id && fresh.messages.length > shown.messages.length ? fresh : shown)),
    );
    try {
      setConversation(await turn().finally(stopPeeking));
      await refreshList();
    } catch (turnError) {
      setError(describe(turnError, t));
      try {
        setConversation(await chatApi.getConversation(target.id));
      } catch {
        // keep what we had
      }
    } finally {
      setWorking(false);
    }
  };

  const send = (text: string) =>
    void (async () => {
      let target = conversation;
      if (!target) {
        setWorking(true);
        setError(null);
        try {
          target = await chatApi.createConversation();
        } catch (createError) {
          setError(describe(createError, t));
          setWorking(false);
          return;
        }
      }
      const base = target;
      const lastSeq = base.messages.at(-1)?.seq ?? 0;
      // The user's line, in view before the server has seen it.
      setConversation({
        ...base,
        messages: [...base.messages, { seq: lastSeq + 1, role: 'user', created_at: null, text }],
      });
      await applyTurn(base, () => chatApi.sendMessage(base.id, text, language));
    })();

  const confirm = (approved: boolean) => {
    if (!conversation) {
      return;
    }
    void applyTurn(conversation, () => chatApi.confirm(conversation.id, approved, language));
  };

  const remove = async (id: string) => {
    setError(null);
    try {
      await chatApi.deleteConversation(id);
    } catch (deleteError) {
      setError(describe(deleteError, t));
      return;
    }
    if (conversation?.id === id) {
      setConversation(null);
    }
    await refreshList();
  };

  const pending = conversation?.pending?.calls[0] ?? null;

  return (
    <main className="grid min-h-0 w-full flex-1 grid-cols-1 grid-rows-[auto_minmax(0,1fr)] md:grid-cols-[16rem_minmax(0,1fr)] md:grid-rows-1">
      {/* On a phone the panel takes a short band above the chat; side by side it takes the full height. */}
      <aside className="flex max-h-56 min-h-0 flex-col md:max-h-none">
        <ChatSidebar
          conversations={conversations}
          activeId={conversation?.id ?? null}
          onSelect={(id) => void open(id)}
          onNew={startNew}
          onDelete={(id) => void remove(id)}
        />
      </aside>
      {/* min-w-0: a long unbroken string in a transcript must wrap, not widen the page. */}
      <section
        className="relative min-h-0 min-w-0 text-ink-3"
        style={
          {
            ...(bandHeight > 0 ? { '--chat-band-height': `${bandHeight}px` } : {}),
            ...(dockHeight > 0 ? { '--chat-dock-height': `${dockHeight}px` } : {}),
          } as CSSProperties
        }
        data-testid="chat-column"
      >
        {conversation && conversation.messages.length > 0 ? (
          <ChatThread
            conversationId={conversation.id}
            messages={conversation.messages}
            pending={pending}
            working={working}
            onConfirm={confirm}
            className="h-full overflow-y-auto"
            contentClassName={cn('pt-[var(--chat-band-height,4rem)] pb-[var(--chat-dock-height,8rem)]', CHAT_FRAME)}
          />
        ) : (
          // What the agent is, centered in the empty thread (owner
          // request 2026-09-26) — not a heading in the corner.
          <div className="flex h-full items-center justify-center px-6 py-6" data-testid="chat-empty">
            <p className="max-w-prose text-center text-sm leading-relaxed text-ink-3">
              {t('chat.empty.hint')}
            </p>
          </div>
        )}
        {/* The band: the menus in the top right corner, each cluster on its own shade; only the buttons take clicks. */}
        <div ref={setBand} className="pointer-events-none absolute right-0 top-0 px-4 pb-6 pt-4" data-testid="chat-band">
          <div className={cn('pointer-events-auto p-1', FLOAT_SHADE)} data-testid="chat-band-content">
            <HeaderControls />
          </div>
        </div>
        {/* The dock: the wheel passes through outside the box's shade; only the box itself takes clicks. */}
        <div ref={setDock} className="pointer-events-none absolute inset-x-0 bottom-0 pb-4 pt-10" data-testid="chat-dock">
          <div className={CHAT_FRAME}>
            <div className={cn('pointer-events-auto flex flex-col gap-3', FLOAT_SHADE)} data-testid="chat-dock-content">
              {error ? (
                <p className="text-xs text-caution" data-testid="chat-error">
                  {error}
                </p>
              ) : null}
              <ChatComposer
                disabled={working || pending !== null}
                disabledHint={pending ? t('chat.composer.waitConfirm') : null}
                onSend={send}
              />
            </div>
          </div>
        </div>
      </section>
    </main>
  );
};

// What went wrong, in the page's words: the server's own code when it
// gave one (busy, no model), else the parsed message.
function describe(error: unknown, t: (key: 'chat.error.busy' | 'chat.error.notConfigured' | 'chat.error.send', params?: Record<string, string>) => string): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as
      | { detail?: { code?: string; error?: string }; error?: string; message?: string }
      | undefined;
    const code = data?.detail?.code ?? data?.detail?.error ?? data?.error;
    if (code === 'busy') {
      return t('chat.error.busy');
    }
    if (code === 'llm_not_configured') {
      return t('chat.error.notConfigured');
    }
    const parsed = (error as { parsedError?: { message?: string } }).parsedError?.message;
    return t('chat.error.send', { error: parsed ?? data?.message ?? error.message });
  }
  return t('chat.error.send', { error: error instanceof Error ? error.message : String(error) });
}

export default ChatPage;
