import type { TieredSummaryStructure } from '../../api/tiered';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import { LinkedClaimV7 } from './VoteTree';

// The deep-analysis report as its fixed outline (owner decision
// 2026-07-24): the group set and order never change run to run —
// summary first, then the four data_reports in report order. The backend
// enforces the shape (StructuredSummaryModel); groups a run left empty
// are skipped, never reordered. Bullets carry the evidence-list link
// contract, so cited values render as jumps to their report row.
const GROUPS: { key: keyof TieredSummaryStructure; labelKey: UiTextKey }[] = [
  { key: 'summary', labelKey: 'tiered.summaryGroup' },
  { key: 'technicals', labelKey: 'tiered.dataReport.technicals' },
  { key: 'fundamentals', labelKey: 'tiered.dataReport.fundamentals' },
  { key: 'positioning', labelKey: 'tiered.dataReport.positioning' },
  { key: 'macro_economy', labelKey: 'tiered.dataReport.macro_economy' },
  { key: 'company_news', labelKey: 'tiered.dataReport.company_news' },
  { key: 'world_news', labelKey: 'tiered.dataReport.world_news' },
];

interface SummaryOutlineProps {
  structure: TieredSummaryStructure;
}

export const SummaryOutline = ({ structure }: SummaryOutlineProps) => {
  const { t } = useUiLanguage();
  return (
    <ul
      data-testid="summary-outline"
      className="flex list-disc flex-col gap-1 pl-4 text-sm leading-relaxed"
    >
      {GROUPS.map(({ key, labelKey }) => {
        const bullets = structure[key] ?? [];
        if (!bullets || bullets.length === 0) {
          return null;
        }
        return (
          <li key={key}>
            <span className="font-semibold text-gray-300">{t(labelKey)}</span>
            <ul className="list-[circle] pl-4">
              {bullets.map((bullet, index) => (
                <li key={index}>
                  <LinkedClaimV7
                    claim={bullet.text}
                    links={bullet.links ?? []}
                    struck={false}
                  />
                  {bullet.children && bullet.children.length > 0 ? (
                    <ul className="list-[square] pl-4 text-gray-400">
                      {bullet.children.map((child, childIndex) => (
                        <li key={childIndex}>
                          <LinkedClaimV7
                            claim={child.text}
                            links={child.links ?? []}
                            struck={false}
                          />
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ul>
  );
};
