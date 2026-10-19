import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import type { ChatContextUsage, ChatConversation, ChatConversationSummary } from '../../api/chat';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';

vi.mock('../../api/chat', () => ({
  chatApi: {
    listConversations: vi.fn(),
    createConversation: vi.fn(),
    getConversation: vi.fn(),
    deleteConversation: vi.fn(),
    sendMessage: vi.fn(),
    getTranscript: vi.fn(),
    confirm: vi.fn(),
    stopTurn: vi.fn(),
    getContext: vi.fn(),
    compact: vi.fn(),
    sideQuestion: vi.fn(),
  },
}));

const { chatApi } = await import('../../api/chat');
const { default: ChatPage } = await import('../ChatPage');

const SUMMARY: ChatConversationSummary = {
  id: 'c1', title: 'hi', created_at: '2026-09-23T10:00:00', updated_at: '2026-09-23T10:00:00',
  message_count: 0, user_input_count: 0, total_tokens: 0, ended_at: null,
};
const EMPTY: ChatConversation = { ...SUMMARY, messages: [], pending: null, busy: false, watched_runs: [] };
const ANSWERED: ChatConversation = {
  ...SUMMARY,
  message_count: 2, user_input_count: 1, total_tokens: 738,
  messages: [
    { seq: 1, role: 'user', created_at: null, text: 'hi there' },
    { seq: 2, role: 'assistant', created_at: null, text: 'hello', usage: { input_tokens: 700, output_tokens: 38 }, llm: 'fake', time_ms: 5, transcript_chars: 100 },
  ],
  pending: null, busy: false, watched_runs: [],
};

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

// Where the router is, for the URL assertions.
const Location = () => <span data-testid="location">{useLocation().pathname}</span>;

// The page as the app mounts it: under its route, so the conversation
// id in the URL reaches it.
const renderPage = (initial = '/chat') =>
  render(
    <MemoryRouter initialEntries={[initial]}>
      <UiLanguageProvider>
        <Routes>
          <Route
            path="/chat/:conversationId?"
            element={
              <>
                <ChatPage />
                <Location />
              </>
            }
          />
        </Routes>
      </UiLanguageProvider>
    </MemoryRouter>,
  );
beforeEach(() => {
  vi.mocked(chatApi.listConversations).mockResolvedValue([]);
  vi.mocked(chatApi.createConversation).mockResolvedValue(EMPTY);
});

describe('ChatPage', () => {
  it('shows the sent line at once with pulsing dots, then the answer', async () => {
    let answer: (value: ChatConversation) => void = () => {};
    vi.mocked(chatApi.sendMessage).mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    renderPage();
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: 'hi there' } });
    fireEvent.click(screen.getByTestId('chat-send'));

    // The user's line and the dots, before the server has answered.
    expect(await screen.findByTestId('chat-user')).toHaveTextContent('hi there');
    expect(screen.getByTestId('chat-working')).toBeInTheDocument();
    expect(screen.queryByText(/Thinking|思考中/)).toBeNull();
    // The box takes typing meanwhile, but no message goes: the arrow is the stop button.
    expect(screen.getByTestId('chat-input')).toBeEnabled();
    expect(screen.getByTestId('chat-input')).toHaveAttribute('placeholder', expect.stringMatching(/Waiting for the reply|等待回复中/));
    expect(screen.queryByTestId('chat-send')).toBeNull();

    vi.mocked(chatApi.listConversations).mockResolvedValue([{ ...SUMMARY, user_input_count: 1, total_tokens: 738 }]);
    await act(async () => {
      answer(ANSWERED);
    });
    await waitFor(() => expect(screen.getByText('hello')).toBeInTheDocument());
    expect(screen.queryByTestId('chat-working')).toBeNull();
    expect(screen.getAllByTestId('chat-user')).toHaveLength(1);
    expect(screen.getByTestId('chat-send')).toBeInTheDocument();
    expect(chatApi.sendMessage).toHaveBeenCalledWith('c1', 'hi there', 'en');
  });

  it('shows each stored step while the turn still runs, dots after it, and never a held call from a peek', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let answer: (value: ChatConversation) => void = () => {};
    vi.mocked(chatApi.sendMessage).mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    // The server has stored the user's line, the tool-calling reply and
    // the tool's result, and holds a second call for the user's yes.
    const partial: ChatConversation = {
      ...SUMMARY,
      message_count: 3, user_input_count: 1,
      messages: [
        { seq: 1, role: 'user', created_at: null, text: 'hi there' },
        { seq: 2, role: 'assistant', created_at: null, text: null, tool_calls: [{ id: 'c1', name: 'list_tickers', arguments: {} }], usage: { input_tokens: 10, output_tokens: 2 }, llm: 'fake' },
        { seq: 3, role: 'tool', created_at: null, tool_call_id: 'c1', name: 'list_tickers', output: { tickers: ['AAPL'] }, output_chars: 20, input: {} },
      ],
      pending: { calls: [{ call_id: 'c2', name: 'delete_run', input: { run_id: 'x' }, facts: {} }] }, busy: false, watched_runs: [],
    };
    vi.mocked(chatApi.getConversation).mockResolvedValue(partial);
    renderPage();
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: 'hi there' } });
    fireEvent.click(screen.getByTestId('chat-send'));
    expect(await screen.findByTestId('chat-user')).toHaveTextContent('hi there');
    expect(screen.queryByTestId('chat-tool')).toBeNull();

    // One peek later the two finished steps are on the page, the dots
    // sit after them, and the held call is not shown yet.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(900);
    });
    expect(chatApi.getConversation).toHaveBeenCalledWith('c1');
    expect(screen.getByTestId('chat-assistant')).toBeInTheDocument();
    const tool = screen.getByTestId('chat-tool');
    expect(tool).toHaveTextContent(/list_tickers/);
    const dots = screen.getByTestId('chat-working');
    expect(tool.compareDocumentPosition(dots) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByTestId('chat-pending')).toBeNull();
    expect(screen.queryByTestId('chat-send')).toBeNull();

    // The request's own answer brings the held call; the dots go.
    vi.mocked(chatApi.getConversation).mockClear();
    await act(async () => {
      answer(partial);
    });
    await waitFor(() => expect(screen.getByTestId('chat-pending')).toBeInTheDocument());
    expect(screen.queryByTestId('chat-working')).toBeNull();
    expect(screen.getByTestId('chat-tool-decision')).toHaveTextContent(/approve|同意/);
    // Peeking stopped with the request.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(chatApi.getConversation).not.toHaveBeenCalled();
  });

  it('floats the mode, language and color menus over the top right corner of the chat, and the message box over its bottom', () => {
    vi.mocked(chatApi.listConversations).mockResolvedValue([SUMMARY]);
    renderPage();
    // The header's menus, with their symbols, float in the chat column's top right corner, on a shade that hugs them: no strip across the width.
    const band = screen.getByTestId('chat-band');
    expect(band).toHaveClass('absolute', 'top-0', 'right-[var(--chat-scrollbar-width,0px)]');
    expect(band.className).not.toMatch(/inset-x-0|bg-/);
    expect(screen.getByTestId('chat-band-content').className).toMatch(/bg-background\/85.*shadow-/);
    const controls = screen.getByTestId('header-controls');
    expect(band).toContainElement(controls);
    for (const menu of ['mode-menu', 'language-menu', 'theme-menu']) {
      expect(controls).toContainElement(screen.getByTestId(menu));
      expect(screen.getByTestId(menu).querySelector('svg')).not.toBeNull();
    }
    const sidebar = screen.getByTestId('chat-sidebar');
    expect(sidebar).not.toContainElement(controls);
    // The panel is level 1; the composer, directly on the page, is level 1 too.
    expect(sidebar).toHaveClass('bg-surface-1');
    expect(screen.getByTestId('chat-composer')).toHaveClass('bg-surface-1');
    // The message box floats at the bottom of the chat column, on a shade.
    const dock = screen.getByTestId('chat-dock');
    expect(screen.getByTestId('chat-column')).toHaveClass('relative');
    expect(dock).toHaveClass('absolute', 'bottom-0');
    expect(dock.className).not.toMatch(/bg-/);
    expect(screen.getByTestId('chat-dock-content').className).toMatch(/bg-background\/85.*shadow-/);
    expect(dock).toContainElement(screen.getByTestId('chat-composer'));
  });

  it('scrolls the chat across the whole column, caps only the text, and puts no backdrop behind it', async () => {
    vi.mocked(chatApi.listConversations).mockResolvedValue([{ ...SUMMARY, user_input_count: 1, total_tokens: 738 }]);
    vi.mocked(chatApi.getConversation).mockResolvedValue(ANSWERED);
    renderPage();
    // The page and the column run edge to edge; nothing caps or insets them.
    const main = screen.getByRole('main');
    expect(main.className).not.toMatch(/max-w-|px-|gap-/);
    const column = screen.getByTestId('chat-column');
    expect(column.className).not.toMatch(/max-w-|mx-auto|bg-surface-1|p-4/);
    // The text inside the scroll box is capped and centered, and keeps a bottom inset for the dock.
    fireEvent.click(await screen.findByTestId('chat-conversation'));
    const thread = await screen.findByTestId('chat-thread');
    expect(thread).toHaveClass('h-full', 'overflow-y-auto');
    expect(thread.className).not.toMatch(/max-w-/);
    const content = screen.getByTestId('chat-thread-content');
    expect(content).toHaveClass('mx-auto', 'max-w-[59rem]', 'pt-[var(--chat-band-height,4rem)]', 'pb-[var(--chat-dock-height,8rem)]');
    expect(screen.getByTestId('chat-dock-content').parentElement).toHaveClass('mx-auto', 'max-w-[59rem]');
  });

  // The text scrolls inside the column less its scrollbar, and the box
  // floated over the whole column, so it sat a half scrollbar to the
  // right of the text, over the bar (owner bug report 2026-10-14).
  it('keeps the message box and the menus off the thread’s scrollbar, in line with the text', async () => {
    const observers: Array<() => void> = [];
    vi.stubGlobal('ResizeObserver', class {
      constructor(fire: () => void) { observers.push(fire); }
      observe() {}
      disconnect() {}
    });
    try {
      vi.mocked(chatApi.listConversations).mockResolvedValue([{ ...SUMMARY, user_input_count: 1, total_tokens: 738 }]);
      vi.mocked(chatApi.getConversation).mockResolvedValue(ANSWERED);
      renderPage();
      fireEvent.click(await screen.findByTestId('chat-conversation'));
      const thread = await screen.findByTestId('chat-thread');
      const column = screen.getByTestId('chat-column');
      // Both floats end where the text does, not at the column's edge.
      for (const float of [screen.getByTestId('chat-dock'), screen.getByTestId('chat-band')]) {
        expect(float).toHaveClass('right-[var(--chat-scrollbar-width,0px)]');
        expect(float).not.toHaveClass('inset-x-0', 'right-0');
      }
      // No scrollbar yet: nothing set, so the floats run to the edge.
      expect(column.style.getPropertyValue('--chat-scrollbar-width')).toBe('');
      // The thread grows past its box: a 15px bar appears inside it.
      Object.defineProperty(thread, 'offsetWidth', { value: 800, configurable: true });
      Object.defineProperty(thread, 'clientWidth', { value: 785, configurable: true });
      act(() => observers.forEach((fire) => fire()));
      expect(column.style.getPropertyValue('--chat-scrollbar-width')).toBe('15px');
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

// The URL names the open conversation (2026-10-13): /chat/<id> opens
// it, so a refresh lands where the user was; picking, starting new,
// a first message and a delete each move the URL.
describe('ChatPage conversation URL', () => {
  beforeEach(() => vi.clearAllMocks());

  it('opens the conversation the URL names, so a refresh lands on it', async () => {
    vi.mocked(chatApi.listConversations).mockResolvedValue([SUMMARY]);
    vi.mocked(chatApi.getConversation).mockResolvedValue(ANSWERED);
    renderPage('/chat/c1');
    await waitFor(() => expect(screen.getByText('hello')).toBeInTheDocument());
    expect(chatApi.getConversation).toHaveBeenCalledWith('c1');
    expect(screen.getByTestId('location')).toHaveTextContent('/chat/c1');
  });

  it('moves the URL when a conversation is picked, and clears it on new', async () => {
    vi.mocked(chatApi.listConversations).mockResolvedValue([SUMMARY]);
    vi.mocked(chatApi.getConversation).mockResolvedValue(ANSWERED);
    renderPage();
    expect(screen.getByTestId('location')).toHaveTextContent('/chat');
    fireEvent.click(await screen.findByTestId('chat-conversation'));
    await waitFor(() => expect(screen.getByText('hello')).toBeInTheDocument());
    expect(screen.getByTestId('location')).toHaveTextContent('/chat/c1');
    fireEvent.click(screen.getByTestId('chat-new'));
    await waitFor(() => expect(screen.getByTestId('chat-empty')).toBeInTheDocument());
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/chat$/);
  });

  it('puts a conversation created by the first message into the URL without refetching it', async () => {
    vi.mocked(chatApi.sendMessage).mockResolvedValue(ANSWERED);
    renderPage();
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: 'hi there' } });
    fireEvent.click(screen.getByTestId('chat-send'));
    await waitFor(() => expect(screen.getByText('hello')).toBeInTheDocument());
    // The router applies a navigation as a low-priority update; wait for it.
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/chat/c1'));
    expect(chatApi.getConversation).not.toHaveBeenCalled();
  });

  it('leaves the URL when the open conversation is deleted', async () => {
    vi.mocked(chatApi.listConversations).mockResolvedValue([SUMMARY]);
    vi.mocked(chatApi.getConversation).mockResolvedValue(ANSWERED);
    vi.mocked(chatApi.deleteConversation).mockResolvedValue(undefined as never);
    renderPage('/chat/c1');
    await waitFor(() => expect(screen.getByText('hello')).toBeInTheDocument());
    fireEvent.click(screen.getAllByTestId('chat-conversation-delete')[0]);
    fireEvent.click(screen.getByTestId('chat-conversation-delete-confirm'));
    await waitFor(() => expect(screen.getByTestId('chat-empty')).toBeInTheDocument());
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/chat$/);
  });
});

// The stop button (2026-10-12): the send arrow becomes a stop button
// while the turn runs; a click asks the server to stop, and the turn's
// own answer — the stopped conversation — brings the arrow back.
describe('ChatPage — stop', () => {
  const STOPPED: ChatConversation = {
    ...SUMMARY,
    message_count: 3, user_input_count: 1,
    messages: [
      { seq: 1, role: 'user', created_at: null, text: 'hi there' },
      { seq: 2, role: 'assistant', created_at: null, text: 'Hello.', usage: null, llm: 'fake', time_ms: 5, transcript_chars: 10 },
      { seq: 3, role: 'stopped', created_at: null, text: '[The user asked to stop this reply, but it had already finished.]', late: true },
    ],
    pending: null, busy: false, watched_runs: [],
  };

  it('turns the arrow into a stop button, asks the server to stop on a click, and shows the stopped turn', async () => {
    let answer: (value: ChatConversation) => void = () => {};
    vi.mocked(chatApi.sendMessage).mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    vi.mocked(chatApi.stopTurn).mockResolvedValue({ id: 'c1', stopped: true });
    renderPage();
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: 'hi there' } });
    fireEvent.click(screen.getByTestId('chat-send'));

    // Enabled once there is a turn to stop (the conversation exists and
    // its request is on its way).
    const stop = await screen.findByTestId('chat-stop');
    await waitFor(() => expect(stop).toBeEnabled());
    expect(screen.queryByTestId('chat-send')).toBeNull();
    fireEvent.click(stop);
    await waitFor(() => expect(chatApi.stopTurn).toHaveBeenCalledWith('c1'));
    // Until the turn comes back (the server finishes the running step
    // first), an unclickable "…" stands where the stop button was.
    expect(screen.queryByTestId('chat-stop')).toBeNull();
    expect(screen.getByTestId('chat-stopping')).toBeDisabled();
    expect(screen.getByTestId('chat-working')).toBeInTheDocument();

    await act(async () => {
      answer(STOPPED);
    });
    await waitFor(() => expect(screen.getByTestId('chat-stopped')).toHaveTextContent(/(That was the last step|这已是最后一步)/));
    expect(screen.queryByTestId('chat-working')).toBeNull();
    expect(screen.queryByTestId('chat-stopping')).toBeNull();
    expect(screen.getByTestId('chat-send')).toBeInTheDocument();
  });

  it('reports a stop that failed and offers the button again', async () => {
    vi.mocked(chatApi.sendMessage).mockReturnValue(new Promise(() => {}));
    vi.mocked(chatApi.stopTurn).mockRejectedValue(new Error('offline'));
    renderPage();
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: 'hi there' } });
    fireEvent.click(screen.getByTestId('chat-send'));
    const stop = await screen.findByTestId('chat-stop');
    await waitFor(() => expect(stop).toBeEnabled());
    fireEvent.click(stop);
    await waitFor(() => expect(screen.getByTestId('chat-error')).toHaveTextContent(/(Could not stop|停止失败).*offline/));
    expect(screen.queryByTestId('chat-stopping')).toBeNull();
    expect(screen.getByTestId('chat-stop')).toBeEnabled();
  });
});

describe('ChatPage slash commands', () => {
  const USAGE: ChatContextUsage = {
    llm: 'gemini/gemini-3.8-flash', source: 'litellm', window: 1048576, output_limit: 65536, max_tokens: 983040,
    used_tokens: 14200, percent: 1.4, compact_at_tokens: 835584, compact_at_percent: 85, chars_per_token: 4.1, calibrated: true,
    system_prompt_tokens: 2000, tools_tokens: 4000, conversation_tokens: 8200,
  };
  // Earlier tests' calls must not count here.
  beforeEach(() => vi.clearAllMocks());
  const page = () => renderPage();
  const type = (text: string) => {
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: text } });
    fireEvent.click(screen.getByTestId('chat-send'));
  };

  it('answers /help and /context under the message box, without a conversation, and sends nothing', async () => {
    vi.mocked(chatApi.getContext).mockResolvedValue(USAGE);
    page();
    type('/help');
    const dock = screen.getByTestId('chat-dock-content');
    // The answer is the box's, not the thread's (owner request 2026-10-15).
    expect(await within(dock).findByTestId('chat-note-help')).toHaveTextContent('/compact');
    expect(within(dock).getByTestId('chat-note-help')).toHaveTextContent(/\/btw <(question|问题)>/);
    expect(screen.getByTestId('chat-empty')).toBeInTheDocument();
    type('/context');
    const note = await within(dock).findByTestId('chat-note-context');
    expect(chatApi.getContext).toHaveBeenCalledWith(null, 'en');
    // Three lines — the model, the window as a subtraction, the usage as
    // a sum — in that order, and nothing else (owner request 2026-10-15).
    expect(note).toHaveTextContent(/(LLM context window usage|LLM 上下文窗口用量)/);
    expect(note).toHaveTextContent(/983,040 ?= ?1,048,576 ?[（(](max|上限)[)）] ?- ?65,536 ?[（(](reserved for the LLM response|为 LLM 回复预留)[)）]/);
    expect(note).toHaveTextContent(/14,200 ?[（(]1\.4%[)）] ?= ?2,000 ?[（(](instructions|指令)[)）] ?\+ ?4,000 ?[（(](tools|工具)[)）] ?\+ ?8,200 ?[（(](conversation|对话)[)）]/);
    expect(note.textContent?.indexOf('gemini/gemini-3.8-flash')).toBeLessThan(note.textContent?.indexOf('1,048,576') ?? -1);
    expect(note).not.toHaveTextContent(/spent so far|累计消耗|characters per token|个字符|auto summary|自动总结|litellm/);
    expect(screen.queryByTestId('chat-note-help')).toBeNull();
    expect(chatApi.sendMessage).not.toHaveBeenCalled();
    expect(chatApi.createConversation).not.toHaveBeenCalled();
  });

  it('refuses an unknown command and /compact with nothing to summarize', async () => {
    page();
    type('/model');
    expect(await screen.findByTestId('chat-error')).toHaveTextContent(/(Unknown command \/model|未知命令 \/model)/);
    // The line stays in the box to be fixed.
    expect(screen.getByTestId('chat-input')).toHaveValue('/model');
    type('/compact');
    expect(await screen.findByTestId('chat-error')).toHaveTextContent(/(Nothing to summarize yet|还没有可总结的内容)/);
    expect(chatApi.compact).not.toHaveBeenCalled();
    expect(chatApi.sendMessage).not.toHaveBeenCalled();
  });

  it('runs /compact as a turn: the command as the user’s line, the summary step as its bare reply', async () => {
    vi.mocked(chatApi.sendMessage).mockResolvedValue(ANSWERED);
    const compacted: ChatConversation = {
      ...ANSWERED,
      messages: [
        ...ANSWERED.messages,
        { seq: 3, role: 'user', created_at: null, text: '/compact' },
        { seq: 4, role: 'summary', created_at: null, text: 'Summary.', compacted: { trigger: 'manual', first_seq: 1, last_seq: 2, tokens_before: 738 }, usage: { input_tokens: 800, output_tokens: 20 }, llm: 'fake' },
      ],
    };
    let finish: (value: ChatConversation) => void = () => {};
    vi.mocked(chatApi.compact).mockReturnValue(new Promise<ChatConversation>((resolve) => { finish = resolve; }));
    page();
    type('hi there');
    await waitFor(() => expect(screen.getByText('hello')).toBeInTheDocument());
    type('/compact');
    await waitFor(() => expect(chatApi.compact).toHaveBeenCalledWith('c1', 'en'));
    // The command is in view as the user's own line before the server answers.
    expect(screen.getAllByTestId('chat-user').map((line) => line.textContent)).toEqual(['hi there', '/compact']);
    await act(async () => finish(compacted));
    const summary = await screen.findByTestId('chat-summary');
    // The step line and the token line, nothing else: the text waits in the transcript.
    expect(summary.firstElementChild?.textContent).toMatch(/^(Step 1: LLM summarized the conversation|第 1 步：LLM 总结了对话)$/);
    expect(summary).not.toHaveTextContent('Summary.');
    expect(summary).toHaveTextContent(/820/);
    expect(screen.getAllByTestId('chat-user')).toHaveLength(2);
    // The turn is over: the arrow is back (disabled only because the box is empty).
    expect(screen.getByTestId('chat-send')).toBeInTheDocument();
    expect(screen.queryByTestId('chat-stop')).toBeNull();
  });

  it('runs /btw as a turn: the question as the user’s marked line, the answer as a side-question step', async () => {
    vi.mocked(chatApi.sendMessage).mockResolvedValue(ANSWERED);
    const asked: ChatConversation = {
      ...ANSWERED,
      messages: [
        ...ANSWERED.messages,
        { seq: 3, role: 'user', created_at: null, text: 'what is tier 2?', side_question: true },
        { seq: 4, role: 'assistant', created_at: null, text: 'The deep analysis.', side_question: true, usage: { input_tokens: 20, output_tokens: 3 }, llm: 'fake' },
      ],
    };
    let finish: (value: ChatConversation) => void = () => {};
    vi.mocked(chatApi.sideQuestion).mockReturnValue(new Promise<ChatConversation>((resolve) => { finish = resolve; }));
    page();
    type('hi there');
    await waitFor(() => expect(screen.getByText('hello')).toBeInTheDocument());
    type('/btw what is tier 2?');
    await waitFor(() => expect(chatApi.sideQuestion).toHaveBeenCalledWith('c1', 'what is tier 2?', 'en'));
    // The question is in view, marked, before the server answers, with the dots after it.
    expect(screen.getAllByTestId('chat-user').map((line) => line.textContent)).toEqual(['hi there', '/btw what is tier 2?']);
    expect(screen.getByTestId('chat-working')).toBeInTheDocument();
    expect(screen.queryByTestId('chat-send')).toBeNull();
    await act(async () => finish(asked));
    await waitFor(() => expect(screen.getByText('The deep analysis.')).toBeInTheDocument());
    const replies = screen.getAllByTestId('chat-assistant');
    expect(replies[1].firstElementChild?.textContent).toMatch(/^(Step 1: LLM answered the side question|第 1 步：LLM 回答了题外问题)$/);
    expect(chatApi.sendMessage).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('chat-send')).toBeInTheDocument();
  });

  it('refuses /btw without a question, and otherwise starts a conversation for one like a first message', async () => {
    page();
    type('/btw');
    expect(await screen.findByTestId('chat-error')).toHaveTextContent(/(Type the question after \/btw|请在 \/btw 后面写上问题)/);
    expect(screen.getByTestId('chat-input')).toHaveValue('/btw');
    expect(chatApi.sideQuestion).not.toHaveBeenCalled();
    expect(chatApi.createConversation).not.toHaveBeenCalled();

    const fresh: ChatConversation = {
      ...EMPTY,
      messages: [
        { seq: 1, role: 'user', created_at: null, text: 'anyone?', side_question: true },
        { seq: 2, role: 'assistant', created_at: null, text: 'Yes.', side_question: true },
      ],
    };
    vi.mocked(chatApi.sideQuestion).mockResolvedValue(fresh);
    type('/btw anyone?');
    await waitFor(() => expect(chatApi.sideQuestion).toHaveBeenCalledWith('c1', 'anyone?', 'en'));
    expect(chatApi.createConversation).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByText('Yes.')).toBeInTheDocument());
    expect(screen.getByTestId('location')).toHaveTextContent('/chat/c1');
    expect(screen.queryByTestId('chat-error')).toBeNull();
  });

  it('refuses /btw while a held call waits for the user’s answer', async () => {
    const held: ChatConversation = {
      ...SUMMARY,
      messages: [{ seq: 1, role: 'user', created_at: null, text: 'cancel q1' }],
      pending: { calls: [{ call_id: 'c2', name: 'delete_run', input: { run_id: 'q1' }, facts: {} }] }, busy: false, watched_runs: [],
    };
    vi.mocked(chatApi.getConversation).mockResolvedValue(held);
    renderPage('/chat/c1');
    await screen.findByTestId('chat-pending');
    type('/btw which run is that?');
    expect(await screen.findByTestId('chat-error')).toHaveTextContent(/(Answer the question above first|请先回答上面的问题)/);
    expect(chatApi.sideQuestion).not.toHaveBeenCalled();
    // The question waits in the box, and so does the held call.
    expect(screen.getByTestId('chat-input')).toHaveValue('/btw which run is that?');
    expect(screen.getByTestId('chat-pending')).toBeInTheDocument();
  });

  it('shows /context as measuring until the server answers', async () => {
    let measured: (value: ChatContextUsage) => void = () => {};
    vi.mocked(chatApi.getContext).mockReturnValue(new Promise((resolve) => { measured = resolve; }));
    page();
    type('/context');
    const note = await screen.findByTestId('chat-note-context');
    // The dots alone, as for a reply still being written: no words.
    expect(within(note).getByTestId('chat-note-waiting')).toBeInTheDocument();
    expect(note.textContent?.trim()).toBe('');
    await act(async () => measured(USAGE));
    await waitFor(() => expect(note).toHaveTextContent(/14,200/));
    expect(within(note).queryByTestId('chat-note-waiting')).toBeNull();
  });

  it('while a reply is awaited, answers /help at once and refuses /context with a line over the box', async () => {
    let answer: (value: ChatConversation) => void = () => {};
    vi.mocked(chatApi.sendMessage).mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    vi.mocked(chatApi.getContext).mockResolvedValue(USAGE);
    page();
    type('hi there');
    await screen.findByTestId('chat-working');

    // Enter on a command line sends it even though the arrow is the stop button.
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: '/help' } });
    fireEvent.keyDown(screen.getByTestId('chat-input'), { key: 'Enter' });
    expect(await screen.findByTestId('chat-note-help')).toBeInTheDocument();

    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: '/context' } });
    fireEvent.keyDown(screen.getByTestId('chat-input'), { key: 'Enter' });
    expect(await screen.findByTestId('chat-error')).toHaveTextContent(/(Wait for the reply before \/context|请等回复返回后再使用 \/context)/);
    expect(screen.queryByTestId('chat-note-help')).toBeNull();
    expect(chatApi.getContext).not.toHaveBeenCalled();
    // The refused line stays in the box (owner request 2026-10-15).
    expect(screen.getByTestId('chat-input')).toHaveValue('/context');

    // Once the reply is back, Enter on the same line runs it.
    await act(async () => answer(ANSWERED));
    await waitFor(() => expect(screen.queryByTestId('chat-working')).toBeNull());
    fireEvent.keyDown(screen.getByTestId('chat-input'), { key: 'Enter' });
    await waitFor(() => expect(chatApi.getContext).toHaveBeenCalledWith('c1', 'en'));
    expect(await screen.findByTestId('chat-note-context')).toHaveTextContent(/14,200/);
    expect(screen.queryByTestId('chat-error')).toBeNull();
  });

  it('lifts the conversation the user just wrote in to the top of the history at once', async () => {
    const older: ChatConversationSummary = { ...SUMMARY, id: 'c0', user_input_count: 1, ended_at: '2026-09-22T10:00:00' };
    vi.mocked(chatApi.listConversations).mockResolvedValue([older, SUMMARY]);
    vi.mocked(chatApi.getConversation).mockResolvedValue(ANSWERED);
    vi.mocked(chatApi.sendMessage).mockReturnValue(new Promise(() => {}));
    renderPage('/chat/c1');
    await waitFor(() => expect(screen.getByText('hello')).toBeInTheDocument());
    const entries = () => screen.getAllByTestId('chat-conversation').map((entry) => entry.getAttribute('aria-current'));
    expect(entries()).toEqual([null, 'page']);
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: 'more' } });
    fireEvent.click(screen.getByTestId('chat-send'));
    // Before any reply: the open conversation is first, with one more input.
    await waitFor(() => expect(entries()).toEqual(['page', null]));
    expect(screen.getAllByTestId('chat-conversation')[0]).toHaveTextContent(/2/);
  });

  it('keeps another conversation open for writing while one waits for its reply', async () => {
    const other: ChatConversation = { ...EMPTY, id: 'c2', title: 'other' };
    // The history lists the running conversation first, the other second.
    vi.mocked(chatApi.listConversations).mockResolvedValue([SUMMARY, { ...SUMMARY, id: 'c2', title: 'other' }]);
    let answer: (value: ChatConversation) => void = () => {};
    vi.mocked(chatApi.sendMessage)
      .mockReturnValueOnce(new Promise((resolve) => { answer = resolve; }))
      .mockResolvedValueOnce({ ...other, messages: [{ seq: 1, role: 'user', created_at: null, text: 'second' }, { ...ANSWERED.messages[1], text: 'reply two' }] });
    vi.mocked(chatApi.getConversation).mockImplementation(async (id) => (id === 'c2' ? other : ANSWERED));
    page();
    type('hi there');
    await screen.findByTestId('chat-working');

    // Open the other conversation: no dots, no stop button, the box sends.
    await waitFor(() => expect(screen.getAllByTestId('chat-conversation')).toHaveLength(2));
    fireEvent.click(screen.getAllByTestId('chat-conversation')[1]);
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/chat/c2'));
    await waitFor(() => expect(screen.queryByTestId('chat-working')).toBeNull());
    expect(screen.queryByTestId('chat-stop')).toBeNull();
    type('second');
    await waitFor(() => expect(chatApi.sendMessage).toHaveBeenCalledWith('c2', 'second', 'en'));
    await waitFor(() => expect(screen.getByText('reply two')).toBeInTheDocument());

    // The first conversation's answer, landing now, does not replace what is shown.
    await act(async () => answer(ANSWERED));
    expect(screen.queryByText('hello')).toBeNull();
    expect(screen.getByText('reply two')).toBeInTheDocument();
  });
});

describe('run notices', () => {
  const NOTICE: ChatConversation['messages'][number] = {
    seq: 3, role: 'notice', created_at: null, text: null,
    run: { run_id: 'r1', ticker: 'AAPL', tier: 1, status: 'succeeded', outlook: 'bullish', score: 7.2, error: null, stopped_stage: null },
  };
  const WAITING: ChatConversation = {
    ...ANSWERED, message_count: 2, watched_runs: [{ run_id: 'r1', language: 'en' }],
  };
  const REPORTED: ChatConversation = {
    ...ANSWERED, message_count: 4, watched_runs: [],
    messages: [
      ...ANSWERED.messages,
      NOTICE,
      { seq: 4, role: 'assistant', created_at: null, text: 'AAPL came back bullish, 7.2.', usage: { input_tokens: 700, output_tokens: 20 }, llm: 'fake', time_ms: 5, transcript_chars: 100 },
    ],
  };

  it('polls while a run is watched, shows the notice and the report when they land, then stops polling', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(chatApi.getConversation).mockResolvedValue(WAITING);
    renderPage('/chat/c1');
    await waitFor(() => expect(screen.getByText('hello')).toBeInTheDocument());
    // Nothing of the page's runs: the box is open, no dots.
    expect(screen.getByTestId('chat-send')).toBeInTheDocument();
    expect(screen.queryByTestId('chat-working')).toBeNull();

    // The server reports the run while the page polls.
    vi.mocked(chatApi.getConversation).mockClear();
    vi.mocked(chatApi.getConversation).mockResolvedValue(REPORTED);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    expect(chatApi.getConversation).toHaveBeenCalledWith('c1');
    await waitFor(() => expect(screen.getByTestId('chat-notice')).toBeInTheDocument());
    expect(screen.getByText('AAPL came back bullish, 7.2.')).toBeInTheDocument();

    // Nothing left to wait for: the polling stops.
    vi.mocked(chatApi.getConversation).mockClear();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(chatApi.getConversation).not.toHaveBeenCalled();
  });

  it('shows the dots and the stop button while the server runs its own turn, and the box blocks', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const BUSY: ChatConversation = { ...WAITING, message_count: 3, messages: [...ANSWERED.messages, NOTICE], busy: true, watched_runs: [] };
    vi.mocked(chatApi.getConversation).mockResolvedValue(BUSY);
    vi.mocked(chatApi.stopTurn).mockResolvedValue({ id: 'c1', stopped: true });
    renderPage('/chat/c1');
    await waitFor(() => expect(screen.getByTestId('chat-notice')).toBeInTheDocument());
    const dots = screen.getByTestId('chat-working');
    expect(screen.getByTestId('chat-notice').compareDocumentPosition(dots) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByTestId('chat-send')).toBeNull();
    expect(screen.getByTestId('chat-input')).toHaveAttribute('placeholder', expect.stringMatching(/Waiting for the reply|等待回复中/));

    // The stop button asks the server to stop that turn; until the poll sees it end, the unclickable "…" stands.
    fireEvent.click(screen.getByTestId('chat-stop'));
    await waitFor(() => expect(chatApi.stopTurn).toHaveBeenCalledWith('c1'));
    expect(screen.getByTestId('chat-stopping')).toBeInTheDocument();

    const STOPPED: ChatConversation = {
      ...BUSY, busy: false, message_count: 4,
      messages: [...BUSY.messages, { seq: 4, role: 'stopped', created_at: null, text: null, late: true }],
    };
    vi.mocked(chatApi.getConversation).mockResolvedValue(STOPPED);
    vi.mocked(chatApi.listConversations).mockClear();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    await waitFor(() => expect(screen.getByTestId('chat-stopped')).toBeInTheDocument());
    expect(screen.queryByTestId('chat-working')).toBeNull();
    expect(screen.getByTestId('chat-send')).toBeInTheDocument();
    // The server's turn cost tokens: the history list is refreshed.
    expect(chatApi.listConversations).toHaveBeenCalled();
  });
});

