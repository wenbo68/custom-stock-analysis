import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ChatMessage, ChatPendingCall } from '../../../api/chat';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ChatThread, type ChatThreadProps } from '../ChatThread';

afterEach(cleanup);

const renderThread = (overrides: Partial<ChatThreadProps> = {}) => {
  const props: ChatThreadProps = {
    conversationId: 'conv1',
    messages: [],
    pending: null,
    working: false,
    onConfirm: vi.fn(),
    transcriptLoader: vi.fn(),
    ...overrides,
  };
  render(
    <UiLanguageProvider>
      <ChatThread {...props} />
    </UiLanguageProvider>,
  );
  return props;
};

const MESSAGES: ChatMessage[] = [
  { seq: 1, role: 'user', created_at: null, text: 'what did I run?' },
  {
    seq: 2, role: 'assistant', created_at: null, text: null,
    tool_calls: [{ id: 'c1', name: 'list_runs', arguments: { ticker: ['AAPL'], page: 1 } }],
    usage: { prompt_tokens: 3238, completion_tokens: 78 }, model: 'fake', duration_ms: 812, transcript_chars: 9000,
  },
  {
    seq: 3, role: 'tool', created_at: null, tool_call_id: 'c1', tool_name: 'list_runs',
    result: { items: [{ task_id: 'x' }], total: 1 }, result_chars: 1420, truncated: false, duration_ms: 12,
  },
  {
    seq: 4, role: 'assistant', created_at: null, text: 'You have **1** run.',
    usage: { prompt_tokens: 5000, completion_tokens: 40 }, model: 'fake', duration_ms: 812, transcript_chars: 12000,
  },
];

describe('ChatThread', () => {
  it('shows the user line, the trace and the reply with its token usage', async () => {
    renderThread({ messages: MESSAGES });
    expect(screen.getByTestId('chat-user')).toHaveTextContent('what did I run?');
    const trace = screen.getByTestId('chat-tool');
    expect(trace).toHaveTextContent(/Tool call|工具调用/);
    expect(trace).toHaveTextContent(/(name|名称): list_runs/);
    expect(trace).toHaveTextContent(/(time|耗时): 12ms/);
    expect(trace).toHaveTextContent(/(output size|输出大小): 1\.4 KB/);
    // The reply renders (Markdown arrives lazily; the raw text stands in first).
    expect(await screen.findByText(/1.*run\./)).toBeInTheDocument();
    // "This step used N tokens": in and out together, plain digits, in
    // the run page's usage-line size and color.
    const usages = screen.getAllByTestId('chat-usage');
    expect(usages[0]).toHaveTextContent(/^(This step used 3316 tokens|本步骤使用了 3316 tokens)$/);
    expect(usages[1]).toHaveTextContent(/^(This step used 5040 tokens|本步骤使用了 5040 tokens)$/);
    expect(usages[0]).toHaveClass('text-xs', 'text-gray-600');
  });

  it('names the tools a text-less reply chose, rules off every step but the last, and gives tool rows no token line', () => {
    renderThread({ messages: MESSAGES });
    expect(screen.getByTestId('chat-tool-choice')).toHaveTextContent('list_runs');
    // Three steps (model call, tool call, model call): a rule after the
    // first two, none after the last. The token line of the first comes
    // before the tool row it led to.
    const rules = screen.getAllByTestId('chat-step-end');
    expect(rules).toHaveLength(2);
    const thread = screen.getByTestId('chat-thread');
    const lastRow = screen.getAllByTestId('chat-assistant').at(-1)!;
    expect(lastRow.compareDocumentPosition(rules[1]) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    expect(thread.querySelector('[data-testid="chat-step-end"]:last-of-type')).not.toBe(thread.lastElementChild);
    const [toolRoundUsage] = screen.getAllByTestId('chat-usage');
    const trace = screen.getByTestId('chat-tool');
    expect(toolRoundUsage.compareDocumentPosition(trace) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(trace.querySelector('[data-testid="chat-usage"]')).toBeNull();
  });

  it('opens the model call transcript from its token line', async () => {
    const transcriptLoader = vi.fn().mockResolvedValue({
      seq: 4, created_at: null, stage: 'chat', model: 'fake', temperature: 0, duration_ms: 812,
      prompt_tokens: 5000, completion_tokens: 40, structured: null, error: null,
      prompt: '=== system ===\nYou are the bot.', reply: 'You have **1** run.',
    });
    renderThread({ messages: MESSAGES, transcriptLoader });
    const [, replyUsage] = screen.getAllByTestId('chat-usage');
    fireEvent.click(replyUsage);
    const card = screen.getByTestId('chat-transcript');
    expect(card).toHaveTextContent(/LLM call|LLM 调用/);
    expect(card).toHaveTextContent('812ms');
    expect(card).toHaveTextContent(/tokens: 5040 (total: 5000 in \+ 40 out|总计：5000 输入 \+ 40 输出)/);
    fireEvent.click(screen.getByText(/^Prompt$|^提示词$/));
    expect(transcriptLoader).toHaveBeenCalledWith('conv1', 4);
    expect(await screen.findByText(/You are the bot\./)).toBeInTheDocument();
    fireEvent.click(replyUsage);
    expect(screen.queryByTestId('chat-transcript')).toBeNull();
  });

  it('keeps the tool line in view and folds its input and output', () => {
    renderThread({ messages: MESSAGES });
    const trace = within(screen.getByTestId('chat-tool'));
    expect(trace.getByText(/list_runs/)).toBeVisible();
    fireEvent.click(trace.getByText(/^Input$|^输入$/));
    expect(screen.getByText(/"ticker"/)).toBeInTheDocument();
    fireEvent.click(trace.getByText(/^Output$|^输出$/));
    const output = screen.getByText(/"total": 1/);
    expect(output).toBeInTheDocument();
    // Shown whole: no capped, scrolling box around the text.
    expect(output.className).not.toMatch(/max-h-|overflow-y/);
  });

  it('flags a tool error and a refused action', () => {
    renderThread({
      messages: [
        { seq: 1, role: 'user', created_at: null, text: 'delete ghost' },
        { seq: 2, role: 'assistant', created_at: null, text: null, tool_calls: [{ id: 'c1', name: 'delete_run', arguments: { task_id: 'ghost' } }] },
        { seq: 3, role: 'tool', created_at: null, tool_call_id: 'c1', tool_name: 'delete_run', result: { error: 'not_found' }, result_chars: 30, approved: false },
      ],
    });
    const trace = screen.getByTestId('chat-tool');
    expect(trace).toHaveTextContent(/not_found/);
    // The refusal is in view without opening anything.
    expect(screen.getByText(/Declined|已拒绝/)).toBeVisible();
  });

  it('shows a failed model call and the step-cap notice', () => {
    renderThread({
      messages: [
        { seq: 1, role: 'assistant', created_at: null, text: 'The model call failed: quota', error: 'quota' },
        { seq: 2, role: 'assistant', created_at: null, text: 'stopped', notice: 'step_cap' },
      ],
    });
    expect(screen.getByText('The model call failed: quota')).toHaveClass('text-red-300');
    expect(screen.getByText(/tool-call limit|工具调用上限/)).toBeInTheDocument();
  });

  it('asks the held question and reports the answer', () => {
    const pending: ChatPendingCall = {
      call_id: 'c1', name: 'delete_run', arguments: { task_id: 'q' },
      facts: { run: { stock_code: 'MSFT', status: 'queued' } },
    };
    const props = renderThread({ messages: MESSAGES.slice(0, 1), pending });
    expect(screen.getByTestId('chat-pending')).toHaveTextContent(/MSFT/);
    fireEvent.click(screen.getByTestId('chat-pending-no'));
    expect(props.onConfirm).toHaveBeenCalledWith(false);
    fireEvent.click(screen.getByTestId('chat-pending-yes'));
    expect(props.onConfirm).toHaveBeenCalledWith(true);
  });

  it('disables the answers while working and shows the thinking line otherwise', () => {
    const pending: ChatPendingCall = { call_id: 'c1', name: 'list_tickers', arguments: {}, facts: {} };
    renderThread({ messages: [], pending, working: true });
    expect(screen.getByTestId('chat-pending-yes')).toBeDisabled();
    expect(screen.queryByTestId('chat-working')).toBeNull();
    cleanup();
    renderThread({ messages: MESSAGES.slice(0, 1), working: true });
    expect(screen.getByTestId('chat-working')).toBeInTheDocument();
  });
});
