import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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
