import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';
import { chatApi, type ChatConversation, type ChatConversationSummary } from '../api/chat';
import { ChatCommandNote, type ChatNote } from '../components/chat/ChatCommandNote';
import { ChatComposer } from '../components/chat/ChatComposer';
import { ChatSidebar } from '../components/chat/ChatSidebar';
import { ChatThread } from '../components/chat/ChatThread';
import { parseInput, type ChatCommand } from '../components/chat/commands';
import { HeaderControls } from '../components/common/HeaderControls';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { useElementHeight } from '../hooks/useElementHeight';
import { useScrollbarWidth } from '../hooks/useScrollbarWidth';
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
//
// A line that starts with "/" is a command, not a message (owner
// request 2026-10-13, after Claude Code's slash commands; commands.ts
// is the table). /help and /context answer on the page, as a panel
// under the message box — part of the box, not of the thread (owner
// request 2026-10-15) — that the next message or command replaces;
// /compact is a turn against the server like a message is, and its
// answer — the conversation with its new summary step — lands the same
// way. An unknown command is an error line, and nothing is sent.
// /btw <question> (owner request 2026-10-16) is a turn too: the
// question goes into the thread as the user's line, marked, and the
// server's answer is a bot step flagged the same way — stored and
// shown, but left out of every later request, so the LLM never
// remembers the exchange. Without a question the line is refused,
// and so is one while a held call waits for the user's answer.
//
// A turn belongs to its conversation, not to the page (owner bug
// report 2026-10-15: one conversation's wait locked every other). The
// turns in flight are kept by conversation id; the box is blocked, the
// dots show and the stop button stands only when the open conversation
// is one of them, and another conversation can be opened and written
// to meanwhile. A turn's answer replaces the shown conversation only
// if it is still the one shown; otherwise it is simply dropped (the
// history list refreshes, and opening the conversation fetches it).
// While a reply is awaited the box still takes typing but sends no
// message (owner request 2026-10-15). A command typed then runs at
// once or is refused with an error line over the box, as its table
// entry says (commands.ts); nothing is queued.
//
// The open conversation's id rides in the URL, /chat/<id> (owner
// request 2026-10-13): a refresh or a shared link lands on it instead
// of on an empty page. The URL is the one source of which conversation
// is open — picking one from the history, starting a new one, the
// first message of a new conversation and deleting the open one all
// change the URL, and one effect opens whatever the URL names.
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
/** A float's right edge: the column's, less the thread's scrollbar (0 until one shows). */
const SCROLLBAR_INSET = 'right-[var(--chat-scrollbar-width,0px)]';

/** A turn in flight: running, or stopping once the stop button was clicked. */
type TurnPhase = 'running' | 'stopping';

/** `record` without `key` (a new object; nothing is mutated). */
const withoutKey = <T,>(record: Record<string, T>, key: string): Record<string, T> =>
  Object.fromEntries(Object.entries(record).filter(([k]) => k !== key));

/** The history's entry for a conversation the user just wrote in, as the
 *  server will list it: at the top, one more input, written just now
 *  (owner request 2026-10-15: the history orders by the user's last
 *  line, so the move happens on send, not when the reply lands). */
const bumped = (list: ChatConversationSummary[], target: ChatConversation): ChatConversationSummary[] => {
  const entry: ChatConversationSummary = {
    id: target.id,
    title: target.title,
    created_at: target.created_at,
    updated_at: target.updated_at,
    total_tokens: target.total_tokens,
    message_count: target.messages.length + 1,
    user_input_count: target.user_input_count + 1,
    ended_at: new Date().toISOString(),
  };
  return [entry, ...list.filter((item) => item.id !== target.id)];
};

/** The conversation with the user's line added as the server will store it: in view before the server has seen it. */
const withUserLine = (base: ChatConversation, text: string, sideQuestion = false): ChatConversation => ({
  ...base,
  messages: [
    ...base.messages,
    {
      seq: (base.messages.at(-1)?.seq ?? 0) + 1,
      role: 'user',
      created_at: null,
      text,
      ...(sideQuestion ? { side_question: true } : {}),
    },
  ],
});

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
  const { conversationId = null } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<ChatConversationSummary[]>([]);
  const [conversation, setConversation] = useState<ChatConversation | null>(null);
  // The shown conversation as the URL effect reads it, so the effect
  // runs on a change of URL only, never on every peek.
  const shownRef = useRef<ChatConversation | null>(null);
  shownRef.current = conversation;
  // The turns in flight, by conversation id: running, or stopping once
  // the stop button was clicked and the turn has not come back yet.
  const [turns, setTurns] = useState<Record<string, TurnPhase>>({});
  // The first message of a new conversation: the conversation is being
  // created, so there is no id to key a turn by yet.
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // A page-side command's answer, shown under the message box.
  const [note, setNote] = useState<ChatNote | null>(null);
  const shownTurn = conversation ? turns[conversation.id] : undefined;
  const pending = conversation?.pending?.calls[0] ?? null;
  const working = creating || shownTurn !== undefined;
  const stopping = shownTurn === 'stopping';
  // The band the menus float in and the dock the message box floats
  // in; their heights are the text's top and bottom insets.
  const [band, setBand] = useState<HTMLDivElement | null>(null);
  const bandHeight = useElementHeight(band);
  const [dock, setDock] = useState<HTMLDivElement | null>(null);
  const dockHeight = useElementHeight(dock);
  // The thread's scroll box, for the width its scrollbar takes: the band
  // and the dock float over the whole column, the text scrolls in the
  // column less its scrollbar, so without this the box sat a half
  // scrollbar right of the text, over the bar (owner bug report 2026-10-14).
  const [scrollBox, setScrollBox] = useState<HTMLDivElement | null>(null);
  const scrollbarWidth = useScrollbarWidth(scrollBox);

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
      setNote(null);
      try {
        setConversation(await chatApi.getConversation(id));
      } catch (openError) {
        setError(describe(openError, t));
      }
    },
    [t],
  );

  // The URL names the open conversation: open what it names when that
  // is not what is shown; show the empty page when it names none. The
  // effect runs on a change of URL and nothing else — `open` is read
  // through a ref, since a new `open` (a change of UI language) must
  // not clear the page.
  const openRef = useRef(open);
  openRef.current = open;
  useEffect(() => {
    if (!conversationId) {
      setConversation(null);
      setNote(null);
      return;
    }
    if (shownRef.current?.id !== conversationId) {
      void openRef.current(conversationId);
    }
  }, [conversationId]);

  // Picking a conversation from the history: the URL changes and the
  // effect opens it; picking the open one again simply reloads it.
  const select = (id: string) => {
    if (id === conversationId) {
      void open(id);
      return;
    }
    navigate(`/chat/${id}`);
  };

  const startNew = () => {
    setError(null);
    navigate('/chat');
  };

  /** A fresh copy of a conversation, shown only if it is the one open. */
  const showIfOpen = (fresh: ChatConversation) => setConversation((shown) => (shown?.id === fresh.id ? fresh : shown));

  // One turn against `target`: the server's answer replaces the shown
  // conversation (if `target` is still the one shown). On failure, the
  // server may have stored part of the turn (the user's line, a tool's
  // result); show what it has.
  const applyTurn = async (target: ChatConversation, turn: () => Promise<ChatConversation>) => {
    setTurns((prev) => ({ ...prev, [target.id]: 'running' }));
    setError(null);
    // Only a longer conversation is news; the same length is what the
    // page already shows (the user's own line, added before sending).
    const stopPeeking = peekWhileWorking(target.id, (fresh) =>
      setConversation((shown) => (shown?.id === fresh.id && fresh.messages.length > shown.messages.length ? fresh : shown)),
    );
    try {
      showIfOpen(await turn().finally(stopPeeking));
      await refreshList();
    } catch (turnError) {
      if (shownRef.current?.id === target.id) {
        setError(describe(turnError, t));
      }
      try {
        showIfOpen(await chatApi.getConversation(target.id));
      } catch {
        // keep what we had
      }
    } finally {
      setTurns((prev) => withoutKey(prev, target.id));
    }
  };

  // The stop button: ask the server to stop the open conversation's
  // turn. The server lets the step that is running finish (so the
  // tokens shown match the bill, whichever model), then the turn's own
  // request comes back with the stopped conversation — its last row is
  // the stopped line, which names the step the stop landed on and what
  // would have followed — and `applyTurn` shows it as it would any
  // answer. Until then an unclickable "…" takes the button's place.
  const stopTurn = () => {
    const id = conversation?.id;
    if (!id || turns[id] !== 'running') {
      return;
    }
    setTurns((prev) => ({ ...prev, [id]: 'stopping' }));
    void chatApi.stopTurn(id).catch((stopError) => {
      setError(describe(stopError, t, 'chat.error.stop'));
      setTurns((prev) => (prev[id] === 'stopping' ? { ...prev, [id]: 'running' } : prev));
    });
  };

  // A command typed into the box: answered on the page, or a turn
  // against the server (see the notes above). /context is the dots
  // alone until the server has measured (owner request 2026-10-15).
  const runCommand = async (command: ChatCommand, argument: string) => {
    const shown = conversation;
    if (command.name === 'help') {
      setNote({ kind: 'help' });
      return;
    }
    if (command.name === 'btw') {
      await startTurn(argument, true, (id) => chatApi.sideQuestion(id, argument, language));
      return;
    }
    if (command.name === 'context') {
      setNote({ kind: 'context', usage: null });
      try {
        const usage = await chatApi.getContext(shown?.id ?? null, language);
        setNote((current) => (current?.kind === 'context' ? { kind: 'context', usage } : current));
      } catch (contextError) {
        setNote((current) => (current?.kind === 'context' && current.usage === null ? null : current));
        setError(describe(contextError, t));
      }
      return;
    }
    if (!shown || shown.messages.length === 0) {
      setError(t('chat.error.nothingToCompact'));
      return;
    }
    // The command is the user's own line (owner request 2026-10-14), as
    // the server stores it; the summary step follows as its reply.
    setConversation(withUserLine(shown, '/compact'));
    setConversations((list) => bumped(list, shown));
    await applyTurn(shown, () => chatApi.compact(shown.id, language));
  };

  // A line from the box: true when it was taken (and the box may
  // clear), false when it was refused and stays in the box — an unknown
  // command, a command that cannot run while the reply is awaited, or
  // a message while a reply or an answer is awaited (owner request
  // 2026-10-15: nothing typed is lost). The verdict is given at once;
  // the work goes on after.
  const send = (input: string): boolean => {
    setNote(null);
    setError(null);
    const parsed = parseInput(input);
    if (parsed.kind === 'unknown') {
      setError(t('chat.command.unknown', { command: parsed.name }));
      return false;
    }
    if (parsed.kind === 'command') {
      if (parsed.command.argumentKey && !parsed.argument) {
        setError(t('chat.command.needsArgument', { command: parsed.command.name, hint: t(parsed.command.argumentKey) }));
        return false;
      }
      if (parsed.command.blockedWhileWaiting && working) {
        setError(t('chat.command.waitTurn', { command: parsed.command.name }));
        return false;
      }
      if (parsed.command.name === 'btw' && pending) {
        // The server would refuse it too (409); refusing here keeps the
        // line in the box.
        setError(t('chat.composer.waitConfirm'));
        return false;
      }
      void runCommand(parsed.command, parsed.argument);
      return true;
    }
    if (working || pending) {
      // The box sends no message meanwhile; a line that slips through
      // (a race) stays in the box, as the server would refuse it.
      return false;
    }
    void sendMessage(parsed.text);
    return true;
  };

  const sendMessage = (text: string) => startTurn(text, false, (id) => chatApi.sendMessage(id, text, language));

  // The user's line into view at once — the conversation created first
  // when there is none yet — then one turn against the server: a
  // message, or a side question (/btw) with its flag on the line.
  const startTurn = async (text: string, sideQuestion: boolean, turn: (id: string) => Promise<ChatConversation>) => {
    let target = conversation;
    if (!target) {
      setCreating(true);
      try {
        target = await chatApi.createConversation();
      } catch (createError) {
        setError(describe(createError, t));
        return;
      } finally {
        setCreating(false);
      }
    }
    const base = target;
    setConversation(withUserLine(base, text, sideQuestion));
    setConversations((list) => bumped(list, base));
    if (base.id !== conversationId) {
      // A conversation just created: into the URL, after the line
      // above so the effect finds it already shown and fetches nothing.
      navigate(`/chat/${base.id}`, { replace: true });
    }
    await applyTurn(base, () => turn(base.id));
  };

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
    if (id === conversationId) {
      navigate('/chat', { replace: true });
    }
    await refreshList();
  };

  return (
    <main className="grid min-h-0 w-full flex-1 grid-cols-1 grid-rows-[auto_minmax(0,1fr)] md:grid-cols-[16rem_minmax(0,1fr)] md:grid-rows-1">
      {/* On a phone the panel takes a short band above the chat; side by side it takes the full height. */}
      <aside className="flex max-h-56 min-h-0 flex-col md:max-h-none">
        <ChatSidebar
          conversations={conversations}
          activeId={conversation?.id ?? null}
          onSelect={select}
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
            ...(scrollbarWidth > 0 ? { '--chat-scrollbar-width': `${scrollbarWidth}px` } : {}),
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
            onScrollBox={setScrollBox}
          />
        ) : (
          // What the agent is, centered in the empty thread (owner
          // request 2026-09-26) — not a heading in the corner.
          <div className="flex h-full flex-col items-center justify-center gap-6 px-6 py-6" data-testid="chat-empty">
            <p className="max-w-prose text-center text-sm leading-relaxed text-ink-3">
              {t('chat.empty.hint')}
            </p>
          </div>
        )}
        {/* The band: the menus in the top right corner, each cluster on its own shade; only the buttons take clicks.
            Both floats stop short of the thread's scrollbar (SCROLLBAR_INSET), so they line up with the text, not the column. */}
        <div ref={setBand} className={cn('pointer-events-none absolute top-0 px-4 pb-6 pt-4', SCROLLBAR_INSET)} data-testid="chat-band">
          <div className={cn('pointer-events-auto p-1', FLOAT_SHADE)} data-testid="chat-band-content">
            <HeaderControls />
          </div>
        </div>
        {/* The dock: the wheel passes through outside the box's shade; only the box itself takes clicks.
            A command's answer, when there is one, sits under the box, inside the same shade (its
            height counts toward the dock's, so the thread's bottom inset grows with it). */}
        <div ref={setDock} className={cn('pointer-events-none absolute bottom-0 left-0 pb-4 pt-10', SCROLLBAR_INSET)} data-testid="chat-dock">
          <div className={CHAT_FRAME}>
            <div className={cn('pointer-events-auto flex flex-col gap-3', FLOAT_SHADE)} data-testid="chat-dock-content">
              {error ? (
                <p className="text-xs text-caution" data-testid="chat-error">
                  {error}
                </p>
              ) : null}
              <ChatComposer
                blocked={working || pending !== null}
                blockedHint={working ? t('chat.composer.waitTurn') : pending ? t('chat.composer.waitConfirm') : null}
                working={working}
                stopping={stopping}
                onSend={send}
                // Nothing to stop yet while the conversation itself is being created.
                onStop={shownTurn ? stopTurn : undefined}
              />
              {note ? <ChatCommandNote note={note} /> : null}
            </div>
          </div>
        </div>
      </section>
    </main>
  );
};

// What went wrong, in the page's words: the server's own code when it
// gave one (busy, no model, a question still waiting, nothing to
// summarize), else the parsed message under `fallback` ("Could not
// send" unless told otherwise).
type ErrorKey =
  | 'chat.error.busy'
  | 'chat.error.notConfigured'
  | 'chat.error.send'
  | 'chat.error.stop'
  | 'chat.error.nothingToCompact'
  | 'chat.composer.waitConfirm';

function describe(
  error: unknown,
  t: (key: ErrorKey, params?: Record<string, string>) => string,
  fallback: 'chat.error.send' | 'chat.error.stop' = 'chat.error.send',
): string {
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
    if (code === 'confirmation_pending') {
      return t('chat.composer.waitConfirm');
    }
    if (code === 'nothing_to_compact') {
      return t('chat.error.nothingToCompact');
    }
    const parsed = (error as { parsedError?: { message?: string } }).parsedError?.message;
    return t(fallback, { error: parsed ?? data?.message ?? error.message });
  }
  return t(fallback, { error: error instanceof Error ? error.message : String(error) });
}

export default ChatPage;
