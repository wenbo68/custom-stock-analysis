import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TieredTranscriptCall, TieredTranscriptCallSummary } from '../../../api/tiered';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { Transcript } from '../Transcript';

const facts = {
  call_number: 1,
  created_at: '2026-09-14T10:00:00',
  stage: 'preliminary_analysis',
  llm: 'gemini/flash',
  temperature: 0,
  time_ms: 120,
  input_tokens: 10,
  output_tokens: 5,
  structured: 'schema',
  error: null,
};

const summary = (
  overrides: Partial<TieredTranscriptCallSummary> = {},
): TieredTranscriptCallSummary => ({
  ...facts,
  input_chars: 10,
  output_chars: 18,
  ...overrides,
});

const call = (overrides: Partial<TieredTranscriptCall> = {}): TieredTranscriptCall => ({
  ...facts,
  input: 'the prompt',
  output: '{"outlook": "buy"}',
  ...overrides,
});

type Loader = (runId: string) => Promise<TieredTranscriptCallSummary[]>;
type CallLoader = (runId: string, seq: number) => Promise<TieredTranscriptCall>;

function renderTranscript(
  loader: Loader,
  callLoader: CallLoader = vi.fn().mockResolvedValue(call()),
) {
  render(
    <UiLanguageProvider>
      <Transcript
        runId="task-1"
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
  screen.getAllByTestId('transcript-facts').flatMap((row) =>
    Array.from(row.children).filter((fact) => pattern.test(fact.textContent ?? '')),
  );

const folds = () => Array.from(document.querySelectorAll('details'));
const summaries = () => Array.from(document.querySelectorAll('summary'));

describe('Transcript', () => {
  it('loads nothing until opened, then shows every call from the index', async () => {
    const loader = vi.fn().mockResolvedValue([
      summary(),
      summary({ call_number: 2, stage: 'trade_plan', output_chars: 0, error: "RuntimeError('boom')" }),
    ]);
    const callLoader = vi.fn();
    renderTranscript(loader, callLoader);
    expect(loader).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /2 LLM calls/ }));

    await waitFor(() => expect(screen.getByText(/Preliminary analysis|初步分析/)).toBeInTheDocument());
    expect(loader).toHaveBeenCalledWith('task-1');
    // The index has no text, and none is fetched until a fold opens.
    expect(callLoader).not.toHaveBeenCalled();
    expect(screen.queryByText('the prompt')).not.toBeInTheDocument();
    expect(screen.getByText(/boom/)).toBeInTheDocument();
    // The call number, then one row of label/value facts: the label
    // stays muted, the value is bright and bold.
    expect(screen.getByText(/^(LLM call 1|第 1 次 LLM 调用)$/)).toBeInTheDocument();
    expect(screen.getAllByTestId('transcript-facts')).toHaveLength(2);
    // No tokens fact: the prompt and reply lines carry their own counts
    // and open the text (owner request 2026-09-24).
    expect(factLines(/^tokens:/)).toHaveLength(0);
    expect(factLines(/^(input|输入): 10 tokens/)).toHaveLength(2);
    expect(factLines(/^(output|输出): 5 tokens/)).toHaveLength(2);
    // The "for" fact names the step in the page's language, not the
    // backend's identifier.
    expect(factLines(/^(for|用于): (Trade plan|交易计划)$/)).toHaveLength(1);
    expect(factLines(/^(time|耗时): 120ms$/)).toHaveLength(2);
    expect(screen.getByText(/^(Trade plan|交易计划)$/)).toHaveClass('font-semibold', 'text-ink-1');
    // Both prompt and reply folded by default. The clickable line is a
    // plain fact line — quiet label, bright value, a triangle after it,
    // no browser marker, no backdrop; only what it opens sits on the
    // fold surface.
    expect(folds()).toHaveLength(4);
    expect(folds().every((fold) => !fold.open)).toBe(true);
    expect(folds().every((fold) => !fold.classList.contains('bg-surface-1/60'))).toBe(true);
    expect(folds().every((fold) => fold.querySelector('.bg-surface-1\\/60') !== null)).toBe(true);
    expect(summaries().every((line) => line.classList.contains('list-none'))).toBe(true);
    expect(summaries().every((line) => line.classList.contains('text-ink-4'))).toBe(true);
    expect(summaries()[0]).toHaveTextContent(/▸$/);
    expect(screen.getAllByText('10 tokens')[0]).toHaveClass('font-semibold', 'text-ink-1');
    // Shown whole when opened: no inner scroll box.
    expect(document.querySelector('pre.max-h-64')).toBeNull();
    // On the card surface, not the history backdrop.
    expect(screen.getByTestId('transcript')).toHaveClass('bg-surface-2');
  });

  it('fetches a call’s text once, the first time either of its folds opens', async () => {
    const loader = vi.fn().mockResolvedValue([summary(), summary({ call_number: 2 })]);
    const callLoader = vi
      .fn()
      .mockImplementation((_task: string, callNumber: number) =>
        Promise.resolve(call({ call_number: callNumber, input: `prompt ${callNumber}`, output: `reply ${callNumber}` })),
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
    const loader = vi.fn().mockResolvedValue([summary({ output_chars: 0 })]);
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
    finish(call({ output: null }));
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
    await waitFor(() => expect(screen.getByText(/Preliminary analysis|初步分析/)).toBeInTheDocument());
    fireEvent.click(button);
    expect(screen.queryByText(/Preliminary analysis|初步分析/)).not.toBeInTheDocument();
    fireEvent.click(button);
    expect(screen.getByText(/Preliminary analysis|初步分析/)).toBeInTheDocument();
    expect(loader).toHaveBeenCalledTimes(1);
  });
});
