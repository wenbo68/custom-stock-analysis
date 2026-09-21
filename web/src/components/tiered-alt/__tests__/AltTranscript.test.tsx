import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TieredTranscriptCall, TieredTranscriptCallSummary } from '../../../api/tiered';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { AltTranscript } from '../AltTranscript';

const facts = {
  seq: 1,
  created_at: '2026-09-14T10:00:00',
  stage: 'tier1_analysis',
  model: 'gemini/flash',
  temperature: 0,
  duration_ms: 120,
  prompt_tokens: 10,
  completion_tokens: 5,
  structured: 'schema',
  error: null,
};

const summary = (
  overrides: Partial<TieredTranscriptCallSummary> = {},
): TieredTranscriptCallSummary => ({
  ...facts,
  prompt_chars: 10,
  reply_chars: 18,
  ...overrides,
});

const call = (overrides: Partial<TieredTranscriptCall> = {}): TieredTranscriptCall => ({
  ...facts,
  prompt: 'the prompt',
  reply: '{"outlook": "buy"}',
  ...overrides,
});

type Loader = (taskId: string) => Promise<TieredTranscriptCallSummary[]>;
type CallLoader = (taskId: string, seq: number) => Promise<TieredTranscriptCall>;

function renderTranscript(
  loader: Loader,
  callLoader: CallLoader = vi.fn().mockResolvedValue(call()),
) {
  render(
    <UiLanguageProvider>
      <AltTranscript
        taskId="task-1"
        label="This run used 2 LLM calls (30 tokens)"
        loader={loader}
        callLoader={callLoader}
      />
    </UiLanguageProvider>,
  );
}

// A fact line is one span whose full text is "label: value"; the value
// sits in a nested span, so plain getByText cannot see the pair together.
const factLines = (pattern: RegExp) =>
  screen.getAllByTestId('alt-transcript-facts').flatMap((row) =>
    Array.from(row.children).filter((fact) => pattern.test(fact.textContent ?? '')),
  );

const folds = () => Array.from(document.querySelectorAll('details'));
const summaries = () => Array.from(document.querySelectorAll('summary'));

describe('AltTranscript', () => {
  it('loads nothing until opened, then shows every call from the index', async () => {
    const loader = vi.fn().mockResolvedValue([
      summary(),
      summary({ seq: 2, stage: 'trade_plan', reply_chars: 0, error: "RuntimeError('boom')" }),
    ]);
    const callLoader = vi.fn();
    renderTranscript(loader, callLoader);
    expect(loader).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /2 LLM calls/ }));

    await waitFor(() => expect(screen.getByText(/tier1 analysis/)).toBeInTheDocument());
    expect(loader).toHaveBeenCalledWith('task-1');
    // The index has no text, and none is fetched until a fold opens.
    expect(callLoader).not.toHaveBeenCalled();
    expect(screen.queryByText('the prompt')).not.toBeInTheDocument();
    expect(screen.getByText(/boom/)).toBeInTheDocument();
    // The call number, then one row of label/value facts: the label
    // stays muted, the value is bright and bold.
    expect(screen.getByText(/^(Call 1|第 1 次调用)$/)).toBeInTheDocument();
    expect(screen.getAllByTestId('alt-transcript-facts')).toHaveLength(2);
    expect(factLines(/^tokens: 15$/)).toHaveLength(2);
    expect(factLines(/^(for|用于): trade plan$/)).toHaveLength(1);
    expect(factLines(/^(time|耗时): 120ms$/)).toHaveLength(2);
    expect(screen.getByText('trade plan')).toHaveClass('font-semibold', 'text-gray-200');
    // Both prompt and reply folded by default, on the same fold surface
    // as the deep-analysis card's details.
    expect(folds()).toHaveLength(4);
    expect(folds().every((fold) => !fold.open)).toBe(true);
    expect(folds().every((fold) => fold.classList.contains('bg-gray-900/60'))).toBe(true);
    // Shown whole when opened: no inner scroll box.
    expect(document.querySelector('pre.max-h-64')).toBeNull();
    // On the card surface, not the history backdrop.
    expect(screen.getByTestId('alt-transcript')).toHaveClass('bg-gray-800');
  });

  it('fetches a call’s text once, the first time either of its folds opens', async () => {
    const loader = vi.fn().mockResolvedValue([summary(), summary({ seq: 2 })]);
    const callLoader = vi
      .fn()
      .mockImplementation((_task: string, seq: number) =>
        Promise.resolve(call({ seq, prompt: `prompt ${seq}`, reply: `reply ${seq}` })),
      );
    renderTranscript(loader, callLoader);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(folds()).toHaveLength(4));

    // Open call 2's reply: only call 2 is fetched, and its prompt fold
    // is filled by the same fetch.
    fireEvent.click(summaries()[3]);
    await waitFor(() => expect(screen.getByText('reply 2')).toBeInTheDocument());
    expect(callLoader).toHaveBeenCalledTimes(1);
    expect(callLoader).toHaveBeenCalledWith('task-1', 2);
    fireEvent.click(summaries()[2]);
    expect(screen.getByText('prompt 2')).toBeInTheDocument();
    expect(callLoader).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('prompt 1')).not.toBeInTheDocument();

    // Closing and reopening does not fetch again.
    fireEvent.click(summaries()[3]);
    fireEvent.click(summaries()[3]);
    expect(callLoader).toHaveBeenCalledTimes(1);
  });

  it('shows a loading note, then the no-reply note for a call that got none', async () => {
    const loader = vi.fn().mockResolvedValue([summary({ reply_chars: 0 })]);
    let finish: (value: TieredTranscriptCall) => void = () => undefined;
    const callLoader = vi.fn().mockReturnValue(
      new Promise<TieredTranscriptCall>((resolve) => {
        finish = resolve;
      }),
    );
    renderTranscript(loader, callLoader);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(folds()).toHaveLength(2));

    fireEvent.click(summaries()[1]);
    expect(screen.getAllByText(/Loading…|加载中…/).length).toBeGreaterThan(0);
    finish(call({ reply: null }));
    await waitFor(() => expect(screen.getByText(/\(no reply\)|（无回复）/)).toBeInTheDocument());
  });

  it('reports a failed call fetch inside the fold instead of hiding it', async () => {
    const loader = vi.fn().mockResolvedValue([summary()]);
    const callLoader = vi.fn().mockRejectedValue(new Error('network down'));
    renderTranscript(loader, callLoader);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(folds()).toHaveLength(2));
    fireEvent.click(summaries()[0]);
    await waitFor(() => expect(screen.getAllByText(/network down/).length).toBeGreaterThan(0));
  });

  it('reports an index load failure instead of hiding it', async () => {
    const loader = vi.fn().mockRejectedValue(new Error('network down'));
    renderTranscript(loader);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(screen.getByText(/network down/)).toBeInTheDocument());
  });

  it('says so when the stored rows have expired', async () => {
    const loader = vi.fn().mockResolvedValue([]);
    renderTranscript(loader);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() =>
      expect(screen.getByText(/已过期|expired/)).toBeInTheDocument(),
    );
  });

  it('fetches the index once and only toggles afterwards', async () => {
    const loader = vi.fn().mockResolvedValue([summary()]);
    renderTranscript(loader);
    const button = screen.getByRole('button');
    fireEvent.click(button);
    await waitFor(() => expect(screen.getByText(/tier1 analysis/)).toBeInTheDocument());
    fireEvent.click(button);
    expect(screen.queryByText(/tier1 analysis/)).not.toBeInTheDocument();
    fireEvent.click(button);
    expect(screen.getByText(/tier1 analysis/)).toBeInTheDocument();
    expect(loader).toHaveBeenCalledTimes(1);
  });
});
