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
    usage: { input_tokens: 3238, output_tokens: 78 }, llm: 'fake', time_ms: 812, transcript_chars: 9000,
  },
  {
    seq: 3, role: 'tool', created_at: null, tool_call_id: 'c1', name: 'list_runs',
    output: { items: [{ run_id: 'x' }], total: 1 }, output_chars: 1420, truncated: false, time_ms: 12,
    // What the tool ran with: the model's arguments plus every default.
    input: { ticker: ['AAPL'], status: [], page: 1, page_size: 10 },
  },
  {
    seq: 4, role: 'assistant', created_at: null, text: 'You have **1** run.',
    usage: { input_tokens: 5000, output_tokens: 40 }, llm: 'fake', time_ms: 812, transcript_chars: 12000,
  },
];

describe('ChatThread', () => {
  it('shows the user line, the trace and the reply with its token usage', async () => {
    renderThread({ messages: MESSAGES });
    expect(screen.getByTestId('chat-user')).toHaveTextContent('what did I run?');
    const trace = screen.getByTestId('chat-tool');
    // Each bot step opens with its step line, counted from the user's
    // last line (owner request 2026-09-24).
    const steps = screen.getAllByTestId(/^chat-(assistant|tool)$/);
    expect(steps.map((step) => step.firstElementChild?.textContent)).toEqual([
      expect.stringMatching(/^(Step 1: LLM decided to call a tool|第 1 步：LLM 决定调用工具)$/),
      expect.stringMatching(/^(Step 2: tool call|第 2 步：工具调用)$/),
      expect.stringMatching(/^(Step 3: LLM decided to say something|第 3 步：LLM 决定作答)$/),
    ]);
    // The step line is the heading: a size up and brighter than the
    // reply text, with everything else indented under it (owner
    // request 2026-09-24).
    for (const step of steps) {
      expect(step.firstElementChild).toHaveClass('text-base', 'font-semibold', 'text-gray-100');
      expect(step.children).toHaveLength(2);
      expect(step.lastElementChild).toHaveClass('pl-4');
    }
    expect(trace).toHaveTextContent(/(name|名称): list_runs/);
    // No time fact on a tool card (owner request 2026-09-24).
    expect(trace).not.toHaveTextContent(/(time|耗时):/);
    // Sizes sit on the input and output lines themselves — no separate
    // output-size fact (owner request 2026-09-24).
    expect(trace).not.toHaveTextContent(/(output size|输出大小):/);
    expect(screen.getByTestId('chat-tool-output')).toHaveTextContent(/^(output|输出): 1\.4 KB/);
    expect(screen.getByTestId('chat-tool-input')).toHaveTextContent(/^(input|输入): \d+ B/);
    // A finished call that answered without an error is done, in the
    // run history's green; a call that needed no permission has no
    // decision line (owner request 2026-09-24).
    const status = within(trace).getByTestId('chat-tool-status');
    expect(status).toHaveTextContent(/^(status: done|状态: 已完成)$/);
    expect(status.lastElementChild).toHaveClass('text-emerald-300');
    expect(within(trace).queryByTestId('chat-tool-decision')).toBeNull();
    // The status line sits between the name and the input.
    expect(status.compareDocumentPosition(screen.getByTestId('chat-tool-input')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // The reply renders (Markdown arrives lazily; the raw text stands in first).
    expect(await screen.findByText(/1.*run\./)).toBeInTheDocument();
    // "This step used N tokens": in and out together, plain digits, in
    // the run page's usage-line size and color. Every step has one —
    // the tool step in the middle says 0.
    const usages = screen.getAllByTestId('chat-usage');
    expect(usages.map((line) => line.textContent)).toEqual([
      expect.stringMatching(/^(This step used 3316 tokens|本步骤使用了 3316 tokens)$/),
      expect.stringMatching(/^(This step used 0 tokens|本步骤使用了 0 tokens)$/),
      expect.stringMatching(/^(This step used 5040 tokens|本步骤使用了 5040 tokens)$/),
    ]);
    expect(usages[0]).toHaveClass('text-gray-600');
    expect(usages[0].closest('.text-xs')).not.toBeNull();
    // Bot steps are bare text: no backdrop, no card padding (owner
    // request 2026-09-24); the user's line keeps the level-1 surface.
    const replies = screen.getAllByTestId('chat-assistant');
    expect(replies).toHaveLength(2);
    for (const step of [...replies, trace]) {
      expect(step.className).not.toMatch(/bg-gray-|p-5/);
    }
    expect(screen.getByTestId('chat-user').firstElementChild).toHaveClass('bg-gray-900');
    expect(replies[0]).toContainElement(usages[0]);
    expect(trace).toContainElement(usages[1]);
    expect(replies[1]).toContainElement(usages[2]);
  });

  it('caps the user at 85% on the right, runs bot steps full width, and lets a long word break', () => {
    const longWord = 'testing'.repeat(40);
    const pending: ChatPendingCall = { call_id: 'c9', name: 'list_tickers', input: {}, facts: {} };
    renderThread({ messages: [...MESSAGES, { seq: 5, role: 'user', created_at: null, text: longWord }], pending });
    // The user's line sits against the right edge; a bot step starts at
    // the left and keeps no right margin (owner request 2026-09-24).
    const userLines = screen.getAllByTestId('chat-user');
    expect(userLines[0]).toHaveClass('justify-end');
    expect(userLines[0].firstElementChild).toHaveClass('max-w-[85%]', 'min-w-0');
    // A held call is a bot step too, so it runs full width like the rest.
    for (const step of [
      ...screen.getAllByTestId('chat-assistant'),
      screen.getByTestId('chat-tool'),
      screen.getByTestId('chat-pending'),
    ]) {
      expect(step.className).not.toMatch(/max-w-|justify-end|ml-auto|mr-|pr-/);
    }
    // A long unbroken word may break anywhere, so nothing widens the thread.
    const thread = screen.getByTestId('chat-thread');
    expect(thread).toHaveClass('min-w-0', '[overflow-wrap:anywhere]');
    expect(thread).toContainElement(screen.getByText(longWord));
  });

  it('names no tools on a text-less reply, draws no rules, and gives a tool step a plain zero-token line', () => {
    renderThread({ messages: MESSAGES });
    // The tool step right after names the tool; the reply does not
    // (owner request 2026-09-24).
    expect(screen.queryByTestId('chat-tool-choice')).toBeNull();
    expect(screen.getAllByTestId('chat-assistant')[0]).not.toHaveTextContent(/chose to call|选择调用/);
    expect(screen.queryAllByTestId('chat-step-end')).toHaveLength(0);
    expect(document.querySelector('hr')).toBeNull();
    // The token line of the first reply comes before the tool row it led
    // to; the tool step's own line is last on its card and is not a button.
    const [replyUsage, toolUsage] = screen.getAllByTestId('chat-usage');
    const trace = screen.getByTestId('chat-tool');
    expect(replyUsage.compareDocumentPosition(trace) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(trace).toContainElement(toolUsage);
    expect(trace.lastElementChild).toContainElement(toolUsage);
    expect(toolUsage.tagName).toBe('P');
    expect(replyUsage.tagName).toBe('BUTTON');
    expect(toolUsage).toHaveClass('text-gray-600');
    expect(toolUsage.closest('.text-xs')).not.toBeNull();
  });

  it('opens the model call transcript from its token line', async () => {
    const transcriptLoader = vi.fn().mockResolvedValue({
      seq: 4, created_at: null, stage: 'chat', llm: 'fake', temperature: 0, time_ms: 812,
      input_tokens: 5000, output_tokens: 40, structured: null, error: null,
      input: '=== system ===\nYou are the bot.', output: 'You have **1** run.',
    });
    renderThread({ messages: MESSAGES, transcriptLoader });
    const replyUsage = screen.getAllByTestId('chat-usage').at(-1)!;
    fireEvent.click(replyUsage);
    const card = screen.getByTestId('chat-transcript');
    // Inside the reply's own card, not a second card on top of it.
    expect(screen.getAllByTestId('chat-assistant').at(-1)).toContainElement(card);
    expect(card).not.toHaveClass('bg-gray-800', 'bg-gray-900');
    // The transcript is indented under its token line, and an opened
    // reply is indented once more under its own line, on level 1 (the
    // step under it is bare).
    expect(card).toHaveClass('pl-4');
    fireEvent.click(screen.getByTestId('transcript-output'));
    expect(screen.getByTestId('transcript-output').nextElementSibling).toHaveClass('bg-gray-900', 'ml-4');
    fireEvent.click(screen.getByTestId('transcript-output'));
    // No "LLM call" title and no "for: chat" fact: in the chat they never
    // vary (owner request 2026-09-24). The facts that do vary stay.
    expect(card).not.toHaveTextContent(/LLM call|LLM 调用|for:|用于:/);
    expect(card).toHaveTextContent(/llm: fake/);
    expect(card).toHaveTextContent('812ms');
    expect(card).not.toHaveTextContent(/tokens: 5040/);
    expect(screen.getByTestId('transcript-input')).toHaveTextContent(/^(input|输入): 5000 tokens/);
    expect(screen.getByTestId('transcript-output')).toHaveTextContent(/^(output|输出): 40 tokens/);
    fireEvent.click(screen.getByTestId('transcript-input'));
    expect(transcriptLoader).toHaveBeenCalledWith('conv1', 4);
    expect(await screen.findByText(/You are the bot\./)).toBeInTheDocument();
    fireEvent.click(replyUsage);
    expect(screen.queryByTestId('chat-transcript')).toBeNull();
  });

  it('opens a reply whose transcript was never kept, and says so in its folds', () => {
    const transcriptLoader = vi.fn();
    renderThread({
      messages: [
        { seq: 1, role: 'user', created_at: null, text: 'hi' },
        { seq: 2, role: 'assistant', created_at: null, text: 'hello', usage: { input_tokens: 700, output_tokens: 38 }, llm: 'fake', time_ms: 5, transcript_chars: null },
      ],
      transcriptLoader,
    });
    const usage = screen.getByTestId('chat-usage');
    expect(usage.tagName).toBe('BUTTON');
    expect(usage).toHaveTextContent('738');
    fireEvent.click(usage);
    expect(screen.getByTestId('chat-transcript')).toBeInTheDocument();
    expect(screen.getByTestId('transcript-input')).toHaveTextContent(/^(input|输入): 700 tokens/);
    fireEvent.click(screen.getByTestId('transcript-input'));
    expect(transcriptLoader).not.toHaveBeenCalled();
    // Both folds carry the note; the loader is never asked.
    expect(screen.getAllByText(/transcript was not kept|没有保存对话记录/)).toHaveLength(2);
  });

  it('keeps the tool line in view and folds its input and output', () => {
    renderThread({ messages: MESSAGES });
    const trace = within(screen.getByTestId('chat-tool'));
    expect(trace.getByText(/list_runs/)).toBeVisible();
    fireEvent.click(trace.getByTestId('chat-tool-input'));
    // The inputs the tool ran with — defaults included — not only what
    // the model sent (owner request 2026-09-24).
    expect(screen.getByText(/"ticker"/)).toBeInTheDocument();
    expect(screen.getByText(/"page_size": 10/)).toBeInTheDocument();
    fireEvent.click(trace.getByTestId('chat-tool-output'));
    const output = screen.getByText(/"total": 1/);
    expect(output).toBeInTheDocument();
    // The opened text is on level 1, indented under its line; the step under it is bare.
    expect(output.parentElement).toHaveClass('bg-gray-900', 'ml-4');
    // Shown whole: no capped, scrolling box around the text.
    expect(output.className).not.toMatch(/max-h-|overflow-y/);
  });

  it('flags a tool error and a refused action', () => {
    renderThread({
      messages: [
        { seq: 1, role: 'user', created_at: null, text: 'delete ghost' },
        { seq: 2, role: 'assistant', created_at: null, text: null, tool_calls: [{ id: 'c1', name: 'delete_run', arguments: { run_id: 'ghost' } }] },
        { seq: 3, role: 'tool', created_at: null, tool_call_id: 'c1', name: 'delete_run', output: { error: 'not_found' }, output_chars: 30, approved: false },
      ],
    });
    const trace = screen.getByTestId('chat-tool');
    expect(trace).toHaveTextContent(/not_found/);
    // The refusal is in the step line, in view without opening anything
    // — no separate Approved/Declined line (owner request 2026-09-24).
    expect(screen.getByText(/^(Step 2: tool call|第 2 步：工具调用)$/)).toBeVisible();
    const decision = within(trace).getByTestId('chat-tool-decision');
    expect(decision).toHaveTextContent(/^(decision: declined|决定: 已拒绝)$/);
    expect(decision.lastElementChild).toHaveClass('text-red-300');
    // An answer with an error code is a failed step, in the run history's
    // red, right under the decision (owner request 2026-09-24).
    const status = within(trace).getByTestId('chat-tool-status');
    expect(status).toHaveTextContent(/^(status: failed|状态: 失败)$/);
    expect(status.lastElementChild).toHaveClass('text-red-300');
    expect(decision.nextElementSibling).toBe(status);
    // No error line of its own (owner request 2026-09-25): the code is
    // in the output fold.
    expect(trace).not.toHaveTextContent(/answered with an error|返回错误/);
    fireEvent.click(within(trace).getByTestId('chat-tool-output'));
    expect(screen.getByText(/"error": "not_found"/)).toBeInTheDocument();
  });

  it('shows a failed model call and the step-cap notice', () => {
    renderThread({
      messages: [
        { seq: 1, role: 'assistant', created_at: null, text: 'The model call failed: quota', error: 'quota' },
        { seq: 2, role: 'assistant', created_at: null, text: 'stopped', notice: 'tool_call_limit' },
        { seq: 3, role: 'assistant', created_at: null, text: 'Hello in the wrong tongue', notice: 'wrong_language' },
      ],
    });
    expect(screen.getByText('The model call failed: quota')).toHaveClass('text-red-300');
    expect(screen.getByText(/tool-call limit|工具调用上限/)).toBeInTheDocument();
    expect(screen.getByText(/not in the chosen language|不是所选的语言/)).toBeInTheDocument();
  });

  it('shows a held call as the next tool step with a decision line, and reports the answer', () => {
    const pending: ChatPendingCall = {
      call_id: 'c1', name: 'delete_run', input: { run_id: 'q' },
      facts: { run: { ticker: 'MSFT', status: 'queued' } },
    };
    const props = renderThread({ messages: MESSAGES.slice(0, 2), pending });
    const held = screen.getByTestId('chat-pending');
    // Numbered after the reply that asked for it; the name and inputs
    // show as on any tool step, and "decision" sits above the input.
    expect(held.firstElementChild).toHaveTextContent(/^(Step 2: tool call|第 2 步：工具调用)$/);
    expect(held).toHaveTextContent(/(name|名称): delete_run/);
    const decision = within(held).getByTestId('chat-tool-decision');
    expect(decision).toHaveTextContent(/^(decision: approve\s*\|\s*decline|决定: 同意\s*\|\s*拒绝)$/);
    expect(decision.compareDocumentPosition(within(held).getByTestId('chat-tool-input')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // Held: status waiting, in the run history's queued amber, right
    // under the decision (owner request 2026-09-24).
    const status = within(held).getByTestId('chat-tool-status');
    expect(status).toHaveTextContent(/^(status: waiting|状态: 等待中)$/);
    expect(status.lastElementChild).toHaveClass('text-amber-300');
    expect(decision.nextElementSibling).toBe(status);
    fireEvent.click(within(held).getByTestId('chat-tool-input'));
    expect(screen.getByText(/"run_id": "q"/)).toBeInTheDocument();
    // Nothing has come back yet: no output fold, no token line.
    expect(within(held).queryByTestId('chat-tool-output')).toBeNull();
    expect(within(held).queryByTestId('chat-usage')).toBeNull();
    // No question card, no facts wording.
    expect(held).not.toHaveTextContent(/MSFT|\?/);
    fireEvent.click(screen.getByTestId('chat-pending-no'));
    expect(props.onConfirm).toHaveBeenCalledWith(false);
    fireEvent.click(screen.getByTestId('chat-pending-yes'));
    expect(props.onConfirm).toHaveBeenCalledWith(true);
  });

  it('is its own scroll box and scrolls to its bottom when the conversation grows or changes', () => {
    const props: ChatThreadProps = {
      conversationId: 'conv1', messages: MESSAGES.slice(0, 1), pending: null, working: false,
      onConfirm: vi.fn(), transcriptLoader: vi.fn(), className: 'h-full overflow-y-auto',
    };
    const view = (overrides: Partial<ChatThreadProps>) => (
      <UiLanguageProvider>
        <ChatThread {...props} {...overrides} />
      </UiLanguageProvider>
    );
    const { rerender } = render(view({}));
    const thread = screen.getByTestId('chat-thread');
    expect(thread).toHaveClass('overflow-y-auto');
    // The test DOM has no layout: give the box a height to scroll through.
    let scrolledTo = 0;
    Object.defineProperty(thread, 'scrollHeight', { value: 500, configurable: true });
    Object.defineProperty(thread, 'scrollTop', {
      get: () => scrolledTo, set: (value: number) => { scrolledTo = value; }, configurable: true,
    });
    rerender(view({ messages: MESSAGES }));
    expect(scrolledTo).toBe(500);
    scrolledTo = 0;
    rerender(view({ messages: MESSAGES, conversationId: 'conv2' }));
    expect(scrolledTo).toBe(500);
  });

  it('shows the answer as approved and the status as processing while the server works, then falls back if it failed', () => {
    const pending: ChatPendingCall = { call_id: 'c1', name: 'list_tickers', input: {}, facts: {} };
    const props: ChatThreadProps = {
      conversationId: 'conv1', messages: MESSAGES.slice(0, 2), pending, working: false,
      onConfirm: vi.fn(), transcriptLoader: vi.fn(),
    };
    const view = (overrides: Partial<ChatThreadProps>) => (
      <UiLanguageProvider>
        <ChatThread {...props} {...overrides} />
      </UiLanguageProvider>
    );
    const { rerender } = render(view({}));
    fireEvent.click(screen.getByTestId('chat-pending-yes'));
    expect(props.onConfirm).toHaveBeenCalledWith(true);
    // The page turns `working` on for the request: the decision keeps
    // the answer given, the status turns processing in the run
    // history's running blue, and no dots show — the step is the
    // progress (owner request 2026-09-24).
    rerender(view({ working: true }));
    const decision = screen.getByTestId('chat-tool-decision');
    expect(decision).toHaveTextContent(/^(decision: approved|决定: 已同意)$/);
    expect(decision.lastElementChild).toHaveClass('text-emerald-300');
    const status = screen.getByTestId('chat-tool-status');
    expect(status).toHaveTextContent(/^(status: processing|状态: 处理中)$/);
    expect(status.lastElementChild).toHaveClass('text-sky-300');
    expect(screen.queryByTestId('chat-pending-yes')).toBeNull();
    expect(screen.queryByTestId('chat-working')).toBeNull();
    // The request failed and the call is still held: the question is
    // asked again and the status is waiting once more.
    rerender(view({ working: false }));
    expect(decision).toHaveTextContent(/^(decision: approve\s*\|\s*decline|决定: 同意\s*\|\s*拒绝)$/);
    expect(status).toHaveTextContent(/^(status: waiting|状态: 等待中)$/);
    expect(status.lastElementChild).toHaveClass('text-amber-300');
  });

  it('never says processing on the decision line, disables the answers while working, and shows the pulsing dots otherwise', () => {
    const pending: ChatPendingCall = { call_id: 'c1', name: 'list_tickers', input: {}, facts: {} };
    renderThread({ messages: [], pending, working: true });
    // The decision is only ever the question or the answer (owner
    // request 2026-09-24); the progress is on the status line.
    expect(screen.getByTestId('chat-tool-decision')).toHaveTextContent(/^(decision: approve\s*\|\s*decline|决定: 同意\s*\|\s*拒绝)$/);
    expect(screen.getByTestId('chat-tool-decision')).not.toHaveTextContent(/processing|处理中/);
    expect(screen.getByTestId('chat-tool-status')).toHaveTextContent(/^(status: processing|状态: 处理中)$/);
    expect(screen.getByTestId('chat-pending-yes')).toBeDisabled();
    expect(screen.getByTestId('chat-pending-no')).toBeDisabled();
    expect(screen.queryByTestId('chat-working')).toBeNull();
    cleanup();
    renderThread({ messages: MESSAGES.slice(0, 1), working: true });
    expect(screen.getByTestId('chat-working')).toBeInTheDocument();
  });
});
