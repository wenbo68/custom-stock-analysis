import { Card } from './Ui';

// A placeholder bar in a skeleton card: the same gray as the page's
// deepest surface, pulsing while motion is allowed.
const Bar = ({ className }: { className: string }) => (
  <span aria-hidden="true" className={`block rounded bg-surface-3 ${className}`} />
);

// One label-and-value row of a numeric card, as the metric rows sit.
const MetricRowBars = ({ labelWidth }: { labelWidth: string }) => (
  <span className="flex items-center justify-between gap-4 py-1">
    <Bar className={`h-3 ${labelWidth}`} />
    <Bar className="h-3 w-12" />
  </span>
);

interface SkeletonCardProps {
  /** The card's name when the step is known; a bar stands in otherwise. */
  title?: string | null;
  /** Names the card for tests and assistive tech: `skeleton-<stage>`. */
  testId: string;
  /** Two for the numeric data reports, whose metric rows sit in two columns; one for every other card. */
  columns?: 1 | 2;
}

// The card being worked on in a running run (owner request 2026-10-19):
// the card's shape — title row, then lines of unequal length, or the
// numeric cards' two columns of metric rows — with nothing in it yet.
// It takes the place the finished card will fill, so the report grows
// in place rather than under a progress line.
export const SkeletonCard = ({ title, testId, columns = 1 }: SkeletonCardProps) => (
  <Card testId={testId} className="motion-safe:animate-pulse" busy>
    <div className="mb-4">
      {title ? (
        <h3 className="min-w-0 truncate font-semibold text-ink-4">{title}</h3>
      ) : (
        <Bar className="h-4 w-28" />
      )}
    </div>
    {columns === 2 ? (
      <div data-testid={`${testId}-columns`}>
        <Bar className="mb-2 h-2.5 w-16" />
        <div className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
          <MetricRowBars labelWidth="w-24" />
          <MetricRowBars labelWidth="w-20" />
          <MetricRowBars labelWidth="w-28" />
          <MetricRowBars labelWidth="w-16" />
          <MetricRowBars labelWidth="w-20" />
          <MetricRowBars labelWidth="w-24" />
        </div>
      </div>
    ) : (
      <div className="flex flex-col gap-2.5">
        <Bar className="h-3 w-11/12" />
        <Bar className="h-3 w-4/5" />
        <Bar className="h-3 w-2/3" />
      </div>
    )}
  </Card>
);
