import type { ChatPendingCall } from '../../api/chat';
import type { UiTextKey, UiTextParams } from '../../i18n/uiText';

type Translate = (key: UiTextKey, params?: UiTextParams) => string;

// Sizes the way the rest of the app words them: whole KB above 1 KB.
export const sizeText = (chars: number | null | undefined): string => {
  const n = chars ?? 0;
  if (n < 1024) {
    return `${n} B`;
  }
  return `${(n / 1024).toFixed(n < 10 * 1024 ? 1 : 0)} KB`;
};

const kbText = (chars: number): string => Math.max(1, Math.round(chars / 1024)).toString();

const DIMENSION_KEYS: Record<string, UiTextKey> = {
  technicals: 'tiered.dimension.technicals',
  fundamentals: 'tiered.dimension.fundamentals',
  macro_economy: 'tiered.dimension.macro_economy',
  positioning: 'tiered.dimension.positioning',
  company_news: 'tiered.dimension.company_news',
  world_news: 'tiered.dimension.world_news',
};

export const dimensionLabel = (name: string, t: Translate): string => {
  const key = DIMENSION_KEYS[name];
  return key ? t(key) : name;
};

// A task id the way the chat shows it: enough to recognise, not the
// whole 32 characters.
export const shortTaskId = (taskId: unknown): string => String(taskId ?? '').slice(0, 8);

export type PendingQuestion = {
  question: string;
  yes: string;
  /** Colors the yes button: an action that costs money, one that
   *  destroys data, or a read that costs tokens. */
  tone: 'start' | 'delete' | 'read';
};

const num = (value: unknown): number | null => (typeof value === 'number' ? value : null);
const str = (value: unknown): string => (value == null ? '' : String(value));

// The question the page asks for a held tool call, worded from the
// facts the backend gathered (src/chatbot/tools.py confirmers).
export const pendingQuestion = (call: ChatPendingCall, t: Translate): PendingQuestion => {
  const facts = call.facts ?? {};
  const args = call.arguments ?? {};
  switch (call.name) {
    case 'start_run': {
      const depth = num(facts.tier) === 2 ? t('chat.confirm.depth.2') : t('chat.confirm.depth.1');
      const risk = num(facts.risk_fraction);
      let question = t('chat.confirm.startRun', {
        depth,
        ticker: str(facts.stock_code || args.stock_code),
        hold: str(facts.hold_weeks),
        capital: num(facts.capital)?.toLocaleString() ?? '',
        risk: risk == null ? '' : String(Number((risk * 100).toFixed(4))),
        reward: str(facts.reward_risk),
      });
      if (facts.run_anyway === true) {
        question += ` ${t('chat.confirm.startRunAnyway')}`;
      }
      return { question, yes: t('chat.confirm.yes.start'), tone: 'start' };
    }
    case 'delete_run': {
      const run = (facts.run ?? {}) as Record<string, unknown>;
      const ticker = str(run.stock_code);
      if (run.status === 'queued') {
        return {
          question: t('chat.confirm.cancelRun', { ticker }),
          yes: t('chat.confirm.yes.cancel'),
          tone: 'delete',
        };
      }
      return {
        question: t('chat.confirm.deleteRun', {
          ticker,
          status: str(run.status),
          date: str(run.created_at).slice(0, 10),
        }),
        yes: t('chat.confirm.yes.delete'),
        tone: 'delete',
      };
    }
    case 'get_dimension_report':
      return {
        question: t('chat.confirm.readDimension', {
          dimension: dimensionLabel(str(args.dimension), t),
          task: shortTaskId(args.task_id),
          kb: kbText(num(facts.chars) ?? 0),
          tokens: (num(facts.tokens_estimate) ?? 0).toLocaleString(),
        }),
        yes: t('chat.confirm.yes.read'),
        tone: 'read',
      };
    case 'get_transcript_call':
      return {
        question: t('chat.confirm.readCall', {
          seq: str(args.seq),
          task: shortTaskId(args.task_id),
          kb: kbText(num(facts.chars) ?? 0),
          tokens: (num(facts.tokens_estimate) ?? 0).toLocaleString(),
        }),
        yes: t('chat.confirm.yes.read'),
        tone: 'read',
      };
    default:
      return {
        question: t('chat.confirm.generic', { name: call.name }),
        yes: t('chat.confirm.yes.generic'),
        tone: 'start',
      };
  }
};

// A tool result's error code when it answered with one.
export const resultError = (result: unknown): string | null => {
  if (result && typeof result === 'object' && 'error' in result) {
    const code = (result as { error?: unknown }).error;
    return code == null ? null : String(code);
  }
  return null;
};

// One line of arguments for the trace title: `task_id=6ff58a40 sections=plan`.
export const argsLine = (args: Record<string, unknown>): string =>
  Object.entries(args)
    .filter(([, value]) => value !== undefined && value !== null && value !== '' && !(Array.isArray(value) && value.length === 0))
    .map(([key, value]) => {
      const shown = key === 'task_id' ? shortTaskId(value) : Array.isArray(value) ? value.join(',') : String(value);
      return `${key}=${shown}`;
    })
    .join(' ');

