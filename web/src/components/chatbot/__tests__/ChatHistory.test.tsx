import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ChatConversation, ChatConversationSummary } from '../../../api/chat';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { formatDateTime } from '../../tiered-alt/altFormat';
import { ChatHistory, type ChatHistoryProps } from '../ChatHistory';

afterEach(cleanup);

const CONVERSATIONS: ChatConversationSummary[] = [
  {
    id: 'a', title: 'show my NVDA runs', created_at: '2026-09-21T10:00:00', updated_at: '2026-09-21T10:05:00',
    message_count: 4, question_count: 2, total_tokens: 8316, last_question_at: '2026-09-21T10:04:00',
  },
  {
    id: 'b', title: null, created_at: '2026-09-20T10:00:00', updated_at: '2026-09-20T10:00:00',
    message_count: 0, question_count: 0, total_tokens: 0, last_question_at: null,
  },
];

const OPENED: ChatConversation = {
  ...CONVERSATIONS[0],
  messages: [
    { seq: 1, role: 'user', created_at: null, text: 'show my NVDA runs' },
    {
      seq: 2, role: 'assistant', created_at: null, text: 'You have one.',
      usage: { prompt_tokens: 3000, completion_tokens: 1000 }, model: 'fake', duration_ms: 10, transcript_chars: 100,
    },
  ],
  pending: null,
};

const renderHistory = (overrides: Partial<ChatHistoryProps> = {}) => {
  const props: ChatHistoryProps = {
    conversations: CONVERSATIONS,
    expandedId: null,
    expanded: null,
    expandedError: null,
    working: false,
    onToggle: vi.fn(),
    onSend: vi.fn(),
    onConfirm: vi.fn(),
    onDelete: vi.fn(),
    deletingId: null,
    deleteError: null,
    transcriptLoader: vi.fn(),
    ...overrides,
  };
  render(
    <UiLanguageProvider>
      <ChatHistory {...props} />
    </UiLanguageProvider>,
  );
  return props;
};

describe('ChatHistory', () => {
  it('lists one row per conversation under column names, in order: name, user inputs, tokens, start date, end date, trash', () => {
    renderHistory();
    const header = screen.getByTestId('chat-history-header');
    expect(Array.from(header.children).map((cell) => cell.textContent)).toEqual([
      expect.stringMatching(/^(Conversation|对话)$/),
      expect.stringMatching(/^(User inputs|用户输入)$/),
      expect.stringMatching(/^(Total tokens|总 tokens)$/),
      expect.stringMatching(/^(Start date|开始日期)$/),
      expect.stringMatching(/^(End date|结束日期)$/),
      '', // the trash column has no name
    ]);
    const rows = screen.getAllByTestId('chat-conversation');
    expect(rows).toHaveLength(2);
    expect(Array.from(rows[0].children).map((cell) => cell.textContent)).toEqual([
      'show my NVDA runs',
      '2',
      '8316',
      formatDateTime('2026-09-21T10:00:00'),
      formatDateTime('2026-09-21T10:04:00'),
      '', // the trash button
    ]);
    expect(Array.from(rows[0].children).at(-1)).toHaveAttribute('data-testid', 'chat-conversation-delete');
    // An untitled conversation is named, and a never-asked one shows a dash.
    expect(rows[1]).toHaveTextContent(/New conversation|新对话/);
    expect(Array.from(rows[1].children).at(-2)).toHaveTextContent('—');
    // The header and every row share the grid, so each value sits under its column name.
    expect(rows[0].className).toContain('grid');
    expect(header.className).toContain('grid');
  });

  it('says so when there is nothing yet', () => {
    renderHistory({ conversations: [] });
    expect(screen.getByText(/No conversations yet|还没有对话/)).toBeInTheDocument();
    expect(screen.queryByTestId('chat-history-header')).toBeNull();
  });

  it('asks to open a row, and opens the conversation in place with its message box', () => {
    const props = renderHistory();
    fireEvent.click(screen.getAllByTestId('chat-conversation')[1]);
    expect(props.onToggle).toHaveBeenCalledWith('b');
    expect(screen.queryByTestId('chat-expanded')).toBeNull();
    cleanup();

    renderHistory({ expandedId: 'a', expanded: OPENED });
    const rows = screen.getAllByTestId('chat-conversation');
    expect(rows[0]).toHaveAttribute('aria-expanded', 'true');
    expect(rows[1]).toHaveAttribute('aria-expanded', 'false');
    const opened = within(screen.getByTestId('chat-expanded'));
    expect(opened.getByTestId('chat-user')).toHaveTextContent('show my NVDA runs');
    expect(opened.getByTestId('chat-usage')).toHaveTextContent('4000');
    // The message box sits at the bottom of the open conversation.
    fireEvent.change(opened.getByTestId('chat-input'), { target: { value: 'and AAPL?' } });
    fireEvent.click(opened.getByTestId('chat-send'));
    expect(screen.getAllByTestId('chat-expanded')).toHaveLength(1);
  });

  it('sends into the open conversation and holds the box while a question waits', () => {
    const props = renderHistory({ expandedId: 'a', expanded: OPENED });
    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: 'and AAPL?' } });
    fireEvent.click(screen.getByTestId('chat-send'));
    expect(props.onSend).toHaveBeenCalledWith('and AAPL?');
    cleanup();

    const held: ChatConversation = {
      ...OPENED,
      pending: { calls: [{ call_id: 'c1', name: 'list_tickers', arguments: {}, facts: {} }] },
    };
    renderHistory({ expandedId: 'a', expanded: held });
    expect(screen.getByTestId('chat-input')).toBeDisabled();
    expect(screen.getByText(/Answer the question above first|请先回答上面的问题/)).toBeInTheDocument();
  });

  it('shows a loading line until the open conversation arrives, and the error when it does not', () => {
    renderHistory({ expandedId: 'a', expanded: null });
    expect(screen.getByText(/^(Loading…|加载中…)$/)).toBeInTheDocument();
    expect(screen.queryByTestId('chat-input')).toBeNull();
    cleanup();

    renderHistory({ expandedId: 'a', expanded: null, expandedError: 'Could not send: boom' });
    expect(screen.getByTestId('chat-error')).toHaveTextContent('boom');
    expect(screen.queryByText(/^(Loading…|加载中…)$/)).toBeNull();
  });

  it('ends every row in a trash button that deletes after a confirmation, without opening the row', () => {
    const props = renderHistory();
    const trashes = screen.getAllByTestId('chat-conversation-delete');
    expect(trashes).toHaveLength(2);
    expect(trashes[0]).not.toHaveTextContent(/Delete/);
    expect(trashes[0].getAttribute('aria-label')).toMatch(/Delete this conversation|删除这个对话/);
    fireEvent.click(trashes[0]);
    expect(props.onToggle).not.toHaveBeenCalled();
    expect(props.onDelete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText(/^Keep$|^保留$/));
    expect(props.onDelete).not.toHaveBeenCalled();
    fireEvent.click(trashes[0]);
    fireEvent.click(screen.getByTestId('chat-conversation-delete-confirm'));
    expect(props.onDelete).toHaveBeenCalledWith('a');
    cleanup();

    renderHistory({ deletingId: 'a' });
    const [deleting, other] = screen.getAllByTestId('chat-conversation-delete');
    expect(deleting).toBeDisabled();
    expect(deleting.getAttribute('aria-label')).toMatch(/Deleting…|删除中…/);
    expect(other).toBeEnabled();
    cleanup();

    // The refusal shows under the row whose removal was confirmed.
    renderHistory({ deleteError: 'Could not send: nope' });
    expect(screen.queryByTestId('chat-conversation-delete-error')).toBeNull();
    fireEvent.click(screen.getAllByTestId('chat-conversation-delete')[1]);
    fireEvent.click(screen.getByTestId('chat-conversation-delete-confirm'));
    const error = screen.getByTestId('chat-conversation-delete-error');
    expect(error).toHaveTextContent('nope');
    const rows = screen.getAllByTestId('chat-conversation');
    expect(rows[1].compareDocumentPosition(error) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(rows[0].compareDocumentPosition(error) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('opens a row from the keyboard, as a button would', () => {
    const props = renderHistory();
    fireEvent.keyDown(screen.getAllByTestId('chat-conversation')[0], { key: 'Enter' });
    expect(props.onToggle).toHaveBeenCalledWith('a');
    fireEvent.keyDown(screen.getAllByTestId('chat-conversation')[1], { key: ' ' });
    expect(props.onToggle).toHaveBeenCalledWith('b');
  });
});
