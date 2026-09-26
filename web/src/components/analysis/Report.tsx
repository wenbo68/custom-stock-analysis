import { useState, type ComponentProps, type ReactNode } from 'react';
import { tieredApi, type TieredResult, type TieredTierSection } from '../../api/tiered';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import { cn } from '../../utils/cn';
import { flashElement } from '../tiered/termHelpers';
import { isPlanNote } from './warningText';
import { HelpTerm as BaseHelpTerm } from '../tiered/terms';
import { adjustedCellId, computedCellId } from './format';
import { RewardRatioValue, type PlanColumn, type RewardRatioValues } from './PlanWarnings';
import { fillTemplate } from './template';
import { ALT_LINK, OUTLOOK_TEXT } from './styles';
import { Card, Modal, WarningsButton } from './Ui';
import { SummaryOutline } from './SummaryOutline';
import { VoteTree, VoteScores, type VoteItemsLoader } from './VoteTree';
import { DataReports } from './DataReports';
import { TradePlan } from './TradePlan';
import { Transcript } from './Transcript';

// ---------- small shared pieces ----------

// Alt skin rule: help popups everywhere, dotted underlines nowhere.
const HelpTerm = (props: ComponentProps<typeof BaseHelpTerm>) => (
  <BaseHelpTerm underline={false} {...props} />
);

// An UPPERCASE title sitting above its card, like the page's section titles.
const Block = ({
  title,
  helpKey,
  children,
}: {
  title: string;
  helpKey?: UiTextKey;
  children: ReactNode;
}) => (
  <section className="flex flex-col gap-2">
    <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
      {helpKey ? <HelpTerm label={title} helpKey={helpKey} /> : title}
    </h3>
    {children}
  </section>
);

// ---------- tier cards ----------

// One header fact — quiet label, prominent value; the same styling for
// outlook, size, stop loss and score alike (children may recolor the
// value, e.g. the outlook's buy/hold/sell tint).
const Fact = ({
  label,
  helpKey,
  children,
}: {
  label: string;
  helpKey?: UiTextKey;
  children: ReactNode;
}) => (
  <span className="text-xs text-gray-500">
    {helpKey ? <HelpTerm label={label} helpKey={helpKey} /> : label}
    {': '}
    <span className="text-sm font-semibold text-gray-200">{children}</span>
  </span>
);

interface TierHeaderProps {
  section: Pick<TieredTierSection, 'outlook'>;
  notes?: string[];
  side?: ReactNode;
}

// The card's title lives above the card (Block); inside, the header is
// one row of `Label: value` facts — Outlook first, then any side facts
// (the deep-analysis score) — and the data-notes mark pinned top-right:
// nothing when there is nothing to report, ⚠ when there is.
const TierHeader = ({ section, notes, side }: TierHeaderProps) => {
  const { t } = useUiLanguage();
  const outlook = section.outlook ?? 'no_outlook';
  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-6 gap-y-1">
      <Fact label={t('tiered.outlook')}>
        {/* Same bullish/neutral/bearish tint as the run-history rows. */}
        <span className={OUTLOOK_TEXT[outlook]}>
          {t(`tiered.outlook.${outlook}` as UiTextKey)}
        </span>
      </Fact>
      {side}
      <span className="ml-auto">
        <WarningsButton notes={notes ?? []} />
      </span>
    </div>
  );
};

// ---------- outlook + action ----------

// The numbers behind a "Buy later": the plan review's reward-below-goal
// warning carries them; a run without that warning (none expected) falls
// back to the same arithmetic over the plan levels.
const rewardRatioValues = (result: TieredResult): RewardRatioValues | null => {
  const warning = (result.plan_warnings?.target ?? []).find(
    (entry) => entry.id === 'reward_below_goal',
  );
  if (warning) {
    const v = warning.values;
    return { entry: v.entry, stop_loss: v.stop_loss, target: v.target, ratio: v.ratio };
  }
  const { entry, stop_loss, target } = result.levels;
  if (entry == null || stop_loss == null || target == null || entry === stop_loss) {
    return null;
  }
  return {
    entry,
    stop_loss,
    target,
    ratio: (target - entry) / (entry - stop_loss),
  };
};

// Flash the plan cell a price came from: the adjusted cell when the
// plan review moved that level, else the computed one.
const jumpToPlanCell = (key: PlanColumn) => {
  if (!flashElement(adjustedCellId(key))) {
    flashElement(computedCellId(key));
  }
};

// The personal action code derived from the outlook and the plan.
// "Buy later" says why, inline: the plan's current reward-to-risk,
// clickable for its arithmetic (owner request 2026-09-16). Shown on
// whichever analysis card the run has (owner decision 2026-09-18: the
// separate conclusion card is gone).
const ActionFact = ({ result }: { result: TieredResult }) => {
  const { t } = useUiLanguage();
  const action = result.action ?? 'no_outlook';
  const rewardValues = action === 'buy_later' ? rewardRatioValues(result) : null;
  return (
    <Fact label={t('tiered.action')} helpKey="tiered.help.action">
      {t(`tiered.action.${action}` as UiTextKey)}
      {rewardValues ? (
        <span data-testid="action-reason">
          {' ('}
          {fillTemplate(t('tiered.actionRatio'), {
            ratio: <RewardRatioValue values={rewardValues} onJump={jumpToPlanCell} />,
          })}
          {')'}
        </span>
      ) : null}
    </Fact>
  );
};

// The run-level analysis/data notes: everything but the plan-flavored
// warnings, which stay on the plan card.
const analysisNotes = (result: TieredResult): string[] =>
  (result.warnings ?? []).filter((raw) => !isPlanNote(raw));

// The preliminary-analysis card (tier-1): the impersonal outlook and
// the personal action, plus the run-level notes mark. (The old earnings
// warning is gone — the date lives on the fundamentals card; the
// previous-day note moved to the history row's date, 2026-09-18.)
const Preliminary = ({ result }: { result: TieredResult }) => {
  const { t } = useUiLanguage();
  const outlook = result.outlook ?? 'no_outlook';
  return (
    <Card testId="preliminary-analysis">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
        <Fact label={t('tiered.outlook')} helpKey="tiered.help.outlook">
          <span className={OUTLOOK_TEXT[outlook]}>
            {t(`tiered.outlook.${outlook}` as UiTextKey)}
          </span>
        </Fact>
        <ActionFact result={result} />
        <span className="ml-auto">
          <WarningsButton notes={analysisNotes(result)} />
        </span>
      </div>
    </Card>
  );
};

interface PlanProps {
  result: TieredResult;
  /** The run's task id — the shares receipt links the run-row inputs. */
  runId?: string;
}

// Backend note strings whose fact the plan table's structured warnings
// row already carries under these ids — the row recomputes its numbers
// from the FINAL (post-review) levels, so the note's stale copy must not
// show beside it (owner decision 2026-07-24).
const NOTE_RE_BY_PLAN_WARNING_ID: Record<string, RegExp> = {
  downtrend: /^trend warning: /,
  reward_below_goal: /^reward below goal: /,
};

// The plan card's data notes: the plan-flavored run warnings (the
// analysis/data notes stay on the preliminary card), minus anything the
// plan's own warnings row already states.
const planCardNotes = (result: TieredResult): string[] => {
  const shownIds = new Set(
    Object.values(result.plan_warnings ?? {})
      .flat()
      .map((warning) => warning.id),
  );
  return (result.warnings ?? [])
    .filter(isPlanNote)
    .filter(
      (raw) =>
        !Object.entries(NOTE_RE_BY_PLAN_WARNING_ID).some(
          ([id, pattern]) => shownIds.has(id) && pattern.test(raw),
        ),
    );
};

// The trade plan in its own card, under the analysis (owner order,
// 2026-07-22). The data-notes mark floats in the card's top-right corner
// so it never occupies a line of its own. Only bullish-outlook runs
// render this card at all (owner decision 2026-08-05), so the plan
// inside is never empty.
const PlanCard = ({ result, runId }: PlanProps) => (
  <Card testId="plan" className="relative">
    <span className="absolute right-5 top-5">
      <WarningsButton notes={planCardNotes(result)} />
    </span>
    <TradePlan
      levels={result.levels}
      levelsDetail={result.levels_detail}
      planWarnings={result.plan_warnings ?? null}
      runId={runId}
    />
  </Card>
);

interface DebateProps {
  result: TieredResult;
  section: TieredTierSection;
  /** The run's task id — the vote tree fetches its items by it. */
  runId?: string;
  loadItems: VoteItemsLoader;
}

// The deep-analysis card: the outlook, the clickable pool score, the
// action, the fixed-outline report, and the evidence vote tree. Its
// notes mark carries the card's own warnings plus the run-level ones
// (owner decision 2026-09-18: the conclusion card that held them is gone).
const Debate = ({ result, section, runId, loadItems }: DebateProps) => {
  const { t } = useUiLanguage();
  const [scoreOpen, setScoreOpen] = useState(false);
  const detail = section.detail ?? null;
  const outlook = detail?.outlook ?? null;
  const notes = Array.from(new Set([...section.warnings, ...analysisNotes(result)]));
  return (
    <Card testId="deep_analysis">
      <TierHeader
        section={section}
        notes={notes}
        side={
          <>
            {outlook?.final_score != null ? (
              <Fact label={t('tiered.score')} helpKey="tiered.help.deepAnalysisScore">
                {/* Clicking the score opens its arithmetic (owner
                    decision 2026-07-22 — moved out of the fold). */}
                <button
                  type="button"
                  data-testid="deep-analysis-score"
                  className={cn('cursor-pointer tabular-nums', ALT_LINK)}
                  onClick={() => setScoreOpen(true)}
                >
                  {outlook.final_score.toFixed(2)}/10
                </button>
              </Fact>
            ) : null}
            <ActionFact result={result} />
          </>
        }
      />
      {outlook?.summary_structure ? (
        <div className="mb-2">
          <SummaryOutline structure={outlook.summary_structure} />
        </div>
      ) : section.summary ? (
        <p className="mb-2 text-sm leading-relaxed">{section.summary}</p>
      ) : null}
      {!outlook ? (
        <p className="text-sm text-amber-300">{t('tiered.deepAnalysis.noOutlook')}</p>
      ) : null}
      {detail && runId ? <VoteTree runId={runId} loader={loadItems} /> : null}
      {detail ? (
        <Modal
          isOpen={scoreOpen}
          title={t('tiered.tree.scores')}
          onClose={() => setScoreOpen(false)}
          panelClassName="w-fit min-w-72 max-w-[95vw]"
        >
          <VoteScores detail={detail} />
        </Modal>
      ) : null}
    </Card>
  );
};

// ---------- the whole result ----------

interface ResultProps {
  result: TieredResult;
  /** The run's task id — lets formula numbers link back to the run row. */
  runId?: string;
  /** Test seam; production pages the vote items from the server. */
  debateItemsLoader?: VoteItemsLoader;
}

// The fixed skeleton (owner order 2026-09-18): the dataReport reports →
// one analysis card (preliminary at tier-1, deep at tier-2; both carry
// the outlook and the action) → the trade plan (levels + shares +
// warnings). The separate conclusion card is gone.
export const Report = ({
  result,
  runId,
  debateItemsLoader = tieredApi.getAllVoteItems,
}: ResultProps) => {
  const { t } = useUiLanguage();
  const usage = result.llm_usage ?? null;
  // Token total is the exact sum of what the provider reported per call
  // — the same numbers the transcript shows for each exchange.
  const usageLine = (u: NonNullable<typeof usage>) =>
    t('tiered.llmUsage', {
      calls: u.total.calls,
      tokens: u.total.input_tokens + u.total.output_tokens,
    });

  return (
    <div className="flex flex-col gap-6">
      <Block title={t('tiered.dataReports.title')}>
        <DataReports dataReports={result.data_reports} />
      </Block>
      {result.deep_analysis ? (
        <Block title={t('tiered.deepAnalysis.title')} helpKey="tiered.help.deepAnalysis">
          <Debate
            result={result}
            section={result.deep_analysis}
            runId={runId}
            loadItems={debateItemsLoader}
          />
        </Block>
      ) : (
        <Block title={t('tiered.preliminaryAnalysis.title')} helpKey="tiered.help.outlook">
          <Preliminary result={result} />
        </Block>
      )}
      {result.outlook === 'bullish' ? (
        // The trade plan sits under the analysis that judged it — and
        // only under a bullish one (owner decision 2026-08-05): a
        // neutral/bearish/unknown outlook shows no plan section at all;
        // the action line already says what to do.
        <Block title={t('tiered.tradePlan.title')} helpKey="tiered.help.plan">
          <PlanCard result={result} runId={runId} />
        </Block>
      ) : null}
      <div className="flex flex-col gap-1 text-xs">
        {usage && usage.total.calls > 0 ? (
          runId && usage.transcript_entries ? (
            // The usage line is the transcript toggle when the run kept
            // one; runs without a transcript (expired, or recorded
            // before it existed) show the same line as plain text.
            <Transcript runId={runId} label={usageLine(usage)} />
          ) : (
            <p className="text-gray-600">
              <HelpTerm label={usageLine(usage)} helpKey="tiered.help.llmUsage" />
            </p>
          )
        ) : null}
      </div>
    </div>
  );
};
