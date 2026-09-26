import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { ChatConversationSummary } from '../../../api/chat';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { formatDateTime } from '../../analysis/format';
import { ChatSidebar } from '../ChatSidebar';

afterEach(cleanup);

const CONVERSATIONS: ChatConversationSummary[] = [
  {
    id: 'a', title: 'show my NVDA runs', created_at: '2026-09-21T10:00:00', updated_at: '2026-09-21T10:05:00',
    message_count: 4, user_input_count: 2, total_tokens: 3000, ended_at: '2026-09-21T10:04:00',
  },
  {
    id: 'b', title: null, created_at: '2026-09-20T10:00:00', updated_at: '2026-09-20T10:00:00',
    message_count: 0, user_input_count: 0, total_tokens: 0, ended_at: null,
  },
];

const renderSidebar = (activeId: string | null = 'a') => {
  const props = { onSelect: vi.fn(), onNew: vi.fn(), onDelete: vi.fn() };
  render(
    <MemoryRouter initialEntries={['/chat']}>
      <UiLanguageProvider>
        <ChatSidebar conversations={CONVERSATIONS} activeId={activeId} {...props} />
      </UiLanguageProvider>
    </MemoryRouter>,
  );
  return props;
};

// A fact line is one span whose full text is "label: value".
const factLines = (row: HTMLElement) => Array.from(row.children).map((line) => line.textContent);

describe('ChatSidebar', () => {
  it('is headed "History" with a "+" for a new chat, lined up with the trash buttons', () => {
    const props = renderSidebar();
    expect(screen.getByRole('heading')).toHaveTextContent(/^(History|历史)$/);
    const plus = screen.getByTestId('chat-new');
    expect(plus).not.toHaveTextContent(/New chat/);
    expect(plus.getAttribute('aria-label')).toMatch(/New chat|新对话/);
    // The heading and the "+" sit at opposite ends of their row.
    expect(plus.parentElement).toHaveClass('justify-between');
    // The "+" and every trash button carry the same side padding and icon
    // size, and the row has no right inset of its own, so the two icons
    // share one vertical line.
    const [trash] = screen.getAllByTestId('chat-conversation-delete');
    expect(plus).toHaveClass('px-2');
    expect(trash).toHaveClass('px-2');
    expect(plus.parentElement!.className).not.toMatch(/px-|pr-/);
    expect(plus.querySelector('svg')).toHaveClass('h-3.5', 'w-3.5');
    expect(trash.querySelector('svg')).toHaveClass('h-3.5', 'w-3.5');
    fireEvent.click(plus);
    expect(props.onNew).toHaveBeenCalled();
  });

  it('shows every conversation as its four facts, in order, with no title', () => {
    renderSidebar();
    const rows = screen.getAllByTestId('chat-conversation');
    expect(rows).toHaveLength(2);
    expect(rows[0]).not.toHaveTextContent('show my NVDA runs');
    expect(factLines(rows[0])).toEqual([
      expect.stringMatching(/^(user inputs|用户输入): 2$/),
      expect.stringMatching(/^(total tokens|总 tokens): 3000$/),
      expect.stringMatching(new RegExp(`^(start date|开始日期): ${formatDateTime('2026-09-21T10:00:00')}$`)),
      expect.stringMatching(new RegExp(`^(end date|结束日期): ${formatDateTime('2026-09-21T10:04:00')}$`)),
    ]);
    // A never-asked conversation has no end date yet.
    expect(factLines(rows[1]).at(-1)).toMatch(/: —$/);
    // Quiet label, bright value — the tool-call fact styling, at its size.
    // The size lives on the list and reaches the entry by inheritance:
    // index.css resets every button's font to `inherit` outside
    // Tailwind's layers, so a size class on the button itself is
    // ignored and the entries render larger than the tool fact lines.
    expect(screen.getByTestId('chat-sidebar-scroll')).toHaveClass('text-xs');
    expect(rows[0]).not.toHaveClass('text-xs');
    expect(screen.getByText('3000')).toHaveClass('font-semibold', 'text-gray-200');
    expect(screen.getByText('3000').parentElement).toHaveClass('text-gray-500');
  });

  it('marks the active conversation with the level-2 surface, on the level-1 panel, and keeps its trash on that surface', () => {
    renderSidebar();
    const rows = screen.getAllByTestId('chat-conversation');
    expect(rows[0]).toHaveAttribute('aria-current', 'page');
    expect(rows[1]).not.toHaveAttribute('aria-current');
    const activeEntry = rows[0].parentElement!;
    expect(activeEntry).toHaveClass('bg-gray-800');
    expect(rows[1].parentElement).not.toHaveClass('bg-gray-800');
    const panel = screen.getByTestId('chat-sidebar');
    expect(panel).toHaveClass('bg-gray-900');
    const [activeTrash, otherTrash] = screen.getAllByTestId('chat-conversation-delete');
    expect(activeTrash.parentElement).toBe(activeEntry);
    expect(activeTrash).toHaveClass('opacity-100');
    expect(otherTrash).toHaveClass('opacity-0');
    expect(panel).toContainElement(activeEntry);
    // The heading and its "+" sit on the panel too, and it has no side inset or rounding: it meets the window's edges.
    expect(panel).toContainElement(screen.getByRole('heading', { level: 2 }));
    expect(panel).toContainElement(screen.getByTestId('chat-new'));
    expect(panel.className).not.toMatch(/px-|p-4|rounded/);
  });

  it('holds no settings: the mode, language and color menus float over the chat instead', () => {
    renderSidebar();
    expect(screen.queryByText('Mode')).toBeNull();
    expect(screen.queryByText('Color')).toBeNull();
    expect(screen.queryByText('Language')).toBeNull();
  });

  it('selects and deletes after a confirmation', () => {
    const props = renderSidebar();
    fireEvent.click(screen.getAllByTestId('chat-conversation')[1]);
    expect(props.onSelect).toHaveBeenCalledWith('b');

    fireEvent.click(screen.getAllByTestId('chat-conversation-delete')[0]);
    expect(props.onDelete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText(/^Keep$|^保留$/));
    expect(props.onDelete).not.toHaveBeenCalled();
    fireEvent.click(screen.getAllByTestId('chat-conversation-delete')[0]);
    fireEvent.click(screen.getByTestId('chat-conversation-delete-confirm'));
    expect(props.onDelete).toHaveBeenCalledWith('a');
  });
});
