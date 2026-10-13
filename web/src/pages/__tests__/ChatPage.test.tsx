import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
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
  },
}));

const { chatApi } = await import('../../api/chat');
const { default: ChatPage } = await import('../ChatPage');

const SUMMARY: ChatConversationSummary = {
  id: 'c1', title: 'hi', created_at: '2026-09-23T10:00:00', updated_at: '2026-09-23T10:00:00',
  message_count: 0, user_input_count: 0, total_tokens: 0, ended_at: null,
};
const EMPTY: ChatConversation = { ...SUMMARY, messages: [], pending: null };
const ANSWERED: ChatConversation = {
  ...SUMMARY,
  message_count: 2, user_input_count: 1, total_tokens: 738,
  messages: [
    { seq: 1, role: 'user', created_at: null, text: 'hi there' },
    { seq: 2, role: 'assistant', created_at: null, text: 'hello', usage: { input_tokens: 700, output_tokens: 38 }, llm: 'fake', time_ms: 5, transcript_chars: 100 },
  ],
  pending: null,
};

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
beforeEach(() => {
  vi.mocked(chatApi.listConversations).mockResolvedValue([]);
  vi.mocked(chatApi.createConversation).mockResolvedValue(EMPTY);
});

describe('ChatPage', () => {
  it('shows the sent line at once with pulsing dots, then the answer', async () => {
    let answer: (value: ChatConversation) => void = () => {};
    vi.mocked(chatApi.sendMessage).mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    render(
      <MemoryRouter initialEntries={['/chat']}>
        <UiLanguageProvider>
          <ChatPage />
        </UiLanguageProvider>
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: 'hi there' } });
    fireEvent.click(screen.getByTestId('chat-send'));

    // The user's line and the dots, before the server has answered.
    expect(await screen.findByTestId('chat-user')).toHaveTextContent('hi there');
    expect(screen.getByTestId('chat-working')).toBeInTheDocument();
    expect(screen.queryByText(/Thinking|思考中/)).toBeNull();
    expect(screen.getByTestId('chat-input')).toBeDisabled();

    vi.mocked(chatApi.listConversations).mockResolvedValue([{ ...SUMMARY, user_input_count: 1, total_tokens: 738 }]);
    await act(async () => {
      answer(ANSWERED);
    });
    await waitFor(() => expect(screen.getByText('hello')).toBeInTheDocument());
    expect(screen.queryByTestId('chat-working')).toBeNull();
    expect(screen.getAllByTestId('chat-user')).toHaveLength(1);
    expect(screen.getByTestId('chat-input')).toBeEnabled();
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
      pending: { calls: [{ call_id: 'c2', name: 'delete_run', input: { run_id: 'x' }, facts: {} }] },
    };
    vi.mocked(chatApi.getConversation).mockResolvedValue(partial);
    render(
      <MemoryRouter initialEntries={['/chat']}>
        <UiLanguageProvider>
          <ChatPage />
        </UiLanguageProvider>
      </MemoryRouter>,
    );
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
    expect(screen.getByTestId('chat-input')).toBeDisabled();

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
    render(
      <MemoryRouter initialEntries={['/chat']}>
        <UiLanguageProvider>
          <ChatPage />
        </UiLanguageProvider>
      </MemoryRouter>,
    );
    // The header's menus, with their symbols, float in the chat column's top right corner, on a shade that hugs them: no strip across the width.
    const band = screen.getByTestId('chat-band');
    expect(band).toHaveClass('absolute', 'top-0', 'right-0');
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
    render(
      <MemoryRouter initialEntries={['/chat']}>
        <UiLanguageProvider>
          <ChatPage />
        </UiLanguageProvider>
      </MemoryRouter>,
    );
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
      { seq: 3, role: 'stopped', created_at: null, text: '[The user asked to stop this reply, but it had already finished.]' },
    ],
    pending: null,
  };

  it('turns the arrow into a stop button, asks the server to stop on a click, and shows the stopped turn', async () => {
    let answer: (value: ChatConversation) => void = () => {};
    vi.mocked(chatApi.sendMessage).mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    vi.mocked(chatApi.stopTurn).mockResolvedValue({ id: 'c1', stopped: true });
    render(
      <MemoryRouter initialEntries={['/chat']}>
        <UiLanguageProvider>
          <ChatPage />
        </UiLanguageProvider>
      </MemoryRouter>,
    );
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
    expect(screen.getByTestId('chat-input')).toBeEnabled();
  });

  it('reports a stop that failed and offers the button again', async () => {
    vi.mocked(chatApi.sendMessage).mockReturnValue(new Promise(() => {}));
    vi.mocked(chatApi.stopTurn).mockRejectedValue(new Error('offline'));
    render(
      <MemoryRouter initialEntries={['/chat']}>
        <UiLanguageProvider>
          <ChatPage />
        </UiLanguageProvider>
      </MemoryRouter>,
    );
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
    used_tokens: 14200, percent: 1, compact_at_tokens: 835584, compact_at_percent: 85, chars_per_token: 4.1, calibrated: true,
    system_prompt_tokens: 2000, tools_tokens: 4000, conversation_tokens: 8200,
  };
  // Earlier tests' calls must not count here.
  beforeEach(() => vi.clearAllMocks());
  const page = () =>
    render(
      <MemoryRouter initialEntries={['/chat']}>
        <UiLanguageProvider>
          <ChatPage />
        </UiLanguageProvider>
      </MemoryRouter>,
    );
  const type = (text: string) => {
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: text } });
    fireEvent.click(screen.getByTestId('chat-send'));
  };

  it('answers /help and /context on the page, without a conversation, and sends nothing', async () => {
    vi.mocked(chatApi.getContext).mockResolvedValue(USAGE);
    page();
    type('/help');
    expect(await screen.findByTestId('chat-note-help')).toHaveTextContent('/compact');
    expect(screen.getByTestId('chat-empty')).toBeInTheDocument();
    type('/context');
    const note = await screen.findByTestId('chat-note-context');
    expect(chatApi.getContext).toHaveBeenCalledWith(null, 'en');
    expect(note).toHaveTextContent(/(14,200 of 983,040 tokens \(1%\)|14,200 \/ 983,040 tokens（1%）)/);
    expect(note).toHaveTextContent(/(minus 65,536|减去为回复预留的 65,536)/);
    expect(note).toHaveTextContent(/(measured from the last reply|按上一条回复实测)/);
    expect(screen.queryByTestId('chat-note-help')).toBeNull();
    expect(chatApi.sendMessage).not.toHaveBeenCalled();
    expect(chatApi.createConversation).not.toHaveBeenCalled();
  });

  it('refuses an unknown command and /compact with nothing to summarize', async () => {
    page();
    type('/model');
    expect(await screen.findByTestId('chat-error')).toHaveTextContent(/(Unknown command \/model|未知命令 \/model)/);
    type('/compact');
    expect(await screen.findByTestId('chat-error')).toHaveTextContent(/(Nothing to summarize yet|还没有可总结的内容)/);
    expect(chatApi.compact).not.toHaveBeenCalled();
    expect(chatApi.sendMessage).not.toHaveBeenCalled();
  });

  it('runs /compact as a turn and shows the summary step', async () => {
    vi.mocked(chatApi.sendMessage).mockResolvedValue(ANSWERED);
    const compacted: ChatConversation = {
      ...ANSWERED,
      messages: [
        ...ANSWERED.messages,
        { seq: 3, role: 'summary', created_at: null, text: 'Summary.', compacted: { trigger: 'manual', first_seq: 1, last_seq: 2, tokens_before: 738 }, usage: { input_tokens: 800, output_tokens: 20 }, llm: 'fake' },
      ],
    };
    vi.mocked(chatApi.compact).mockResolvedValue(compacted);
    page();
    type('hi there');
    await waitFor(() => expect(screen.getByText('hello')).toBeInTheDocument());
    type('/compact');
    await waitFor(() => expect(chatApi.compact).toHaveBeenCalledWith('c1', 'en'));
    expect(await screen.findByTestId('chat-summary')).toHaveTextContent('Summary.');
    expect(screen.getAllByTestId('chat-user')).toHaveLength(1);
    expect(screen.getByTestId('chat-input')).toBeEnabled();
  });
});
