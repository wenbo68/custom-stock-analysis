import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import type { ChatConversationSummary } from '../../api/chat';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { formatDateTime } from '../analysis/format';
import { Modal, MODAL_BODY } from '../analysis/Ui';
import { CHAT_SURFACE_1, CHAT_SURFACE_2, CHAT_SURFACE_2_HOVER } from './chatSurfaces';

export interface ChatSidebarProps {
  conversations: ChatConversationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

// A small icon button at the far right of a row: the heading's "+" and
// each entry's trash share it, so the two icons sit on one vertical
// line (owner request 2026-09-27).
const ROW_END_BUTTON = 'cursor-pointer px-2 transition';

// The chat page's left panel: the history of conversations, most
// recently touched first, as a chat app lays it out: the list on the
// left, the open one on the right. A "+" at the far end of the
// heading's row starts a new one. Each entry is its four facts (owner
// request 2026-09-23; no title) — how many messages the user sent, the
// tokens every LLM call cost together, when it started and when the
// user last wrote — in the same size and quiet-label / bright-value
// styling as a tool call's or LLM call's fact lines (owner request
// 2026-09-23). The size class sits on the list, not the entry's button:
// index.css resets every button's font to `inherit` outside Tailwind's
// layers, which beats a size utility set on the button itself (that
// made the entries render larger than the tool and LLM fact lines,
// 2026-09-24). The heading, its "+" and the list all sit in the page's
// one level-1 panel, which fills the column from the window's top edge
// to its bottom and from its left edge (owner request 2026-09-26, so no
// rounded corners and no side padding: the heading carries the same
// side inset as an entry's text, and an entry's backdrop runs to the
// panel's edges). The active entry carries the level-2 surface on top
// of the panel, with its trash button on that same surface. Deleting
// asks once, in the app's usual popup.
export const ChatSidebar = ({ conversations, activeId, onSelect, onNew, onDelete }: ChatSidebarProps) => {
  const { t } = useUiLanguage();
  const [confirmId, setConfirmId] = useState<string | null>(null);

  return (
    <nav
      aria-label={t('chat.sidebar.title')}
      className={cn('flex min-h-0 flex-1 flex-col py-3 text-gray-400', CHAT_SURFACE_1)}
      data-testid="chat-sidebar"
    >
      {/* No right inset on the row: the "+" carries the trash buttons' own side padding, so the icons line up. */}
      <div className="flex items-center justify-between gap-2 pl-3" data-testid="chat-sidebar-heading">
        <h2 className="py-1.5 text-xs font-semibold uppercase tracking-wider text-gray-500">{t('chat.sidebar.title')}</h2>
        <button
          type="button"
          data-testid="chat-new"
          aria-label={t('chat.new')}
          title={t('chat.new')}
          onClick={onNew}
          className={cn(ROW_END_BUTTON, 'py-1.5 text-gray-400 hover:text-gray-100')}
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
      <ul className="mt-1 flex min-h-0 flex-col gap-0.5 overflow-y-auto text-xs" data-testid="chat-sidebar-scroll">
        {conversations.map((conversation) => {
          const isActive = conversation.id === activeId;
          const facts: [string, string][] = [
            [t('chat.facts.inputs'), String(conversation.user_input_count)],
            [t('chat.facts.tokens'), String(conversation.total_tokens)],
            [t('chat.facts.start'), formatDateTime(conversation.created_at)],
            [t('chat.facts.end'), formatDateTime(conversation.ended_at)],
          ];
          return (
            <li
              key={conversation.id}
              className={cn(
                'group flex items-start rounded transition',
                isActive ? CHAT_SURFACE_2 : CHAT_SURFACE_2_HOVER,
              )}
            >
              <button
                type="button"
                data-testid="chat-conversation"
                aria-current={isActive ? 'page' : undefined}
                onClick={() => onSelect(conversation.id)}
                className="flex min-w-0 flex-1 cursor-pointer flex-col gap-0.5 px-3 py-2 text-left"
              >
                {facts.map(([label, value]) => (
                  <span key={label} className="text-gray-500">
                    {label}
                    {': '}
                    <span className="font-semibold text-gray-200">{value}</span>
                  </span>
                ))}
              </button>
              <button
                type="button"
                data-testid="chat-conversation-delete"
                aria-label={t('chat.sidebar.delete')}
                title={t('chat.sidebar.delete')}
                onClick={() => setConfirmId(conversation.id)}
                className={cn(
                  ROW_END_BUTTON,
                  'py-2.5 text-gray-500 hover:text-red-300 focus:opacity-100 group-hover:opacity-100',
                  isActive ? 'opacity-100' : 'opacity-0',
                )}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </li>
          );
        })}
      </ul>
      <Modal isOpen={confirmId !== null} onClose={() => setConfirmId(null)}>
        <div className={MODAL_BODY}>
          <p>{t('chat.sidebar.deleteAsk')}</p>
          <div className="flex items-center gap-4 pt-1 text-xs">
            <button
              type="button"
              data-testid="chat-conversation-delete-confirm"
              className="cursor-pointer font-semibold text-red-300 hover:text-red-200"
              onClick={() => {
                const id = confirmId;
                setConfirmId(null);
                if (id) {
                  onDelete(id);
                }
              }}
            >
              {t('chat.sidebar.confirmDelete')}
            </button>
            <button
              type="button"
              className="cursor-pointer text-gray-400 hover:text-gray-200"
              onClick={() => setConfirmId(null)}
            >
              {t('chat.sidebar.keep')}
            </button>
          </div>
        </div>
      </Modal>
    </nav>
  );
};
