import apiClient from './index';
import type { TieredTranscriptCall } from './tiered';

// Types mirror the backend JSON verbatim (api/v1/endpoints/chat_schemas.py).

export type ChatRole = 'user' | 'assistant' | 'tool';

export type ChatToolCall = {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
};

export type ChatUsage = {
  prompt_tokens: number | null;
  completion_tokens: number | null;
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
  model?: string | null;
  /** Assistant rows: the model call failed with this. */
  error?: string | null;
  /** Assistant rows: `step_cap` when the turn hit the tool-round limit. */
  notice?: string | null;
  /** Assistant rows: how long the model call took. Tool rows: how long
   *  the tool ran (null when nothing ran). */
  duration_ms?: number | null;
  /** Assistant rows: how much text the call's transcript holds (prompt
   *  and reply), fetched with `getTranscript`; null without one. */
  transcript_chars?: number | null;
  /** Tool rows: which call this answers and what came back. */
  tool_call_id?: string | null;
  tool_name?: string | null;
  result?: unknown;
  result_chars?: number | null;
  truncated?: boolean | null;
  /** Tool rows that waited for the user: their answer. */
  approved?: boolean | null;
};

export type ChatPendingCall = {
  call_id: string;
  name: string;
  arguments: Record<string, unknown>;
  facts: Record<string, unknown>;
};

export type ChatConversationSummary = {
  id: string;
  title: string | null;
  created_at: string | null;
  updated_at: string | null;
  message_count: number;
  /** How many messages the user sent: the conversation's questions. */
  question_count: number;
  /** Tokens every LLM call in the conversation used, together. */
  total_tokens: number;
  /** When the user last sent a message; null before the first. */
  last_question_at: string | null;
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

  sendMessage: async (id: string, text: string): Promise<ChatConversation> => {
    const response = await apiClient.post<ChatConversation>(
      `/api/v1/chat/conversations/${id}/messages`,
      { text },
      { timeout: TURN_TIMEOUT_MS },
    );
    return response.data;
  },

  // One bot reply's model call — the exact prompt, the raw reply, the
  // model, timing and tokens — in the same shape as a run's AI call.
  getTranscript: async (id: string, seq: number): Promise<TieredTranscriptCall> => {
    const response = await apiClient.get<TieredTranscriptCall>(
      `/api/v1/chat/conversations/${id}/messages/${seq}/transcript`,
    );
    return response.data;
  },

  confirm: async (id: string, approved: boolean): Promise<ChatConversation> => {
    const response = await apiClient.post<ChatConversation>(
      `/api/v1/chat/conversations/${id}/confirm`,
      { approved },
      { timeout: TURN_TIMEOUT_MS },
    );
    return response.data;
  },
};
