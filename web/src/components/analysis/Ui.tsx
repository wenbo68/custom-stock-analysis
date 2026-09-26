import { useEffect, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { CircleAlert } from 'lucide-react';
import type { TieredCitation } from '../../api/tiered';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { jumpToMetric } from '../tiered/termHelpers';
import { ALT_LINK } from './styles';
import { friendlyWarning } from './warningText';

interface CardProps {
  children: ReactNode;
  className?: string;
  testId?: string;
}

// The only surface on the alt page: flat gray-800, small radius, no border,
// no shadow — separation comes from the gray-900 canvas and whitespace.
export const Card = ({ children, className, testId }: CardProps) => (
  <section data-testid={testId} className={cn('rounded bg-surface-2 p-5', className)}>
    {children}
  </section>
);

interface ModalProps {
  isOpen: boolean;
  /** Omit for a title-less popup (the data-notes modal). */
  title?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  /** Overrides the panel's width classes (e.g. fit-to-content for formulas). */
  panelClassName?: string;
}

// A formula variable: italic, so words read as placeholders and numbers
// (plain or linked) read as values — no underscores, no parentheses.
export const FVar = ({ children }: { children: ReactNode }) => <i>{children}</i>;

// One typography contract for EVERY popup body on the alt page (owner
// decision 2026-07-21): same font size, spacing, colors and divider in
// every modal — body text gray-300, emphasized lines gray-200 semibold.
export const MODAL_BODY = 'flex flex-col gap-2 text-sm leading-relaxed text-ink-2';
export const MODAL_STRONG = 'font-semibold text-ink-1';
export const ModalDivider = () => <hr className="border-border/60" />;

export const SectionLabel = ({ children }: { children: ReactNode }) => (
  <div className="mb-1 text-xs font-semibold text-ink-4">{children}</div>
);

// Every popup title on the alt page names two things: WHAT the popup is
// about (a metric, a plan level, a check) and WHICH KIND of popup it is
// (formula / adjustment / warnings / why blank / an outlook). They used to
// run together as one "subject: kind" sentence, which read as a single
// long label. Owner request 2026-08-08: split them, and always onto TWO
// LINES — subject first, kind under it — so the shape of the header is
// identical in every popup no matter how long either part is. The subject
// keeps the panel's largest, brightest type; the kind sits below as a
// small tracked uppercase tag in the muted body gray. Hierarchy by scale
// and score, no new accent color competing with the amber note mark.
export const ModalTitle = ({ subject, kind }: { subject: ReactNode; kind: ReactNode }) => (
  <span className="flex flex-col gap-0.5">
    <span className="text-base font-semibold leading-tight text-ink-1">{subject}</span>
    <span className="text-[11px] font-semibold uppercase leading-tight tracking-[0.14em] text-ink-4">
      {kind}
    </span>
  </span>
);

// A quiet inline fold (deep analysis transcript, scoring breakdown, LLM
// prompt/reply). `className` replaces the default top margin for hosts
// that space their children with a flex gap.
export const Fold = ({
  title,
  children,
  className = 'mt-4',
  onToggle,
}: {
  title: string;
  children: ReactNode;
  className?: string;
  /** Called with the new state each time the fold opens or closes —
   *  a caller can load its content on the first open. */
  onToggle?: (open: boolean) => void;
}) => {
  const [open, setOpen] = useState(false);
  return (
    <details open={open} className={`${className} min-w-0 rounded bg-surface-1/60 px-4 py-3`.trim()}>
      <summary
        className="cursor-pointer text-xs font-semibold text-ink-2"
        onClick={(event) => {
          // Owned by React so every browser (and the test DOM) reports
          // the toggle the same way.
          event.preventDefault();
          const next = !open;
          setOpen(next);
          onToggle?.(next);
        }}
      >
        {title}
      </summary>
      <div className="mt-3 flex min-w-0 flex-col gap-3">{children}</div>
    </details>
  );
};

// A fact line that opens (owner request 2026-09-24): "label: value ▸"
// in exactly the quiet-label / bright-value styling of the fact lines
// around it, with a small triangle after the value instead of the
// browser's own marker at the left. The line itself has no backdrop;
// what it opens sits under it on the fold surface — by default the
// alt page's inset, or whatever `surfaceClassName` the host needs so
// the text stands out from the card it is on. The LLM call card's
// input/output and the tool call card's input/output are these.
export const FactFold = ({
  label,
  value,
  children,
  onToggle,
  testId,
  surfaceClassName = 'bg-surface-1/60',
}: {
  label: string;
  value: string;
  children: ReactNode;
  /** Called with the new state each time the fold opens or closes. */
  onToggle?: (open: boolean) => void;
  /** Lands on the clickable line. */
  testId?: string;
  /** Classes on the opened text's box: its backdrop, and an indent if the host wants one. */
  surfaceClassName?: string;
}) => {
  const [open, setOpen] = useState(false);
  return (
    <details open={open} className="min-w-0">
      <summary
        data-testid={testId}
        aria-expanded={open}
        className="cursor-pointer list-none text-ink-4 [&::-webkit-details-marker]:hidden"
        onClick={(event) => {
          event.preventDefault();
          const next = !open;
          setOpen(next);
          onToggle?.(next);
        }}
      >
        {label}
        {': '}
        <span className="font-semibold text-ink-1">{value}</span>
        <span aria-hidden="true" className="ml-1">
          {open ? '▾' : '▸'}
        </span>
      </summary>
      <div className={cn('mt-2 flex min-w-0 flex-col gap-3 rounded px-4 py-3', surfaceClassName)}>{children}</div>
    </details>
  );
};

// showplayer-style popup: black/50 backdrop, flat gray-800 panel.
export const Modal = ({ isOpen, title, onClose, children, panelClassName }: ModalProps) => {
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          'max-h-[80vh] w-full max-w-lg overflow-y-auto rounded bg-surface-2 p-5 text-sm text-ink-3',
          panelClassName,
        )}
        onClick={(event) => event.stopPropagation()}
      >
        {/* No ✕ button (owner decision 2026-07-24): clicking the backdrop
            or pressing Escape closes every popup. mb-2 matches MODAL_BODY's
            gap-2, so the title-to-body gap equals every other gap in the
            popup (owner report 2026-07-21). Every titled popup gets a
            divider between title and body (owner request 2026-08-09).
            Title-less popups (the data-notes modal) start straight at the
            body — no leftover header spacing. */}
        {title != null ? (
          <>
            <h3 className="mb-2 font-semibold text-ink-2">{title}</h3>
            <hr className="mb-2 border-border/60" />
          </>
        ) : null}
        {children}
      </div>
    </div>,
    document.body,
  );
};

interface NotesButtonProps {
  notes: string[];
}

// The card's only data-quality signal. Nothing to report → no mark at
// all (an exclamation mark opening an empty list reads as a bug, owner
// report 2026-08-09). Something to report → a small amber exclamation
// mark that opens a title-less modal listing each note as "keyword:
// plain-English sentence" (altWarningText.ts) — raw backend text no
// longer shown; unknown shapes keep their raw wording under the generic
// "Warning" keyword. No vote item dots — every entry is its own
// keyword-led line (owner request 2026-08-09). The old coverage grades
// (full/partial/unavailable badges, the red X) are retired 2026-08-19:
// blank fields with their own notes ARE the degradation signal.
export const WarningsButton = ({ notes }: NotesButtonProps) => {
  const { t, language } = useUiLanguage();
  const [isOpen, setIsOpen] = useState(false);

  if (notes.length === 0) {
    return null;
  }
  return (
    <>
      <button
        type="button"
        data-testid="warnings-button"
        aria-label={t('tiered.warnings')}
        onClick={() => setIsOpen(true)}
        className="inline-flex cursor-pointer items-center rounded text-caution hover:text-caution-hover"
      >
        <CircleAlert className="h-4 w-4" />
      </button>
      <Modal isOpen={isOpen} onClose={() => setIsOpen(false)}>
        {/* No title, no explainer line (owner decision 2026-07-24) — the
            amber lives on the trigger icon only. Entries are keyword-led
            lines in the "keyword: sentence" shape. */}
        <ul className={MODAL_BODY}>
          {notes.map((raw, index) => {
            const friendly = friendlyWarning(raw, t, language);
            return (
              <li key={index}>
                <span className={MODAL_STRONG}>{friendly.keyword}: </span>
                {friendly.text}
              </li>
            );
          })}
        </ul>
      </Modal>
    </>
  );
};

const CITATION_MARKER_SPLIT_RE = /(\[\d+\])/g;
const CITATION_MARKER_RE = /^\[(\d+)\]$/;

interface NarrativeProps {
  text: string;
  citations: TieredCitation[];
}

// Narrative text with [n] markers linked to their numbered sources —
// same behavior as the main page, alt colors.
export const SummaryText = ({ text, citations }: NarrativeProps) => (
  <p className="text-sm leading-relaxed">
    {text.split(CITATION_MARKER_SPLIT_RE).map((part, index) => {
      const match = CITATION_MARKER_RE.exec(part);
      const citation = match ? citations[Number(match[1]) - 1] : undefined;
      if (citation?.url) {
        return (
          <a
            key={index}
            href={citation.url}
            target="_blank"
            rel="noreferrer"
            aria-label={citation.title ?? citation.url}
            className={ALT_LINK}
          >
            {part}
          </a>
        );
      }
      return <span key={index}>{part}</span>;
    })}
  </p>
);

interface EvidenceRefsProps {
  refs: string[];
  onNavigate?: () => void;
}

// Evidence references as links: each payload path scrolls to that metric row.
export const EvidenceRefs = ({ refs, onNavigate }: EvidenceRefsProps) => (
  <span className="inline-flex flex-wrap gap-x-2 text-[11px]">
    {refs.map((refPath, index) => (
      <button
        key={index}
        type="button"
        className={cn('cursor-pointer', ALT_LINK)}
        onClick={() => {
          onNavigate?.();
          // Let any open modal unmount before scrolling to the row behind it.
          window.setTimeout(() => jumpToMetric(refPath), 50);
        }}
      >
        {refPath}
      </button>
    ))}
  </span>
);
