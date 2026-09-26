import { useMemo, useState, type ReactNode } from 'react';
import type {
  TieredLevelDetail,
  TieredLevelReason,
  TieredLevels,
  TieredLevelsDetail,
  TieredPlanWarnings,
  TieredReviewFailure,
} from '../../api/tiered';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { metricEntry } from '../../i18n/metricLabels';
import type { UiTextKey } from '../../i18n/uiText';
import { cn } from '../../utils/cn';
import { flashElement, formatPrice, jumpToMetricFirst } from '../tiered/termHelpers';
import { HelpTerm as BaseHelpTerm } from '../tiered/terms';
import { LinkedTextV8 } from './VoteTree';
import { WarningsCell } from './PlanWarnings';
import { adjustedCellId, computedCellId, plainNumber, riskPctText } from './format';
import { ALT_LINK, FORMULA_LINE, FORMULA_RESULT } from './styles';
import {
  EvidenceRefs,
  Modal,
  ModalTitle,
  SectionLabel,
  FVar,
  MODAL_BODY,
  MODAL_STRONG,
} from './Ui';

// Alt skin rule: help popups everywhere, dotted underlines nowhere.
const HelpTerm = (props: Parameters<typeof BaseHelpTerm>[0]) => (
  <BaseHelpTerm underline={false} {...props} />
);

// Backup entry retired (owner decision, 2026-07-21): the plan is one
// order at the entry, so the table shows three levels — old stored
// runs simply no longer render their backup column. The plan-review
// redesign (2026-07-22) adds the shares column at the end.
const LEVEL_ORDER = ['entry', 'stop_loss', 'target'] as const;
type LevelKey = (typeof LEVEL_ORDER)[number];
const COLUMNS = ['entry', 'stop_loss', 'target', 'shares'] as const;
type ColumnKey = (typeof COLUMNS)[number];

const LEVEL_LABEL_KEYS: Record<ColumnKey, UiTextKey> = {
  entry: 'tiered.levels.entry',
  stop_loss: 'tiered.levels.stopLoss',
  target: 'tiered.levels.target',
  shares: 'tiered.levels.shares',
};

const LEVEL_HELP_KEYS: Record<ColumnKey, UiTextKey> = {
  entry: 'tiered.help.entry',
  stop_loss: 'tiered.help.stopLoss',
  target: 'tiered.help.target',
  shares: 'tiered.help.sizing',
};

// Every risk line — an AI adjustment reason or a plan warning — opens
// with a fixed keyword so the reader can categorize it at a glance
// (owner decision 2026-07-22). The keyword comes from the backend's
// deterministic check/warning id, never from LLM text; unknown ids
// render without one rather than get a made-up label.
const CHECK_KEYWORD_KEYS: Record<string, UiTextKey> = {
  downtrend: 'tiered.checkKey.downtrend',
  liquidity: 'tiered.checkKey.liquidity',
  volatility: 'tiered.checkKey.volatility',
  stop_vs_support: 'tiered.checkKey.stop_vs_support',
};

// One vote item per reason, each opening with its check keyword.
// `leading` renders as the first vote item regardless of reasons — the
// shares modal always opens with its arithmetic receipt (2026-07-22).
const AdjustReasonList = ({
  reasons,
  leading,
}: {
  reasons: TieredLevelReason[];
  leading?: ReactNode;
}) => {
  const { t } = useUiLanguage();
  if (!leading && reasons.length === 0) {
    return null;
  }
  return (
    <ul className="flex list-disc flex-col gap-2 pl-4" data-testid="adjust-reasons">
      {leading ? <li data-testid="adjust-receipt">{leading}</li> : null}
      {reasons.map((reason, index) => {
        const keywordKey = CHECK_KEYWORD_KEYS[reason.check];
        return (
          <li key={index}>
            <span className={MODAL_STRONG}>{keywordKey ? t(keywordKey) : reason.check}: </span>
            <LinkedTextV8 text={reason.text} links={reason.links ?? []} />
          </li>
        );
      })}
    </ul>
  );
};

// Formula inputs with a source row on the technicals card, and the
// payload path that row anchors at.
const TECHNICALS_INPUT_REFS: Record<string, string[]> = {
  close: ['technicals.price.close'],
  atr_14: ['technicals.volatility.atr_14'],
  sma_50: ['technicals.daily.sma_50'],
  sma_200: ['technicals.daily.sma_200'],
  support_1: ['technicals.levels.support_1'],
  resistance_1: ['technicals.levels.resistance_1'],
  high_1y: ['technicals.price.high_1y'],
};

// Formula inputs that ARE another computed level of this same table (the
// stop uses the computed entry, the target uses the computed stop) — their
// numbers link to that computed cell, so every number in a formula points
// at a place it already appeared.
const COMPUTED_CELL_INPUTS: Record<string, LevelKey> = {
  ideal_entry: 'entry',
  stop_loss: 'stop_loss',
};

// On-screen names for formula variables: report inputs carry the exact
// label their technicals row shows (metricLabels shorts, owner decision
// 2026-07-28) — never raw underscore tokens. Variables that are the
// plan's own numbers reuse the card's uiText names (the backend key
// is ideal_entry; it displays as the entry).
const useVarLabel = (): ((key: string) => string) => {
  const { language, t } = useUiLanguage();
  return (key: string): string => {
    if (key === 'ideal_entry') return t('tiered.f.entry');
    if (key === 'stop_loss') return t('tiered.f.stop');
    if (key === 'round_level') return t('tiered.roundLevelTitle');
    return metricEntry(key, language)?.short ?? key;
  };
};

// The stored formulas name two input GROUPS in prose. Expanding the
// phrases into the run's actual input keys lets the split-and-link
// machinery below turn every one of them into a real, clickable number.
const SUPPORT_KEYS = ['sma_50', 'sma_200', 'support_1', 'round_level'];
const RESISTANCE_KEYS = ['resistance_1', 'high_1y'];

const expandProse = (formula: string, inputs: Record<string, number>): string => {
  let expanded = formula;
  const supports = SUPPORT_KEYS.filter((key) => inputs[key] !== undefined);
  if (supports.length > 0) {
    expanded = expanded.replace('support candidates', supports.join(', '));
  }
  const resistances = RESISTANCE_KEYS.filter((key) => inputs[key] !== undefined);
  if (resistances.length > 0) {
    expanded = expanded.replace(
      'nearest overhead resistance',
      `nearest of (${resistances.join(', ')})`,
    );
  }
  return expanded;
};

const splitOnInputs = (formula: string, inputs: Record<string, number>): string[] => {
  const keys = Object.keys(inputs).sort((a, b) => b.length - a.length);
  if (keys.length === 0) {
    return [formula];
  }
  return expandProse(formula, inputs).split(new RegExp(`(${keys.join('|')})`, 'g'));
};

// The round level is computed on the spot (the largest round price below
// the close), so it has no source row to link to — clicking it opens a
// small how-computed note instead.
const RoundLevelNumber = ({ value }: { value: number }) => {
  const { t } = useUiLanguage();
  const [isOpen, setIsOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        aria-label={t('tiered.roundLevelTitle')}
        data-testid="round-level"
        className={cn('cursor-pointer tabular-nums', ALT_LINK)}
        onClick={() => setIsOpen(true)}
      >
        {formatPrice(value)}
      </button>
      <Modal
        isOpen={isOpen}
        title={t('tiered.roundLevelTitle')}
        onClose={() => setIsOpen(false)}
      >
        <p className={MODAL_BODY}>
          {t('tiered.roundLevelBody', { value: formatPrice(value) })}
        </p>
      </Modal>
    </>
  );
};

// One plugged-in number, linking to where it already appears — a
// technicals metric row, or another computed cell of the levels table.
const InputNumberLink = ({
  inputKey,
  value,
  onNavigate,
}: {
  inputKey: string;
  value: number;
  onNavigate: () => void;
}) => {
  const varLabel = useVarLabel();
  if (inputKey === 'round_level') {
    return <RoundLevelNumber value={value} />;
  }
  const computedTarget = COMPUTED_CELL_INPUTS[inputKey];
  const technicalsRefs = TECHNICALS_INPUT_REFS[inputKey];
  const jump = technicalsRefs
    ? () => jumpToMetricFirst(technicalsRefs)
    : computedTarget
      ? () => flashElement(computedCellId(computedTarget))
      : null;
  if (!jump) {
    return <span className="tabular-nums">{formatPrice(value)}</span>;
  }
  return (
    <button
      type="button"
      aria-label={varLabel(inputKey)}
      className={cn('cursor-pointer tabular-nums', ALT_LINK)}
      onClick={() => {
        onNavigate();
        // Let the modal unmount before scrolling to the row behind it.
        window.setTimeout(jump, 50);
      }}
    >
      {formatPrice(value)}
    </button>
  );
};

interface FormulaProps {
  formula: string;
  inputs: Record<string, number>;
  onNavigate: () => void;
}

// The formula in words: variables italic, everything else as written.
const FormulaWords = ({ formula, inputs }: Omit<FormulaProps, 'onNavigate'>) => {
  const varLabel = useVarLabel();
  return (
    <>
      {splitOnInputs(formula, inputs).map((part, index) =>
        inputs[part] === undefined ? (
          <span key={index}>{part}</span>
        ) : (
          <FVar key={index}>{varLabel(part)}</FVar>
        ),
      )}
    </>
  );
};

// The formula with each input replaced by this run's number.
const Formula = ({ formula, inputs, onNavigate }: FormulaProps) => {
  const parts = useMemo(() => splitOnInputs(formula, inputs), [formula, inputs]);

  return (
    <>
      {parts.map((part, index) =>
        inputs[part] === undefined ? (
          <span key={index}>{part}</span>
        ) : (
          <InputNumberLink key={index} inputKey={part} value={inputs[part]} onNavigate={onNavigate} />
        ),
      )}
    </>
  );
};

interface LevelCellProps {
  levelKey: LevelKey;
  detail: TieredLevelDetail | null;
  label: string;
}

// The computed (formula-base) number. Clicking it opens the receipts, in
// the shares-computation shape: the formula, the formula with this run's
// numbers plugged in (each number a link to its source), and the result.
const ComputedCell = ({ levelKey, detail, label }: LevelCellProps) => {
  const { t } = useUiLanguage();
  const [isOpen, setIsOpen] = useState(false);
  const close = () => setIsOpen(false);

  if (!detail || detail.base === null) {
    return <span className="text-gray-600">—</span>;
  }

  return (
    <>
      <button
        type="button"
        id={computedCellId(levelKey)}
        data-testid={`level-computed-${levelKey}`}
        onClick={() => setIsOpen(true)}
        className={cn('cursor-pointer tabular-nums', ALT_LINK)}
      >
        {formatPrice(detail.base)}
      </button>
      <Modal
        isOpen={isOpen}
        title={<ModalTitle subject={label} kind={t('tiered.kind.formula')} />}
        onClose={close}
        // Fit the widest formula line; each line stays a single line.
        panelClassName="w-fit min-w-72 max-w-[95vw]"
      >
        {!detail.formula ? (
          <p>{t('tiered.levelModal.noBase')}</p>
        ) : (
          <div className="flex flex-col gap-2 overflow-x-auto text-sm" data-testid="formula-modal">
            <p className={FORMULA_LINE} data-testid="formula-words">
              <FormulaWords formula={detail.formula} inputs={detail.inputs ?? {}} />
            </p>
            <p className={FORMULA_LINE} data-testid="formula-plugged">
              {'= '}
              <Formula formula={detail.formula} inputs={detail.inputs ?? {}} onNavigate={close} />
            </p>
            <p className={FORMULA_RESULT}>= {formatPrice(detail.base)}</p>
          </div>
        )}
      </Modal>
    </>
  );
};

// The AI's adjusted number — or "keep" when the computed value stands.
// Clicking the number opens why the AI moved it, with its references.
const AdjustedCell = ({ levelKey, detail, label }: LevelCellProps) => {
  const { t } = useUiLanguage();
  const [isOpen, setIsOpen] = useState(false);
  const close = () => setIsOpen(false);

  if (!detail || detail.base === null) {
    return <span className="text-gray-600">—</span>;
  }
  if (detail.adjusted === null) {
    return (
      <span data-testid={`level-keep-${levelKey}`} className="text-gray-500">
        {t('tiered.levels.keep')}
      </span>
    );
  }

  return (
    <>
      <button
        type="button"
        id={adjustedCellId(levelKey)}
        data-testid={`level-adjusted-${levelKey}`}
        onClick={() => setIsOpen(true)}
        className={cn('cursor-pointer tabular-nums', ALT_LINK)}
      >
        {formatPrice(detail.adjusted)}
      </button>
      <Modal
        isOpen={isOpen}
        title={<ModalTitle subject={label} kind={t('tiered.kind.adjustment')} />}
        onClose={close}
      >
        <div className={MODAL_BODY}>
          {/* No header lines (owner decision 2026-07-22): straight to the
              bulleted reasons, keyword first, cited values linked. */}
          <AdjustReasonList reasons={detail.reasons ?? []} />
          {detail.evidence.length > 0 ? (
            <div>
              <SectionLabel>{t('tiered.levelModal.references')}</SectionLabel>
              <ul className="flex flex-col gap-1">
                {detail.evidence.map((refPath, index) => (
                  <li key={index} className="flex gap-2 text-xs">
                    <span className="shrink-0 text-gray-500">[{index + 1}]</span>
                    <EvidenceRefs refs={[refPath]} onNavigate={close} />
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </Modal>
    </>
  );
};

// When the check-adjust cycle never converged, the backend threw every
// adjustment away — the whole adjusted row shows "keep" in link-blue and
// clicking any of them opens what still failed in each round.
const KeepFailedCell = ({
  columnKey,
  detail,
  failures,
}: {
  columnKey: ColumnKey;
  detail: TieredLevelDetail | null;
  failures: TieredReviewFailure[];
}) => {
  const { t } = useUiLanguage();
  const [isOpen, setIsOpen] = useState(false);

  if (!detail || detail.base === null) {
    return <span className="text-gray-600">—</span>;
  }
  const checkNames = (checks: string[]) =>
    checks
      .map((check) => {
        const keywordKey = CHECK_KEYWORD_KEYS[check];
        return keywordKey ? t(keywordKey) : check;
      })
      .join(', ');
  return (
    <>
      <button
        type="button"
        data-testid={`level-keepfail-${columnKey}`}
        onClick={() => setIsOpen(true)}
        className={cn('cursor-pointer', ALT_LINK)}
      >
        {t('tiered.levels.keep')}
      </button>
      <Modal
        isOpen={isOpen}
        title={t('tiered.reviewFail.title')}
        onClose={() => setIsOpen(false)}
      >
        <div className={MODAL_BODY}>
          <p>{t('tiered.reviewFail.intro')}</p>
          <ul className="flex list-disc flex-col gap-2 pl-4" data-testid="review-failures">
            {failures.map((failure, index) => (
              <li key={index}>
                {t('tiered.reviewFail.round', {
                  round: String(failure.round),
                  checks: checkNames(failure.checks),
                })}
              </li>
            ))}
          </ul>
        </div>
      </Modal>
    </>
  );
};

// ---------- the shares column (plan-review redesign, 2026-07-22) ----------

// A number that scroll-flashes the element it came from (run-row inputs,
// plan-table cells); plain text when there is nothing to point at.
const FlashNum = ({ targetId, text }: { targetId: string | null; text: string }) =>
  targetId ? (
    <button
      type="button"
      className={cn('cursor-pointer tabular-nums', ALT_LINK)}
      onClick={() => flashElement(targetId)}
    >
      {text}
    </button>
  ) : (
    <span className="tabular-nums text-gray-300">{text}</span>
  );

// The share-count arithmetic, in the same three-line receipt shape as the
// level formulas: words, this run's numbers (each linking to where it
// already appears), result.
const SharesReceipt = ({
  inputs,
  shares,
  runId,
  entryTargetId,
  stopTargetId,
}: {
  inputs: Record<string, number>;
  shares: number;
  runId?: string;
  entryTargetId: string | null;
  stopTargetId: string | null;
}) => {
  const { t } = useUiLanguage();
  const capital = inputs.capital;
  const risk = inputs.risk_pct;
  const entry = inputs.entry;
  const stop = inputs.stop_loss;
  return (
    <div className="flex flex-col gap-2 overflow-x-auto text-sm" data-testid="shares-receipt">
      <p className={FORMULA_LINE}>
        <FVar>{t('tiered.f.capital')}</FVar> × <FVar>{t('tiered.f.risk')}</FVar>
        {' / ('}
        <FVar>{t('tiered.f.entry')}</FVar> − <FVar>{t('tiered.f.stop')}</FVar>
        {')'}
      </p>
      <p className={FORMULA_LINE}>
        {'= '}
        <FlashNum
          targetId={runId ? `run-${runId}-capital` : null}
          text={capital != null ? plainNumber(capital) : '—'}
        />
        {' × '}
        <FlashNum
          targetId={runId ? `run-${runId}-risk` : null}
          text={risk != null ? `${riskPctText(risk)}%` : '—'}
        />
        {' / ('}
        <FlashNum targetId={entryTargetId} text={formatPrice(entry ?? null)} />
        {' − '}
        <FlashNum targetId={stopTargetId} text={formatPrice(stop ?? null)} />
        {')'}
      </p>
      <p className={FORMULA_RESULT}>= {t('tiered.history.shares', { value: shares })}</p>
    </div>
  );
};

interface SharesCellProps {
  detail: TieredLevelDetail | null;
  runId?: string;
  /** Whether entry / stop carry an accepted adjustment (links target). */
  levelAdjusted: (key: LevelKey) => boolean;
}

// The computed share count — clicking it opens the arithmetic receipt.
const SharesComputedCell = ({ detail, runId }: Omit<SharesCellProps, 'levelAdjusted'>) => {
  const { t } = useUiLanguage();
  const [isOpen, setIsOpen] = useState(false);

  if (!detail || detail.base === null) {
    return <span className="text-gray-600">—</span>;
  }
  return (
    <>
      <button
        type="button"
        id={computedCellId('shares')}
        data-testid="level-computed-shares"
        onClick={() => setIsOpen(true)}
        className={cn('cursor-pointer tabular-nums', ALT_LINK)}
      >
        {detail.base}
      </button>
      <Modal
        isOpen={isOpen}
        title={
          <ModalTitle
            subject={t('tiered.levels.shares')}
            kind={t('tiered.kind.formula')}
          />
        }
        onClose={() => setIsOpen(false)}
        panelClassName="w-fit min-w-72 max-w-[95vw]"
      >
        <SharesReceipt
          inputs={detail.inputs ?? {}}
          shares={detail.base}
          runId={runId}
          entryTargetId={computedCellId('entry')}
          stopTargetId={computedCellId('stop_loss')}
        />
      </Modal>
    </>
  );
};

// The adjusted share count: an AI trim opens its cited reason; a purely
// mechanical recompute (a level moved, so the count followed) opens the
// same receipt with the final levels plugged in.
const SharesAdjustedCell = ({ detail, runId, levelAdjusted }: SharesCellProps) => {
  const { t } = useUiLanguage();
  const [isOpen, setIsOpen] = useState(false);

  if (!detail || detail.base === null) {
    return <span className="text-gray-600">—</span>;
  }
  if (detail.adjusted === null) {
    return (
      <span data-testid="level-keep-shares" className="text-gray-500">
        {t('tiered.levels.keep')}
      </span>
    );
  }
  const levelTarget = (key: LevelKey): string =>
    levelAdjusted(key) ? adjustedCellId(key) : computedCellId(key);
  return (
    <>
      <button
        type="button"
        id={adjustedCellId('shares')}
        data-testid="level-adjusted-shares"
        onClick={() => setIsOpen(true)}
        className={cn('cursor-pointer tabular-nums', ALT_LINK)}
      >
        {detail.adjusted}
      </button>
      <Modal
        isOpen={isOpen}
        title={
          <ModalTitle
            subject={t('tiered.levels.shares')}
            kind={t('tiered.kind.adjustment')}
          />
        }
        onClose={() => setIsOpen(false)}
        panelClassName="w-fit min-w-72 max-w-[95vw]"
      >
        <div className={MODAL_BODY}>
          {/* Bullet 1 is always the mechanical recompute from the adjusted
              levels — the AI trim's reasons follow (owner, 2026-07-22). */}
          <AdjustReasonList
            reasons={detail.reasons ?? []}
            leading={
              detail.adjusted_inputs ? (
                <SharesReceipt
                  inputs={detail.adjusted_inputs}
                  shares={detail.mechanical ?? detail.adjusted}
                  runId={runId}
                  entryTargetId={levelTarget('entry')}
                  stopTargetId={levelTarget('stop_loss')}
                />
              ) : undefined
            }
          />
        </div>
      </Modal>
    </>
  );
};

// ---------- the warnings row ----------
// Rendering lives in PlanWarnings.tsx: keyword-first sentences whose
// every value is clickable (report rows, plan cells, formula popups).

interface LevelsProps {
  levels: TieredLevels;
  levelsDetail: TieredLevelsDetail | null | undefined;
  /** Plan-review warnings per column. */
  planWarnings?: TieredPlanWarnings | null;
  /** The run's task id — lets the shares receipt link the run-row inputs. */
  runId?: string;
}

const CELL = 'py-1.5 pr-4 text-sm';
const ROW_LABEL = 'py-1.5 pr-4 text-xs text-gray-500';

// The trade plan as a computed/adjusted table — the three price levels
// plus the share count, with the AI's validated adjustments beneath the
// formula bases and a warnings row underneath. A run whose levels could
// not be computed carries no audit trail and falls back to a single row.
export const TradePlan = ({
  levels,
  levelsDetail,
  planWarnings,
  runId,
}: LevelsProps) => {
  const { t } = useUiLanguage();
  const details = levelsDetail?.levels ?? null;
  const sharesDetail = details?.shares ?? null;
  const reviewFailures = levelsDetail?.review_failures ?? [];
  const levelAdjusted = (key: LevelKey): boolean =>
    (details?.[key]?.adjusted ?? null) !== null;
  // Where a warning value pointing at a plan column should flash: the
  // adjusted cell when an adjustment exists, else the computed cell.
  const cellTarget = (key: ColumnKey): string => {
    const isAdjusted =
      key === 'shares' ? (sharesDetail?.adjusted ?? null) !== null : levelAdjusted(key);
    return isAdjusted ? adjustedCellId(key) : computedCellId(key);
  };

  const headerCells: ReactNode = (
    <tr>
      <th className="pb-1.5 pr-4" />
      {COLUMNS.map((key) => (
        <th key={key} className="pb-1.5 pr-4 text-left text-xs font-semibold text-gray-500">
          <HelpTerm label={t(LEVEL_LABEL_KEYS[key])} helpKey={LEVEL_HELP_KEYS[key]} />
        </th>
      ))}
    </tr>
  );

  return (
    <div className="overflow-x-auto" data-testid="levels-table">
      <table className="w-full">
        <thead>{headerCells}</thead>
        <tbody>
          {details ? (
            <>
              <tr>
                <td className={ROW_LABEL}>{t('tiered.levels.computed')}</td>
                {LEVEL_ORDER.map((key) => (
                  <td key={key} className={CELL}>
                    <ComputedCell
                      levelKey={key}
                      detail={details[key] ?? null}
                      label={t(LEVEL_LABEL_KEYS[key])}
                    />
                  </td>
                ))}
                <td className={CELL}>
                  <SharesComputedCell detail={sharesDetail} runId={runId} />
                </td>
              </tr>
              <tr>
                <td className={ROW_LABEL}>{t('tiered.levels.adjusted')}</td>
                {reviewFailures.length > 0 ? (
                  COLUMNS.map((key) => (
                    <td key={key} className={CELL}>
                      <KeepFailedCell
                        columnKey={key}
                        detail={(key === 'shares' ? sharesDetail : details[key]) ?? null}
                        failures={reviewFailures}
                      />
                    </td>
                  ))
                ) : (
                  <>
                    {LEVEL_ORDER.map((key) => (
                      <td key={key} className={CELL}>
                        <AdjustedCell
                          levelKey={key}
                          detail={details[key] ?? null}
                          label={t(LEVEL_LABEL_KEYS[key])}
                        />
                      </td>
                    ))}
                    <td className={CELL}>
                      <SharesAdjustedCell
                        detail={sharesDetail}
                        runId={runId}
                        levelAdjusted={levelAdjusted}
                      />
                    </td>
                  </>
                )}
              </tr>
              {planWarnings ? (
                <tr>
                  <td className={ROW_LABEL}>{t('tiered.levels.warnings')}</td>
                  {COLUMNS.map((key) => (
                    <td key={key} className={CELL}>
                      <WarningsCell
                        column={key}
                        warnings={planWarnings[key] ?? []}
                        label={t(LEVEL_LABEL_KEYS[key])}
                        runId={runId}
                        cellTarget={cellTarget}
                      />
                    </td>
                  ))}
                </tr>
              ) : null}
            </>
          ) : (
            <tr>
              <td className={ROW_LABEL} />
              {LEVEL_ORDER.map((key) => (
                <td key={key} className={cn(CELL, 'tabular-nums text-gray-300')}>
                  {formatPrice(levels[key])}
                </td>
              ))}
              <td className={cn(CELL, 'text-gray-600')}>—</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
};
