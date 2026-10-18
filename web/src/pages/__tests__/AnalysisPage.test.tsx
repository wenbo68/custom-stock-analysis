import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TieredRunSummary } from '../../api/tiered';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';

vi.mock('../../api/tiered', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/tiered')>();
  return {
    ...actual,
    tieredApi: {
      ...actual.tieredApi,
      start: vi.fn(),
      listRuns: vi.fn(),
      listTickers: vi.fn(),
      getRun: vi.fn(),
      deleteRun: vi.fn(),
      stopRun: vi.fn(),
    },
  };
});

const { tieredApi } = await import('../../api/tiered');
const { default: AnalysisPage } = await import('../AnalysisPage');

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  vi.mocked(tieredApi.listRuns).mockResolvedValue({
    items: [], page: 1, page_size: 10, total: 0, page_count: 1,
  });
  vi.mocked(tieredApi.listTickers).mockResolvedValue([]);
  vi.mocked(tieredApi.start).mockResolvedValue({
    run_id: 'r1', ticker: 'AAPL', tier: 1, status: 'queued',
  });
});

// Every run carries the language the user chose for the app (2026-09-26):
// the report's model-written sentences are in it. The choice is read
// from storage here, the same way the page reads it at start-up.
async function startRun(language: 'zh' | 'en') {
  window.localStorage.setItem('uiLanguage', language);
  render(
    <UiLanguageProvider>
      <AnalysisPage />
    </UiLanguageProvider>,
  );
  // The form's ticker field comes first; the history filter has one too.
  const [input] = screen.getAllByLabelText(/代码|Ticker/);
  fireEvent.change(input, { target: { value: 'AAPL' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  fireEvent.click(screen.getByRole('button', { name: /开始|Start/ }));
  await waitFor(() => expect(tieredApi.start).toHaveBeenCalledTimes(1));
  return vi.mocked(tieredApi.start).mock.calls[0][0];
}

describe('AnalysisPage — the run request', () => {
  it('starts a run in Chinese when the app is in Chinese', async () => {
    const request = await startRun('zh');
    expect(request).toMatchObject({ ticker: 'AAPL', tier: 1, language: 'zh' });
  });

  it('starts a run in English when the app is in English', async () => {
    const request = await startRun('en');
    expect(request).toMatchObject({ ticker: 'AAPL', tier: 1, language: 'en' });
  });
});


// Stop button (2026-10-19): the page asks the server to stop a running
// run, keeps the row marked as stopping until the server says it is
// stopped, then fetches the report of what finished.
describe('AnalysisPage — stopping a run', () => {
  const runningRow: TieredRunSummary = {
    run_id: 'r1', ticker: 'AAPL', status: 'running', error: null,
    created_at: '2026-10-19T04:00:00', updated_at: null, tier: 1,
    capital: 100000, risk_pct: 1, reward_ratio: 2, max_hold_weeks: 2,
    outlook: null, shares: null,
  };
  const page = (items: TieredRunSummary[]) => ({
    items, page: 1, page_size: 10, total: items.length, page_count: 1,
  });

  it('asks the server to stop, shows stopping until the row flips, then loads the partial report', async () => {
    // Real time still passes (waitFor polls), but the page's 5-second
    // list poll is driven by hand below.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    window.localStorage.setItem('uiLanguage', 'en');
    vi.mocked(tieredApi.listRuns).mockResolvedValue(page([runningRow]));
    vi.mocked(tieredApi.stopRun).mockResolvedValue({ run_id: 'r1', ticker: 'AAPL' });
    render(
      <UiLanguageProvider>
        <AnalysisPage />
      </UiLanguageProvider>,
    );
    const stop = await screen.findByTestId('run-stop');
    fireEvent.click(stop);
    fireEvent.click(screen.getByTestId('run-stop-confirm'));
    await waitFor(() => expect(tieredApi.stopRun).toHaveBeenCalledWith('r1'));
    // The server still says running: the row is marked as stopping.
    await waitFor(() => expect(screen.getByTestId('run-stop')).toBeDisabled());
    expect(screen.getByTestId('run-stop').getAttribute('aria-label')).toMatch(/Stopping…/);

    // The next poll says stopped: the row shows the trash, and opening
    // it fetches the report of what finished.
    const stoppedRow: TieredRunSummary = { ...runningRow, status: 'stopped' };
    vi.mocked(tieredApi.listRuns).mockResolvedValue(page([stoppedRow]));
    vi.mocked(tieredApi.getRun).mockResolvedValue({
      ...stoppedRow,
      sections: ['core', 'data_reports', 'deep_analysis', 'plan'],
      result: {
        ticker: 'AAPL', market: 'us', tier: 1, stopped_stage: 'positioning',
        score: null, confidence: null, levels: { entry: null, stop_loss: null, target: null },
        summary: null, warnings: [], data_reports: [],
      },
    });
    fireEvent.click(screen.getByRole('button', { name: /AAPL/ }));
    try {
      vi.advanceTimersByTime(5000);
      await waitFor(() => expect(screen.getByTestId('run-delete')).toBeInTheDocument());
      await waitFor(() => expect(tieredApi.getRun).toHaveBeenCalledWith('r1'));
      expect(await screen.findByTestId('stopped-banner')).toHaveTextContent(/Positioning did not finish/);
    } finally {
      vi.useRealTimers();
    }
  });

  it('words a refusal under the row when the run is no longer running', async () => {
    window.localStorage.setItem('uiLanguage', 'en');
    vi.mocked(tieredApi.listRuns).mockResolvedValue(page([runningRow]));
    const axios = (await import('axios')).default;
    vi.mocked(tieredApi.stopRun).mockRejectedValue(
      new axios.AxiosError('conflict', '409', undefined, undefined, {
        status: 409, statusText: 'Conflict', headers: {}, config: {} as never,
        data: { detail: { code: 'run_not_running', run_id: 'r1', status: 'succeeded' } },
      }),
    );
    render(
      <UiLanguageProvider>
        <AnalysisPage />
      </UiLanguageProvider>,
    );
    fireEvent.click(await screen.findByTestId('run-stop'));
    fireEvent.click(screen.getByTestId('run-stop-confirm'));
    expect(await screen.findByTestId('run-stop-error')).toHaveTextContent(/no longer running/);
    // Nothing is marked as stopping after a refusal.
    expect(screen.getByTestId('run-stop')).not.toBeDisabled();
  });
});
