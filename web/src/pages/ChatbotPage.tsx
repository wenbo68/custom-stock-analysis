import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { chatApi, type ChatConversation, type ChatConversationSummary } from '../api/chat';
import { ChatComposer } from '../components/chatbot/ChatComposer';
import { ChatHistory } from '../components/chatbot/ChatHistory';
import { useUiLanguage } from '../contexts/UiLanguageContext';

// The chat page, in the analysis page's shape (owner request
// 2026-09-23): a "new chat" box at the top, and under it the
// conversation history — one row per conversation that expands in
// place to show the whole exchange with its message box. A
// conversation is only created on the first message, so visiting the
// page never leaves empty rows behind; the moment one is created it
// appears at the top of the history, expanded, and the bot's reply
// lands there. Each send (and each yes/no to a held action) is one
// request that returns the whole conversation, so the page never has
// to merge partial updates.
const ChatbotPage = () => {
  const { t } = useUiLanguage();
  const [conversations, setConversations] = useState<ChatConversationSummary[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ChatConversation | null>(null);
  const [expandedError, setExpandedError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [newError, setNewError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const refreshList = useCallback(async () => {
    try {
      setConversations(await chatApi.listConversations());
    } catch (listError) {
      setNewError(describe(listError, t));
    }
  }, [t]);

  useEffect(() => {
    void refreshList();
  }, [refreshList]);

  // Open a row (loading its messages) or fold the open one.
  const toggle = useCallback(
    async (id: string) => {
      setDeleteError(null);
      if (id === expandedId) {
        setExpandedId(null);
        setExpanded(null);
        setExpandedError(null);
        return;
      }
      setExpandedId(id);
      setExpanded(null);
      setExpandedError(null);
      try {
        setExpanded(await chatApi.getConversation(id));
      } catch (openError) {
        setExpandedError(describe(openError, t));
      }
    },
    [expandedId, t],
  );

  // One turn against a conversation: the bot's answer replaces the
  // expanded conversation — unless the reader has since opened another
  // row, whose messages then stay in view.
  const applyTurn = async (turn: () => Promise<ChatConversation>, id: string) => {
    setWorking(true);
    setExpandedError(null);
    try {
      const result = await turn();
      setExpanded((current) => (current && current.id !== result.id ? current : result));
      await refreshList();
    } catch (turnError) {
      setExpandedError(describe(turnError, t));
      // The server may have stored part of the turn (the user's line, a
      // tool's result) before failing; show what it has.
      try {
        const stored = await chatApi.getConversation(id);
        setExpanded((current) => (current && current.id !== stored.id ? current : stored));
      } catch {
        // keep what we had
      }
    } finally {
      setWorking(false);
    }
  };

  // The top box: create the conversation, show it expanded at the top
  // of the history, then send the first message into it.
  const startNew = (text: string) =>
    void (async () => {
      setWorking(true);
      setNewError(null);
      let created: ChatConversation;
      try {
        created = await chatApi.createConversation();
      } catch (createError) {
        setNewError(describe(createError, t));
        setWorking(false);
        return;
      }
      setExpandedId(created.id);
      setExpanded(created);
      setExpandedError(null);
      setDeleteError(null);
      await refreshList();
      await applyTurn(() => chatApi.sendMessage(created.id, text), created.id);
    })();

  const send = (text: string) => {
    if (!expanded) {
      return;
    }
    void applyTurn(() => chatApi.sendMessage(expanded.id, text), expanded.id);
  };

  const confirm = (approved: boolean) => {
    if (!expanded) {
      return;
    }
    void applyTurn(() => chatApi.confirm(expanded.id, approved), expanded.id);
  };

  const remove = async (id: string) => {
    setDeletingId(id);
    setDeleteError(null);
    try {
      await chatApi.deleteConversation(id);
    } catch (removeError) {
      setDeleteError(describe(removeError, t));
      return;
    } finally {
      setDeletingId(null);
    }
    if (expandedId === id) {
      setExpandedId(null);
      setExpanded(null);
      setExpandedError(null);
    }
    await refreshList();
  };

  return (
    <main className="mx-auto flex min-h-full w-full max-w-7xl flex-col gap-6 px-4 pb-8 pt-4 md:px-6 lg:px-8">
      <section className="flex flex-col gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">{t('chat.new')}</h2>
        <div className="flex flex-col gap-4 rounded bg-gray-900 p-4 text-gray-400 sm:p-6" data-testid="chat-new">
          <div className="flex flex-col gap-1">
            <p className="text-base font-semibold text-gray-200">{t('chat.empty.title')}</p>
            <p className="max-w-prose text-sm leading-relaxed text-gray-400">{t('chat.empty.hint')}</p>
          </div>
          <ChatComposer
            disabled={working}
            disabledHint={working ? t('chat.composer.sending') : null}
            onSend={startNew}
          />
          {newError ? (
            <p className="text-xs text-amber-300" data-testid="chat-new-error">
              {newError}
            </p>
          ) : null}
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">{t('chat.history')}</h2>
        <div className="rounded bg-gray-900 p-4 text-gray-400 sm:p-6">
          <ChatHistory
            conversations={conversations}
            expandedId={expandedId}
            expanded={expanded}
            expandedError={expandedError}
            working={working}
            onToggle={(id) => void toggle(id)}
            onSend={send}
            onConfirm={confirm}
            onDelete={(id) => void remove(id)}
            deletingId={deletingId}
            deleteError={deleteError}
          />
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

export default ChatbotPage;
