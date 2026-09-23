import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import type { ChatConversation, ChatConversationSummary } from '../../api/chat';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { formatDateTime, rowKeyDown } from '../tiered-alt/altFormat';
import { AltModal, MODAL_BODY } from '../tiered-alt/AltUi';
import { ChatComposer } from './ChatComposer';
import { ChatThread, type TranscriptLoader } from './ChatThread';

// The column-name header and every conversation row share this
// template, so each value sits under its column name. The title column
// is twice as wide as the four fact columns; the last, narrow column is
// the trash button.
const ROW_GRID =
  'grid w-full grid-cols-2 gap-2 sm:grid-cols-[minmax(0,2fr)_repeat(4,minmax(0,1fr))_auto] sm:gap-3 md:gap-4';

// The column names, in row order (owner request 2026-09-23): the
// conversation's name, then how many messages the user sent, the
// tokens every LLM call cost together, when it started, and when the
// user last sent something.
const HEADER_KEYS = [
  'chat.history.h.title',
  'chat.history.h.inputs',
  'chat.history.h.tokens',
  'chat.history.h.start',
  'chat.history.h.end',
] as const;

export interface ChatHistoryProps {
  /** Every conversation, most recently touched first. */
  conversations: ChatConversationSummary[];
  expandedId: string | null;
  /** The expanded conversation with its messages, once loaded. */
  expanded: ChatConversation | null;
  /** Why the expanded conversation could not be loaded, or the last turn failed. */
  expandedError: string | null;
  /** A turn is in flight: the bot is thinking or running a tool. */
  working: boolean;
  onToggle: (id: string) => void;
  /** Send a message into the expanded conversation. */
  onSend: (text: string) => void;
  /** Answer the expanded conversation's held action. */
  onConfirm: (approved: boolean) => void;
  onDelete: (id: string) => void;
  /** The conversation whose removal is in flight, if any. */
  deletingId: string | null;
  /** Why the last removal failed, shown under that row. */
  deleteError: string | null;
  /** Test seam; production reads the reply's stored transcript. */
  transcriptLoader?: TranscriptLoader;
}

// The chat page's history, in the run history's shape (owner request
// 2026-09-23): a column-name header, then one row per conversation
// ending in a trash button. Clicking a row expands the whole
// conversation inline — its messages, the message box at the bottom —
// and clicking it again folds it. The trash asks once in the app's
// usual popup, and the server's refusal, if any, shows under the row.
export const ChatHistory = ({
  conversations,
  expandedId,
  expanded,
  expandedError,
  working,
  onToggle,
  onSend,
  onConfirm,
  onDelete,
  deletingId,
  deleteError,
  transcriptLoader,
}: ChatHistoryProps) => {
  const { t } = useUiLanguage();
  // The conversation whose trash button was clicked — its confirmation is open.
  const [confirmId, setConfirmId] = useState<string | null>(null);
  // The conversation whose removal was last confirmed: the error, if any, goes under it.
  const [removedId, setRemovedId] = useState<string | null>(null);

  if (conversations.length === 0) {
    return <p className="py-8 text-center text-sm text-gray-600">{t('chat.history.none')}</p>;
  }

  return (
    <div className="flex w-full flex-col gap-4">
      {/* Column names, so each row value reads without guessing. */}
      <div data-testid="chat-history-header" className={cn(ROW_GRID, 'border-b border-gray-800 pb-1.5')}>
        {HEADER_KEYS.map((key) => (
          <span key={key} className="text-xs font-semibold text-gray-500">
            {t(key)}
          </span>
        ))}
        {/* The trash column has no name. */}
        <span aria-hidden="true" className="w-6" />
      </div>
      <ul className="flex flex-col divide-y divide-gray-800">
        {conversations.map((conversation) => {
          const isExpanded = conversation.id === expandedId;
          const isLoaded = isExpanded && expanded?.id === conversation.id;
          const pending = isLoaded ? (expanded?.pending?.calls[0] ?? null) : null;
          const isDeleting = deletingId === conversation.id;
          const trashLabel = isDeleting ? t('chat.history.deleting') : t('chat.history.delete');
          const disabledHint = pending
            ? t('chat.composer.waitConfirm')
            : working
              ? t('chat.composer.sending')
              : null;
          return (
            <li key={conversation.id}>
              {/* A div with the button role, so the trash inside can be a real button. */}
              <div
                role="button"
                tabIndex={0}
                data-testid="chat-conversation"
                aria-expanded={isExpanded}
                onClick={() => onToggle(conversation.id)}
                onKeyDown={rowKeyDown(() => onToggle(conversation.id))}
                className={cn(
                  ROW_GRID,
                  'cursor-pointer items-center rounded py-2.5 text-start text-sm hover:bg-gray-800/60',
                  isExpanded ? 'bg-gray-800/40' : '',
                )}
              >
                <span className="truncate font-semibold text-gray-300">
                  {conversation.title ?? t('chat.untitled')}
                </span>
                <span className="text-xs tabular-nums text-gray-400">{conversation.question_count}</span>
                <span className="text-xs tabular-nums text-gray-400">{conversation.total_tokens}</span>
                <span className="truncate text-xs tabular-nums text-gray-400">
                  {formatDateTime(conversation.created_at)}
                </span>
                <span className="truncate text-xs tabular-nums text-gray-400">
                  {formatDateTime(conversation.last_question_at)}
                </span>
                {/* A click here removes the conversation, never toggles the row. */}
                <button
                  type="button"
                  data-testid="chat-conversation-delete"
                  aria-label={trashLabel}
                  title={trashLabel}
                  disabled={isDeleting}
                  onClick={(event) => {
                    event.stopPropagation();
                    setConfirmId(conversation.id);
                  }}
                  className="cursor-pointer justify-self-end rounded p-1 text-gray-600 hover:text-red-300 disabled:cursor-default disabled:opacity-50 disabled:hover:text-gray-600"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              {deleteError && removedId === conversation.id ? (
                <p className="pb-2 text-xs text-amber-300" data-testid="chat-conversation-delete-error">
                  {deleteError}
                </p>
              ) : null}
              {isExpanded ? (
                <div className="flex flex-col gap-3 pb-5 pt-3" data-testid="chat-expanded">
                  {isLoaded && expanded ? (
                    <ChatThread
                      conversationId={expanded.id}
                      messages={expanded.messages}
                      pending={pending}
                      working={working}
                      onConfirm={onConfirm}
                      transcriptLoader={transcriptLoader}
                    />
                  ) : expandedError ? null : (
                    <p className="text-sm text-gray-500">{t('chat.history.loading')}</p>
                  )}
                  {expandedError ? (
                    <p className="text-xs text-amber-300" data-testid="chat-error">
                      {expandedError}
                    </p>
                  ) : null}
                  {isLoaded ? (
                    <ChatComposer disabled={working || pending !== null} disabledHint={disabledHint} onSend={onSend} />
                  ) : null}
                </div>
              ) : null}
              <AltModal isOpen={confirmId === conversation.id} onClose={() => setConfirmId(null)}>
                <div className={MODAL_BODY}>
                  <p>{t('chat.history.deleteAsk')}</p>
                  <div className="flex justify-end gap-4 pt-1">
                    <button
                      type="button"
                      className="cursor-pointer text-gray-400 hover:text-gray-200"
                      onClick={() => setConfirmId(null)}
                    >
                      {t('chat.history.keep')}
                    </button>
                    <button
                      type="button"
                      data-testid="chat-conversation-delete-confirm"
                      className="cursor-pointer font-semibold text-red-300 hover:text-red-200"
                      onClick={() => {
                        setConfirmId(null);
                        setRemovedId(conversation.id);
                        onDelete(conversation.id);
                      }}
                    >
                      {t('chat.history.confirmDelete')}
                    </button>
                  </div>
                </div>
              </AltModal>
            </li>
          );
        })}
      </ul>
    </div>
  );
};
