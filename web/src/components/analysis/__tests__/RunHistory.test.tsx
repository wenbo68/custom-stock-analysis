import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TieredRunSummary } from '../../../api/tiered';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { RunHistory, type RunHistoryProps } from '../RunHistory';
import { NO_FILTERS } from '../historyFilters';

function makeRun(id: string, overrides: Partial<TieredRunSummary> = {}): TieredRunSummary {
  return {
    run_id: id,
    ticker: 'AAPL',
    status: 'succeeded',
    error: null,
    created_at: '2026-07-10T04:00:00',
    updated_at: null,
    outlook: 'bullish',
    shares: 41,
    tier: 1,
    capital: 100000,
    risk_pct: 1,
    ...overrides,
  };
}

function renderHistory(overrides: Partial<RunHistoryProps> = {}) {
  const props: RunHistoryProps = {
    runs: [],
    tickers: [],
    filters: NO_FILTERS,
    onFilters: vi.fn(),
    page: 1,
    pageCount: 1,
    onPage: vi.fn(),
    expandedTaskId: null,
    expandedResult: null,
    expandedError: null,
    onToggle: vi.fn(),
    onDelete: vi.fn(),
    deletingTaskId: null,
    deleteError: null,
    onStop: vi.fn(),
    stoppingTaskIds: [],
    stopError: null,
    ...overrides,
  };
  render(
    <UiLanguageProvider>
      <RunHistory {...props} />
    </UiLanguageProvider>,
  );
  return props;
}

// Min boxes in filter order: capital, risk, rewardRatio, date (the shares
// filter was dropped 2026-08-16).
const minBoxes = () => screen.getAllByPlaceholderText(/^下限$|^Min$/);
const maxBoxes = () => screen.getAllByPlaceholderText(/^上限$|^Max$/);
const DATE_MIN = 3;

// A filter's title: the bold span above its control (the table has
// column headers with the same words).
const titleOf = (text: RegExp) =>
  screen.getAllByText(text).find((el) => el.classList.contains('font-semibold')) as HTMLElement;

const commit = (box: HTMLElement, value: string) => {
  fireEvent.change(box, { target: { value } });
  fireEvent.keyDown(box, { key: 'Enter' });
};

describe('RunHistory', () => {
  it('ends every row in a trash button that deletes after a confirmation, without opening the row', () => {
    const props = renderHistory({
      runs: [makeRun('t1'), makeRun('t2')],
    });
    // One trash per row, in the row itself (no delete link inside an expanded row).
    const [remove] = screen.getAllByTestId('run-delete');
    expect(screen.getAllByTestId('run-delete')).toHaveLength(2);
    expect(remove).not.toHaveTextContent(/Delete/);
    expect(remove.getAttribute('aria-label')).toMatch(/Delete this run|删除这次分析/);
    fireEvent.click(remove);
    expect(props.onToggle).not.toHaveBeenCalled();
    expect(props.onDelete).not.toHaveBeenCalled();
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent(/cannot be undone|无法撤销/);
    fireEvent.click(screen.getByText(/^Keep$|^保留$/));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(props.onDelete).not.toHaveBeenCalled();
    fireEvent.click(remove);
    fireEvent.click(screen.getByTestId('run-delete-confirm'));
    expect(props.onDelete).toHaveBeenCalledWith('t1');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('words removal of a queued run as cancelling it, and offers none for a running one', () => {
    const props = renderHistory({
      runs: [makeRun('q1', { status: 'queued', outlook: undefined })],
    });
    const remove = screen.getByTestId('run-delete');
    expect(remove.getAttribute('aria-label')).toMatch(/Cancel this run|取消本次运行/);
    fireEvent.click(remove);
    expect(screen.getByRole('dialog')).toHaveTextContent(/will not start|不会开始/);
    fireEvent.click(screen.getByTestId('run-delete-confirm'));
    expect(props.onDelete).toHaveBeenCalledWith('q1');

    cleanup();
    renderHistory({
      runs: [makeRun('r1', { status: 'running', outlook: undefined })],
      expandedTaskId: 'r1',
    });
    expect(screen.queryByTestId('run-delete')).not.toBeInTheDocument();
  });

  it('shows the removal in flight and the server’s refusal under the row', () => {
    renderHistory({
      runs: [makeRun('t1')],
      deletingTaskId: 't1',
    });
    const remove = screen.getByTestId('run-delete');
    expect(remove).toBeDisabled();
    expect(remove.getAttribute('aria-label')).toMatch(/Deleting…|删除中…/);

    cleanup();
    renderHistory({
      runs: [makeRun('t1'), makeRun('t2')],
      deleteError: 'This run is in progress and cannot be removed.',
    });
    // The refusal belongs to the row whose removal was confirmed.
    expect(screen.queryByTestId('run-delete-error')).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByTestId('run-delete')[1]);
    fireEvent.click(screen.getByTestId('run-delete-confirm'));
    const error = screen.getByTestId('run-delete-error');
    expect(error).toHaveTextContent(/in progress/);
    const rows = Array.from(document.querySelectorAll('[role="button"][aria-expanded]'));
    expect(rows[1].compareDocumentPosition(error) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('shows a queued row with its place in line and explains it when expanded', () => {
    renderHistory({
      runs: [makeRun('q1', { status: 'queued', queue_position: 3, shares: null })],
      expandedTaskId: 'q1',
    });

    // two runs ahead → this one is 3rd in line
    expect(screen.getByText(/排队中（第 3 位）|Queued \(3rd\)/)).toBeInTheDocument();
    expect(screen.getByText(/轮到时会自动开始|starts by itself/)).toBeInTheDocument();
  });

  it('shows a queued row without a count when the backend sends none', () => {
    renderHistory({ runs: [makeRun('q1', { status: 'queued' })] });

    expect(screen.getByText(/^排队中$|^Queued$/)).toBeInTheDocument();
  });

  it('shows ticker, capital, risk, tier, status, outlook and date per row', () => {
    renderHistory({
      runs: [
        makeRun('t1', { ticker: 'MSFT', tier: 2 }),
        makeRun('t2', {
          ticker: 'NVDA',
          status: 'running',
          outlook: null,
          shares: null,
          tier: null,
          capital: null,
          risk_pct: null,
        }),
      ],
    });

    expect(screen.getByText('MSFT')).toBeInTheDocument();
    expect(screen.getByText('100000')).toBeInTheDocument();
    expect(screen.getByText('1%')).toBeInTheDocument();
    expect(screen.getAllByText(/^\d{4}\/\d{2}\/\d{2}, \d{2}:\d{2}$/)).toHaveLength(2);
    expect(screen.getByText(/层级 2|Tier 2/)).toBeInTheDocument();
    // status and outlook are separate columns (owner request 2026-09-17)
    expect(screen.getByText(/^(成功|Succeeded)$/)).toBeInTheDocument();
    expect(screen.getByText(/看多|Bullish/)).toBeInTheDocument();
    // the shares column was dropped (owner request 2026-08-16)
    expect(screen.queryByText(/41/)).toBeNull();
    expect(screen.getByText('NVDA')).toBeInTheDocument();
    expect(screen.getByText(/分析中|Running/)).toBeInTheDocument();
    // the running row has no capital/risk/reward/hold/tier/outlook yet —
    // six dashes, plus the done row's reward and hold dashes (stored
    // before those inputs were recorded).
    expect(screen.getAllByText('—')).toHaveLength(8);
    // the pager is always there, even when everything fits on one page
    expect(screen.getByRole('button', { name: '1' })).toBeInTheDocument();
  });

  it('draws whatever page the server sent: rows are not filtered here', () => {
    // A row the filters would not admit still shows — the server did the
    // filtering, and this component trusts it.
    renderHistory({
      runs: [makeRun('t1', { ticker: 'MSFT', outlook: 'bearish' })],
      filters: { ...NO_FILTERS, outlooks: ['bullish'], tickers: ['NVDA'] },
    });
    expect(screen.getByText('MSFT')).toBeInTheDocument();
  });

  it('offers a dash in the outlook filter that asks for rows without an outlook', () => {
    const props = renderHistory({ runs: [makeRun('t1', { ticker: 'MSFT' })] });
    fireEvent.focus(screen.getByPlaceholderText(/输入展望|Enter outlook/));
    // the dropdown's dash option (the rows' own dashes are not buttons)
    fireEvent.click(screen.getAllByText('—').find((el) => el.closest('button'))!);
    expect(props.onFilters).toHaveBeenCalledWith({ outlooks: ['no_outlook'] });
  });

  it('shows no status dot before the ticker', () => {
    renderHistory({ runs: [makeRun('t1')] });
    expect(document.querySelector('.rounded-full')).toBeNull();
  });

  it('colors a previous-day report date amber and explains it on click', () => {
    // created_at is 2026-07-10, long before today
    renderHistory({ runs: [makeRun('t1')] });
    const date = screen.getByTestId('run-date-stale');
    expect(date).toHaveClass('text-caution');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(date);
    expect(screen.getByRole('dialog')).toHaveTextContent(/重跑|re-run/);
  });

  it('colors a same-day report date green, and an unfinished run gray', () => {
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, '0');
    const todayUtc =
      `${now.getUTCFullYear()}-${pad(now.getUTCMonth() + 1)}-${pad(now.getUTCDate())}` +
      `T${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:00`;
    renderHistory({
      runs: [
        makeRun('t1', { created_at: todayUtc }),
        makeRun('t2', { status: 'running', created_at: todayUtc, outlook: null }),
      ],
    });
    expect(screen.queryByTestId('run-date-stale')).not.toBeInTheDocument();
    const dates = screen.getAllByText(/^\d{4}\/\d{2}\/\d{2}, \d{2}:\d{2}$/);
    expect(dates[0]).toHaveClass('text-positive');
    expect(dates[1]).toHaveClass('text-ink-3');
  });

  it('asks for capital and risk ranges and shows their pills', () => {
    const props = renderHistory({
      runs: [makeRun('t1', { ticker: 'MSFT' })],
      filters: { ...NO_FILTERS, capitalMin: '100000', riskPctMax: '1' },
    });

    commit(minBoxes()[0], '50000');
    expect(props.onFilters).toHaveBeenLastCalledWith({ capitalMin: '50000' });
    commit(maxBoxes()[1], '2');
    expect(props.onFilters).toHaveBeenLastCalledWith({ riskPctMax: '2' });

    // pills read Label: value and remove on click
    fireEvent.click(screen.getByRole('button', { name: /(Capital Min|本金下限): 100000/ }));
    expect(props.onFilters).toHaveBeenLastCalledWith({ capitalMin: null });
    fireEvent.click(screen.getByRole('button', { name: /(Risk Max|单笔风险上限): 1%/ }));
    expect(props.onFilters).toHaveBeenLastCalledWith({ riskPctMax: null });
  });

  it('offers the tickers the server knows as a multi-pick dropdown filter', () => {
    const props = renderHistory({
      runs: [makeRun('t1', { ticker: 'MSFT' })],
      tickers: ['MSFT', 'NVDA'],
      filters: { ...NO_FILTERS, tickers: ['NVDA'] },
    });

    const tickerBox = screen.getByPlaceholderText(/输入代码|Enter ticker/);
    fireEvent.focus(tickerBox);
    // multi-pick: adding a second ticker keeps the first
    fireEvent.click(screen.getByRole('button', { name: 'MSFT' }));
    expect(props.onFilters).toHaveBeenLastCalledWith({ tickers: ['NVDA', 'MSFT'] });
    // picking a set one again clears it
    fireEvent.click(screen.getByRole('button', { name: 'NVDA' }));
    expect(props.onFilters).toHaveBeenLastCalledWith({ tickers: [] });
    fireEvent.mouseDown(document.body);

    // the pill reads Label: value and removes on click
    fireEvent.click(screen.getByRole('button', { name: /(Ticker|代码): NVDA/ }));
    expect(props.onFilters).toHaveBeenLastCalledWith({ tickers: [] });
  });

  it('clears an outlook filter by picking the same option again', () => {
    const props = renderHistory({
      runs: [makeRun('t1', { ticker: 'MSFT' })],
      filters: { ...NO_FILTERS, outlooks: ['neutral'] },
    });

    fireEvent.focus(screen.getByPlaceholderText(/输入展望|Enter outlook/));
    fireEvent.click(screen.getAllByText(/中性|Neutral/)[0]);
    expect(props.onFilters).toHaveBeenLastCalledWith({ outlooks: [] });
    fireEvent.click(screen.getAllByText(/看多|Bullish/)[0]);
    expect(props.onFilters).toHaveBeenLastCalledWith({ outlooks: ['neutral', 'bullish'] });
  });

  it('asks for a status from the dropdown and shows a dash outlook for a failed run', () => {
    const props = renderHistory({
      runs: [makeRun('t2', { ticker: 'NVDA', status: 'failed', outlook: null })],
      filters: { ...NO_FILTERS, statuses: ['failed'] },
    });

    fireEvent.focus(screen.getByPlaceholderText(/输入状态|Enter status/));
    fireEvent.click(screen.getByRole('button', { name: /^(成功|Succeeded)$/ }));
    expect(props.onFilters).toHaveBeenLastCalledWith({ statuses: ['failed', 'succeeded'] });
    fireEvent.mouseDown(document.body);

    // the failed row's outlook cell is a dash (plus its reward and hold
    // dashes); its status cell says Failed
    expect(screen.getAllByText('—')).toHaveLength(3);
    expect(screen.getByText(/^(失败|Failed)$/)).toBeInTheDocument();
    expect(screen.queryByText(/看多|Bullish/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /(Status|状态): (Failed|失败)/ }));
    expect(props.onFilters).toHaveBeenLastCalledWith({ statuses: [] });
  });

  it('shows a dash outlook for a finished run whose judge produced nothing', () => {
    renderHistory({
      runs: [makeRun('t1', { ticker: 'MSFT', outlook: 'no_outlook' })],
    });

    expect(screen.getByText(/^(成功|Succeeded)$/)).toBeInTheDocument();
    // outlook dash plus the reward and hold dashes
    expect(screen.getAllByText('—')).toHaveLength(3);
  });

  it('asks for a tier from the dropdown and shows its pill', () => {
    const props = renderHistory({
      runs: [makeRun('t2', { ticker: 'NVDA', tier: 2 })],
      filters: { ...NO_FILTERS, tiers: ['2'] },
    });

    fireEvent.focus(screen.getByPlaceholderText(/输入层级|Enter tier/));
    fireEvent.click(screen.getByRole('button', { name: /^1[:：]/ }));
    expect(props.onFilters).toHaveBeenLastCalledWith({ tiers: ['2', '1'] });
    expect(screen.getByRole('button', { name: /(Tier|层级): 2/ })).toBeInTheDocument();
  });

  it('shows the max hold column and asks for a max hold from the dropdown', () => {
    const props = renderHistory({
      runs: [
        makeRun('t1', { ticker: 'MSFT', max_hold_weeks: 2 }),
        // an old stored run without a recorded max hold shows a dash
        makeRun('t2', { ticker: 'NVDA' }),
      ],
      filters: { ...NO_FILTERS, maxHoldWeeks: ['2'] },
    });

    expect(screen.getByText(/^(2w|2 周)$/)).toBeInTheDocument();

    fireEvent.focus(screen.getByPlaceholderText(/输入最长持有|Enter max hold/));
    fireEvent.click(screen.getByRole('button', { name: '3' }));
    expect(props.onFilters).toHaveBeenLastCalledWith({ maxHoldWeeks: ['2', '3'] });

    // the pill wears the same wording as the form's max-hold pill
    fireEvent.click(screen.getByRole('button', { name: /(Max hold|最长持有): 2/ }));
    expect(props.onFilters).toHaveBeenLastCalledWith({ maxHoldWeeks: [] });
  });

  it('asks for a date range and rejects an invalid date instead of committing it', () => {
    const props = renderHistory({
      runs: [makeRun('t1', { ticker: 'MSFT' })],
      filters: { ...NO_FILTERS, dateMin: '2026/07/01' },
    });
    const dateMin = minBoxes()[DATE_MIN];
    const dateMax = maxBoxes()[DATE_MIN];

    commit(dateMax, '2026/07/31');
    expect(props.onFilters).toHaveBeenLastCalledWith({ dateMax: '2026/07/31' });

    commit(dateMin, 'yesterday');
    expect(dateMin).toHaveValue('yesterday');
    expect(props.onFilters).not.toHaveBeenCalledWith({ dateMin: 'yesterday' });

    fireEvent.click(screen.getByRole('button', { name: /2026\/07\/01/ }));
    expect(props.onFilters).toHaveBeenLastCalledWith({ dateMin: null });
  });

  it('shows the column-name header row and asks for a reward range', () => {
    const props = renderHistory({
      runs: [
        makeRun('t1', { ticker: 'MSFT', reward_ratio: 1.5 }),
        makeRun('t2', { ticker: 'NVDA', reward_ratio: 3 }),
      ],
      filters: { ...NO_FILTERS, rewardRatioMin: '2' },
    });
    expect(screen.getByTestId('history-header')).toBeInTheDocument();
    expect(screen.getByText('1.5×')).toBeInTheDocument();
    expect(screen.getByText('3×')).toBeInTheDocument();

    commit(minBoxes()[2], '2.5');
    expect(props.onFilters).toHaveBeenLastCalledWith({ rewardRatioMin: '2.5' });
    expect(
      screen.getByRole('button', { name: /(Reward ratio Min|盈亏比下限): 2×/ }),
    ).toBeInTheDocument();
  });

  it('draws the server’s page count and asks for another page', () => {
    const props = renderHistory({
      runs: Array.from({ length: 10 }, (_, index) => makeRun(`t${index}`)),
      page: 1,
      pageCount: 3,
    });

    expect(screen.getAllByText('AAPL')).toHaveLength(10);
    fireEvent.click(screen.getByRole('button', { name: '2' }));
    expect(props.onPage).toHaveBeenCalledWith(2);
    fireEvent.click(screen.getByRole('button', { name: /最后一页|Last page/ }));
    expect(props.onPage).toHaveBeenCalledWith(3);
  });

  it('says "no match" under filters and "start a run" without them', () => {
    renderHistory({ runs: [], filters: { ...NO_FILTERS, tiers: ['2'] } });
    expect(screen.getByText(/没有符合筛选的运行|No runs match/)).toBeInTheDocument();
  });

  it('says "start a run" when the history is empty and unfiltered', () => {
    renderHistory({ runs: [] });
    expect(screen.getByText(/输入股票代码|Enter a ticker/)).toBeInTheDocument();
  });

  // Stop button (2026-10-19): a running run shows a stop where the trash
  // would sit; once stopped, the row is history with the trash as usual.
  it('ends a running row in a stop button that stops after a confirmation, without opening the row', () => {
    const props = renderHistory({
      runs: [makeRun('r1', { status: 'running', outlook: null, shares: null })],
    });
    expect(screen.queryByTestId('run-delete')).not.toBeInTheDocument();
    const stop = screen.getByTestId('run-stop');
    expect(stop.getAttribute('aria-label')).toMatch(/Stop this run|停止本次运行/);

    fireEvent.click(stop);
    expect(props.onToggle).not.toHaveBeenCalled();
    expect(props.onStop).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toHaveTextContent(/finished|已完成/);
    fireEvent.click(screen.getByText(/^Keep$|^保留$/));
    expect(props.onStop).not.toHaveBeenCalled();

    fireEvent.click(stop);
    fireEvent.click(screen.getByTestId('run-stop-confirm'));
    expect(props.onStop).toHaveBeenCalledWith('r1');
    expect(props.onToggle).not.toHaveBeenCalled();
  });

  it('shows the stop in flight, its refusal under the row, and a stopped row with the trash', () => {
    renderHistory({
      runs: [makeRun('r1', { status: 'running', outlook: null, shares: null })],
      stoppingTaskIds: ['r1'],
      expandedTaskId: 'r1',
    });
    const stop = screen.getByTestId('run-stop');
    expect(stop).toBeDisabled();
    expect(stop.getAttribute('aria-label')).toMatch(/Stopping…|停止中…/);
    // The expanded running row says the stop is on its way.
    expect(screen.getByText(/Stopping…|停止中…/, { selector: 'p' })).toBeInTheDocument();

    cleanup();
    renderHistory({
      runs: [
        makeRun('r1', { status: 'running', outlook: null, shares: null }),
        makeRun('r2', { status: 'running', outlook: null, shares: null }),
      ],
      stopError: 'Could not stop: network down',
    });
    // The refusal belongs to the row whose stop was confirmed.
    expect(screen.queryByTestId('run-stop-error')).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByTestId('run-stop')[1]);
    fireEvent.click(screen.getByTestId('run-stop-confirm'));
    const error = screen.getByTestId('run-stop-error');
    expect(error).toHaveTextContent(/network down/);
    const rows = Array.from(document.querySelectorAll('[role="button"][aria-expanded]'));
    expect(rows[1].compareDocumentPosition(error) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    cleanup();
    const props = renderHistory({
      runs: [makeRun('s1', { status: 'stopped', outlook: null, shares: null })],
    });
    expect(screen.queryByTestId('run-stop')).not.toBeInTheDocument();
    expect(screen.getByText(/^Stopped$|^已停止$/)).toBeInTheDocument();
    // No outlook, whatever the stopped run's analysis found: the dash.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    const remove = screen.getByTestId('run-delete');
    expect(remove.getAttribute('aria-label')).toMatch(/Delete this run|删除这次分析/);
    fireEvent.click(remove);
    fireEvent.click(screen.getByTestId('run-delete-confirm'));
    expect(props.onDelete).toHaveBeenCalledWith('s1');
  });

  it('offers stopped in the status filter', () => {
    const props = renderHistory({ runs: [makeRun('t1')] });
    fireEvent.focus(screen.getByPlaceholderText(/输入状态|Enter status/));
    fireEvent.click(screen.getAllByText(/^Stopped$|^已停止$/).find((el) => el.closest('button'))!);
    expect(props.onFilters).toHaveBeenCalledWith({ statuses: ['stopped'] });
  });

  it('clicking a row asks to expand it; a failed expanded row shows its error', () => {
    const props = renderHistory({
      runs: [
        makeRun('t1', { ticker: 'MSFT' }),
        makeRun('t2', {
          ticker: 'NVDA',
          status: 'failed',
          shares: null,
          tier: null,
          error: 'LLM quota exhausted',
        }),
      ],
      expandedTaskId: 't2',
    });

    fireEvent.click(screen.getByRole('button', { name: /MSFT/ }));
    expect(props.onToggle).toHaveBeenCalledWith('t1');
    expect(screen.getByText('LLM quota exhausted')).toBeInTheDocument();
  });

  it("colors a set filter's title like its pill and leaves the others gray", () => {
    renderHistory({
      runs: [makeRun('t1', { ticker: 'MSFT' })],
      filters: { ...NO_FILTERS, capitalMin: '50000', statuses: ['succeeded'] },
    });
    // one end of a range is enough to count as set
    expect(titleOf(/^Capital$|^本金$/)).toHaveClass('text-orange-700', 'dark:text-orange-300');
    expect(titleOf(/^Status$|^状态$/)).toHaveClass('text-blue-700', 'dark:text-blue-300');
    expect(titleOf(/^Ticker$|^代码$/)).toHaveClass('text-ink-2');
  });
});
