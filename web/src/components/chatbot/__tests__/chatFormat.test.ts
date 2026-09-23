import { describe, expect, it } from 'vitest';
import type { ChatPendingCall } from '../../../api/chat';
import { formatUiText, UI_TEXT, type UiTextKey, type UiTextParams } from '../../../i18n/uiText';
import { argsLine, pendingQuestion, resultError, shortTaskId, sizeText } from '../chatFormat';

const t = (key: UiTextKey, params?: UiTextParams) => formatUiText(UI_TEXT.en[key], params);

const call = (name: string, args: Record<string, unknown>, facts: Record<string, unknown>): ChatPendingCall => ({
  call_id: 'c1',
  name,
  arguments: args,
  facts,
});

describe('sizeText', () => {
  it('words bytes and kilobytes', () => {
    expect(sizeText(0)).toBe('0 B');
    expect(sizeText(900)).toBe('900 B');
    expect(sizeText(1536)).toBe('1.5 KB');
    expect(sizeText(20 * 1024)).toBe('20 KB');
    expect(sizeText(null)).toBe('0 B');
  });
});

describe('pendingQuestion', () => {
  it('words a run start from the effective inputs', () => {
    const asked = pendingQuestion(
      call('start_run', { stock_code: 'aapl' }, {
        stock_code: 'AAPL', tier: 2, hold_weeks: 3, capital: 50000, risk_fraction: 0.005,
        reward_risk: 2.5, run_anyway: true,
      }),
      t,
    );
    expect(asked.question).toBe(
      'Start a deep analysis of AAPL? Max hold 3 weeks, capital 50,000, risk 0.5%, reward-to-risk 2.5. '
      + 'The market is open, so it will analyze the previous completed session.',
    );
    expect(asked.yes).toBe('Start');
    expect(asked.tone).toBe('start');
  });

  it('tells a cancel from a delete by the run status', () => {
    const queued = pendingQuestion(
      call('delete_run', { task_id: 'q' }, { run: { stock_code: 'MSFT', status: 'queued' } }),
      t,
    );
    expect(queued.question).toBe('Cancel the queued MSFT run? It leaves the line and is deleted.');
    expect(queued.yes).toBe('Cancel the run');
    const done = pendingQuestion(
      call('delete_run', { task_id: 'd' }, {
        run: { stock_code: 'MSFT', status: 'done', created_at: '2026-09-18T10:00:00' },
      }),
      t,
    );
    expect(done.question).toBe(
      'Delete the MSFT run from 2026-09-18 (done) and its AI transcript? This cannot be undone.',
    );
    expect(done.tone).toBe('delete');
  });

  it('prices the large reads', () => {
    const report = pendingQuestion(
      call('get_dimension_report', { task_id: '6ff58a4026a341e5', dimension: 'technicals' },
        { chars: 22000, tokens_estimate: 5500 }),
      t,
    );
    expect(report.question).toBe(
      'Read the Technicals report of run 6ff58a40 into the model? About 21 KB, roughly 5,500 tokens of your API budget.',
    );
    expect(report.yes).toBe('Read it');
    expect(report.tone).toBe('read');
    const callText = pendingQuestion(
      call('get_transcript_call', { task_id: 'abcdefghij', seq: 7 }, { chars: 500, tokens_estimate: 125 }),
      t,
    );
    expect(callText.question).toBe(
      'Read AI call #7 of run abcdefgh (prompt and reply) into the model? About 1 KB, roughly 125 tokens of your API budget.',
    );
  });

  it('falls back to a generic question', () => {
    expect(pendingQuestion(call('mystery', {}, {}), t).question).toBe('Allow mystery?');
  });
});

describe('helpers', () => {
  it('reads an error code out of a tool result', () => {
    expect(resultError({ error: 'not_found' })).toBe('not_found');
    expect(resultError({ items: [] })).toBeNull();
    expect(resultError('text')).toBeNull();
  });

  it('shortens task ids and lists arguments on one line', () => {
    expect(shortTaskId('6ff58a4026a341e5a7cae7cd51999bb0')).toBe('6ff58a40');
    expect(argsLine({ task_id: '6ff58a4026a341e5', sections: ['plan'], ticker: [], page: 1, x: null })).toBe(
      'task_id=6ff58a40 sections=plan page=1',
    );
  });
});

