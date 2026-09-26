import { useState, type ReactNode } from 'react';
import { Play } from 'lucide-react';
import type { TieredTier, TieredDuplicateRun, TieredMarketOpenGate } from '../../api/tiered';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import { HelpTerm } from '../tiered/terms';
import { tickerCurrency } from './currency';
import { Pill, PillRow, Select } from './Fields';
import { ALT_COLOR } from './styles';
import { Modal, SectionLabel, MODAL_BODY } from './Ui';

// Tier 3 retired (outlook redesign) — the picker offers 1 and 2 only.
const TIERS: TieredTier[] = [1, 2];

// Dropdown suggestions only — any ticker can still be typed and entered.
const TICKER_IDEAS = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', '600519', 'hk00700'];
const CAPITAL_IDEAS = ['10000', '50000', '100000', '200000', '500000', '1000000'];
const RISK_IDEAS = ['0.5', '1', '2'];
// Reward-to-risk ratio the plan aims for; '2' is the default.
const REWARD_RATIO_IDEAS = ['1.5', '2', '3'];

// Max maxHoldWeeks time choices in weeks (owner decision 2026-08-08): the
// horizon the AI judges against and the forward test grades at.
const MAX_HOLD_WEEKS = ['1', '2', '3', '4'];

// Field colors are positional in the showplayer palette (ALT_COLOR order,
// starting at red): pill N wears color N, and Start wears the next slot.
const TONE = {
  ticker: ALT_COLOR[1],
  capital: ALT_COLOR[2],
  risk: ALT_COLOR[3],
  rewardRatio: ALT_COLOR[4],
  maxHoldWeeks: ALT_COLOR[5],
  tier: ALT_COLOR[6],
};

// The Start control is a pill like its neighbors, in the next palette slot.
const START_PILL = `inline-flex cursor-pointer items-center gap-1.5 rounded px-[9px] py-0.5 text-xs font-semibold ring-1 ring-inset transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50 ${ALT_COLOR[7]}`;

const isPositiveNumber = (raw: string): boolean => {
  const value = Number(raw);
  return Number.isFinite(value) && value > 0;
};

const isRiskPct = (raw: string): boolean => {
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 && value < 100;
};

// Reward-to-risk ratio: above 1 (or the trade can't pay for its risk),
// capped at 10 to keep typos out.
const isRewardRatio = (raw: string): boolean => {
  const value = Number(raw);
  return Number.isFinite(value) && value > 1 && value <= 10;
};

// The gate's session bounds are ISO strings whose UTC offset IS the
// market's — so the market-local clock time is read straight off the
// string (parsing would convert it to the browser's zone)…
const marketClock = (iso: string): string => iso.slice(11, 16);
// …and the user-local time comes from letting Date do that conversion.
const localClock = (iso: string): string =>
  new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });

interface Notice {
  title: string;
  body: ReactNode;
}

export interface RunFormProps {
  ticker: string | null;
  tier: TieredTier | null;
  capital: string | null;
  riskPct: string | null;
  rewardRatio: string | null;
  maxHoldWeeks: string | null;
  submitting: boolean;
  error: string | null;
  /** Clock gate: the backend rejected the start because the ticker's
   *  market is open — non-null shows the popup (market + session hours
   *  + the "run anyway" choice). */
  gate: TieredMarketOpenGate | null;
  /** Duplicate run: the backend refused the start because an unfinished
   *  run has the same ticker and inputs — non-null shows it in the
   *  Error popup. */
  duplicate: TieredDuplicateRun | null;
  onTicker: (value: string | null) => void;
  onTier: (value: TieredTier | null) => void;
  onCapital: (value: string | null) => void;
  onRiskPct: (value: string | null) => void;
  onRewardRatio: (value: string | null) => void;
  onMaxHoldWeeks: (value: string | null) => void;
  onStart: () => void;
  onRunAnyway: () => void;
  onGateClose: () => void;
  onDuplicateClose: () => void;
}

// Section 1: the new-run form. Fields are write-only — every choice lands
// as a removable pill below; the Start pill launches the run only when
// every field is picked (a popup explains otherwise). All five fields are
// required; rewardRatio (the reward-to-risk ratio) defaults to 2.
// Capital is in the ticker's own trading currency, so it can't be picked
// before the ticker. Picking an already-picked dropdown option clears it,
// same as clicking its pill.
export const RunForm = ({
  ticker,
  tier,
  capital,
  riskPct,
  rewardRatio,
  maxHoldWeeks,
  submitting,
  error,
  gate,
  duplicate,
  onTicker,
  onTier,
  onCapital,
  onRiskPct,
  onRewardRatio,
  onMaxHoldWeeks,
  onStart,
  onRunAnyway,
  onGateClose,
  onDuplicateClose,
}: RunFormProps) => {
  const { t } = useUiLanguage();
  // A popup: "Heads up" for advice the user may ignore, "Error" for what
  // stops the run (setError).
  const [notice, setNotice] = useState<Notice | null>(null);
  const setHeadsUp = (body: ReactNode) => setNotice({ title: t('tiered.form.noticeTitle'), body });
  const setError = (body: ReactNode) => setNotice({ title: t('tiered.form.errorTitle'), body });
  // The duplicate refusal from the backend shows in the same Error popup
  // as the form's own checks; it is derived from the prop, so closing
  // the popup tells the page to drop it.
  const shownNotice: Notice | null =
    notice ??
    (duplicate
      ? {
          title: t('tiered.form.errorTitle'),
          body: (
            <p>
              {t(
                duplicate.status === 'running'
                  ? 'tiered.form.duplicateRunning'
                  : 'tiered.form.duplicateQueued',
                { ticker: ticker ?? '' },
              )}
            </p>
          ),
        }
      : null);
  const closeNotice = () => {
    setNotice(null);
    if (duplicate) {
      onDuplicateClose();
    }
  };

  const currency = ticker ? tickerCurrency(ticker) : null;

  // Market display name for the gate popup ("US", "美股", …) — the same
  // names the decision-signals page uses; the raw code is the fallback
  // for a market with no translation.
  const gateMarketName = gate?.market
    ? t(`tiered.form.market.${gate.market}` as UiTextKey)
    : '';
  const gateHasHours = Boolean(gate?.sessionOpen && gate?.sessionClose);

  const commitCapital = (value: string) => {
    if (!ticker) {
      setHeadsUp(t('tiered.form.needTickerFirst'));
      return;
    }
    onCapital(value === capital ? null : value);
  };

  const handleStart = () => {
    // The missing fields, in on-screen order.
    const fields: ReadonlyArray<readonly [unknown, UiTextKey]> = [
      [ticker, 'tiered.form.req.ticker'],
      [capital, 'tiered.form.req.capital'],
      [riskPct, 'tiered.form.req.risk'],
      [rewardRatio, 'tiered.form.req.reward'],
      [maxHoldWeeks, 'tiered.form.req.hold'],
      [tier !== null, 'tiered.form.req.tier'],
    ];
    const missing = fields.filter(([filled]) => !filled).map(([, key]) => t(key));
    if (missing.length > 0) {
      setError(
        <>
          <p>{t('tiered.form.missingIntro')}</p>
          <div>
            <SectionLabel>{t('tiered.form.title')}</SectionLabel>
            <ul className="list-disc pl-5">
              {missing.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          </div>
        </>,
      );
      return;
    }
    onStart();
  };

  return (
    <div className="flex w-full flex-col gap-4">
      <div className="grid w-full grid-cols-2 gap-2 text-sm sm:grid-cols-6 sm:gap-3 md:gap-4">
        <Select
          label={t('tiered.form.ticker')}
          tone={ticker ? TONE.ticker : undefined}
          options={TICKER_IDEAS.map((value) => ({ value, label: value }))}
          selected={ticker ? [ticker] : undefined}
          placeholder={t('tiered.form.tickerPh')}
          freeText
          onCommit={(value) => onTicker(value === ticker ? null : value)}
        />
        <Select
          label={
            <HelpTerm
              label={
                currency
                  ? t('tiered.form.capitalCurrency', { currency })
                  : t('tiered.form.capital')
              }
              helpKey="tiered.help.capital"
              underline={false}
            />
          }
          tone={capital ? TONE.capital : undefined}
          options={CAPITAL_IDEAS.map((value) => ({ value, label: value }))}
          selected={capital ? [capital] : undefined}
          placeholder={t('tiered.form.capitalPh')}
          inputMode="decimal"
          freeText
          validate={isPositiveNumber}
          onCommit={commitCapital}
        />
        <Select
          label={
            <HelpTerm
              label={t('tiered.form.risk')}
              helpKey="tiered.help.riskPct"
              underline={false}
            />
          }
          tone={riskPct ? TONE.risk : undefined}
          options={RISK_IDEAS.map((value) => ({ value, label: value }))}
          selected={riskPct ? [riskPct] : undefined}
          placeholder={t('tiered.form.riskPh')}
          inputMode="decimal"
          freeText
          validate={isRiskPct}
          onCommit={(value) => onRiskPct(value === riskPct ? null : value)}
        />
        <Select
          label={
            <HelpTerm
              label={t('tiered.form.reward')}
              helpKey="tiered.help.reward"
              underline={false}
            />
          }
          tone={rewardRatio ? TONE.rewardRatio : undefined}
          options={REWARD_RATIO_IDEAS.map((value) => ({ value, label: value }))}
          selected={rewardRatio ? [rewardRatio] : undefined}
          placeholder={t('tiered.form.rewardPh')}
          inputMode="decimal"
          freeText
          validate={isRewardRatio}
          onCommit={(value) => {
            // Below 1.5× the trade barely pays for its risk — warn (a
            // popup), but honor the choice: the run still goes ahead.
            if (value !== rewardRatio && Number(value) < 1.5) {
              setHeadsUp(t('tiered.form.lowRewardWarn', { value }));
            }
            onRewardRatio(value === rewardRatio ? null : value);
          }}
        />
        <Select
          label={
            <HelpTerm
              label={t('tiered.form.hold')}
              helpKey="tiered.help.hold"
              underline={false}
            />
          }
          tone={maxHoldWeeks ? TONE.maxHoldWeeks : undefined}
          options={MAX_HOLD_WEEKS.map((value) => ({ value, label: value }))}
          selected={maxHoldWeeks ? [maxHoldWeeks] : undefined}
          placeholder={t('tiered.form.holdPh')}
          onCommit={(value) => onMaxHoldWeeks(value === maxHoldWeeks ? null : value)}
        />
        <Select
          label={
            <HelpTerm label={t('tiered.form.tier')} helpKey="tiered.help.tier" underline={false} />
          }
          tone={tier !== null ? TONE.tier : undefined}
          options={TIERS.map((value) => ({
            value: String(value),
            label: t(`tiered.form.tierOption${value}` as UiTextKey),
          }))}
          selected={tier !== null ? [String(tier)] : undefined}
          placeholder={t('tiered.form.tierPh')}
          onCommit={(value) =>
            onTier(Number(value) === tier ? null : (Number(value) as TieredTier))
          }
        />
      </div>

      <PillRow>
        {ticker ? (
          <Pill tone={TONE.ticker} onRemove={() => onTicker(null)}>
            {t('tiered.pill.ticker', { value: ticker })}
          </Pill>
        ) : null}
        {capital ? (
          <Pill tone={TONE.capital} onRemove={() => onCapital(null)}>
            {t('tiered.pill.capital', { value: capital, currency: currency ?? '' }).trim()}
          </Pill>
        ) : null}
        {riskPct ? (
          <Pill tone={TONE.risk} onRemove={() => onRiskPct(null)}>
            {t('tiered.pill.risk', { value: riskPct })}
          </Pill>
        ) : null}
        {rewardRatio ? (
          <Pill tone={TONE.rewardRatio} onRemove={() => onRewardRatio(null)}>
            {t('tiered.pill.reward', { value: rewardRatio })}
          </Pill>
        ) : null}
        {maxHoldWeeks ? (
          <Pill tone={TONE.maxHoldWeeks} onRemove={() => onMaxHoldWeeks(null)}>
            {t('tiered.pill.hold', { value: maxHoldWeeks })}
          </Pill>
        ) : null}
        {tier !== null ? (
          <Pill tone={TONE.tier} onRemove={() => onTier(null)}>
            {t('tiered.pill.tier', { value: tier })}
          </Pill>
        ) : null}
        <button type="button" onClick={handleStart} disabled={submitting} className={START_PILL}>
          <Play className="h-3 w-3" />
          {t('tiered.form.start')}
        </button>
      </PillRow>

      {error ? <p className="text-sm text-negative">{error}</p> : null}

      <Modal isOpen={shownNotice !== null} title={shownNotice?.title ?? ''} onClose={closeNotice}>
        <div className={MODAL_BODY}>{shownNotice?.body}</div>
      </Modal>

      {/* Clock gate (2026-08-08): the market is open, so the app has no
          completed trading day to analyze yet. "Run anyway" re-submits
          with the override — the run then reads the PREVIOUS session.
          The hours paragraph needs the session bounds in the 409 body,
          so it stays hidden against a backend that predates them. */}
      <Modal
        isOpen={gate !== null}
        title={t('tiered.form.marketOpenTitle')}
        onClose={onGateClose}
      >
        <div className={MODAL_BODY}>
          <p>{t('tiered.form.marketOpenTrading', { market: gateMarketName })}</p>
          {gateHasHours && gate?.sessionOpen && gate.sessionClose ? (
            <p>
              {t('tiered.form.marketOpenHours', {
                open: marketClock(gate.sessionOpen),
                close: marketClock(gate.sessionClose),
                openLocal: localClock(gate.sessionOpen),
                closeLocal: localClock(gate.sessionClose),
              })}
            </p>
          ) : null}
          <p>{t('tiered.form.marketOpenMixedData')}</p>
          <p>{t('tiered.form.marketOpenBestWindow')}</p>
        </div>
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            className={START_PILL}
            onClick={onRunAnyway}
            disabled={submitting}
          >
            {t('tiered.form.runAnyway')}
          </button>
        </div>
      </Modal>
    </div>
  );
};
