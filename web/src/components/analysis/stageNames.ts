import type { UiTextKey } from '../../i18n/uiText';

// The stage names a stopped run's banner can carry, as the page already
// words them: the data reports' titles, then the three analysis steps.
const STAGE_KEYS: Record<string, UiTextKey> = {
  technicals: 'tiered.dataReport.technicals',
  fundamentals: 'tiered.dataReport.fundamentals',
  macro_economy: 'tiered.dataReport.macro_economy',
  positioning: 'tiered.dataReport.positioning',
  company_news: 'tiered.dataReport.company_news',
  world_news: 'tiered.dataReport.world_news',
  preliminary_analysis: 'tiered.preliminaryAnalysis.title',
  deep_analysis: 'tiered.deepAnalysis.title',
  trade_plan: 'tiered.tradePlan.title',
};

export const stageName = (stage: string, t: (key: UiTextKey) => string): string =>
  STAGE_KEYS[stage] ? t(STAGE_KEYS[stage]) : stage;
