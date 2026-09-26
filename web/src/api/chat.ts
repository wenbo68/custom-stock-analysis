import apiClient from './index';
import type { UiLanguage } from '../i18n/uiText';
import type { TieredTranscriptCall } from './tiered';

// Types mirror the backend JSON verbatim (api/v1/endpoints/chat_schemas.py).

export type ChatRole = 'user' | 'assistant' | 'tool';

export type ChatToolCall = {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
};

export type ChatUsage = {
  input_tokens: number | null;
  output_tokens: number | null;
};

export type ChatMessage = {
  seq: number;
  role: ChatRole;
  created_at: string | null;
  /** User and assistant rows. */
  text?: string | null;
  /** Assistant rows: the tools the model asked for. */
  tool_calls?: ChatToolCall[];
  usage?: ChatUsage | null;
  /** Assistant rows: the model that answered (the page's "llm" fact). */
  llm?: string | null;
  /** Assistant rows: the LLM call failed with this. */
  error?: string | null;
  /** Assistant rows: `tool_call_limit` when the turn hit the tool-call
   *  limit; `wrong_language` when the reply is not in the chosen
   *  language (the bot is asked again, up to twice; the last one stands). */
  notice?: string | null;
  /** Assistant rows: how long the LLM call took. Tool rows: how long
   *  the tool ran (null when nothing ran). */
  time_ms?: number | null;
  /** Assistant rows: how much text the call's transcript holds (prompt
   *  and reply), fetched with `getTranscript`; null without one. */
  transcript_chars?: number | null;
  /** Tool rows: which call this answers and what came back. */
  tool_call_id?: string | null;
  name?: string | null;
  output?: unknown;
  output_chars?: number | null;
  truncated?: boolean | null;
  /** Tool rows that waited for the user: their answer. */
  approved?: boolean | null;
  /** Tool rows: the inputs the tool ran with, every default filled in
   *  (2026-09-24). Null when the model's arguments never parsed, and
   *  absent on rows stored before then — fall back to the assistant
   *  row's `tool_calls`. */
  input?: Record<string, unknown> | null;
};

export type ChatPendingCall = {
  call_id: string;
  name: string;
  /** The inputs the tool would run with, every default filled in. */
  input: Record<string, unknown>;
  facts: Record<string, unknown>;
};

export type ChatConversationSummary = {
  id: string;
  title: string | null;
  created_at: string | null;
  updated_at: string | null;
  message_count: number;
  /** How many messages the user sent: the conversation's questions. */
  user_input_count: number;
  /** Tokens every LLM call in the conversation used, together. */
  total_tokens: number;
  /** When the user last sent a message; null before the first. */
  ended_at: string | null;
};

export type ChatConversation = ChatConversationSummary & {
  messages: ChatMessage[];
  pending: { calls: ChatPendingCall[] } | null;
};

// A turn may run several tool calls through the model; far longer than
// the client's default 30 s.
const TURN_TIMEOUT_MS = 180_000;

export const chatApi = {
  listConversations: async (): Promise<ChatConversationSummary[]> => {
    const response = await apiClient.get<{ items: ChatConversationSummary[] }>('/api/v1/chat/conversations');
    return response.data.items;
  },

  createConversation: async (): Promise<ChatConversation> => {
    const response = await apiClient.post<ChatConversation>('/api/v1/chat/conversations');
    return response.data;
  },

  getConversation: async (id: string): Promise<ChatConversation> => {
    const response = await apiClient.get<ChatConversation>(`/api/v1/chat/conversations/${id}`);
    return response.data;
  },

  deleteConversation: async (id: string): Promise<void> => {
    await apiClient.delete(`/api/v1/chat/conversations/${id}`);
  },

  // Every turn carries the language the user chose for the app; the bot
  // answers in it whatever language the message is written in.
  sendMessage: async (id: string, text: string, language: UiLanguage): Promise<ChatConversation> => {
    const response = await apiClient.post<ChatConversation>(
      `/api/v1/chat/conversations/${id}/messages`,
      { text, language },
      { timeout: TURN_TIMEOUT_MS },
    );
    return response.data;
  },

  // One bot reply's LLM call — the exact input, the raw output, the
  // llm, time and tokens — in the same shape as a run's LLM call.
  getTranscript: async (id: string, seq: number): Promise<TieredTranscriptCall> => {
    const response = await apiClient.get<TieredTranscriptCall>(
      `/api/v1/chat/conversations/${id}/messages/${seq}/transcript`,
    );
    return response.data;
  },

  confirm: async (id: string, approved: boolean, language: UiLanguage): Promise<ChatConversation> => {
    const response = await apiClient.post<ChatConversation>(
      `/api/v1/chat/conversations/${id}/confirm`,
      { approved, language },
      { timeout: TURN_TIMEOUT_MS },
    );
    return response.data;
  },
};
