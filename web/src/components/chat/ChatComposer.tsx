import { useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react';
import { ArrowUp, Ellipsis, Square } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { ALT_COLOR } from '../analysis/styles';
import { CHAT_SURFACE_1 } from './chatSurfaces';

export interface ChatComposerProps {
  /** Nothing can be sent right now: a turn is running or a question waits. */
  disabled: boolean;
  /** Why, shown under the box when disabled. */
  disabledHint?: string | null;
  /** A turn is in flight: the send arrow becomes a stop button. */
  working?: boolean;
  /** The stop was asked and the turn has not yet come back: the server
   *  lets the step in flight finish first, so this can take a while, and
   *  the stop button gives way to an unclickable "…" meanwhile. */
  stopping?: boolean;
  onSend: (text: string) => void;
  onStop?: () => void;
}

const ROUND_BUTTON = 'inline-flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-full ring-1 ring-inset transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50';
const SEND_BUTTON = `${ROUND_BUTTON} ${ALT_COLOR[7]}`;
/** The stop button: the same round button in the outlook palette's red, so it reads as "stop", not "send". */
const STOP_BUTTON = `${ROUND_BUTTON} ${ALT_COLOR[1]}`;
/** The "…" that stands in for the stop button once clicked: the same shape, muted, never clickable. */
const STOPPING_BUTTON = `${ROUND_BUTTON} ring-ink-5 text-ink-4`;
/** The box grows with the text up to this many lines, then scrolls. */
export const MAX_ROWS = 6;
/** The width the send arrow takes beside a one-line draft: h-7 (28px) plus gap-3 (12px). */
const ARROW_LANE_PX = 40;

interface Measured {
  /** Lines the draft takes at the width it will render at. */
  lines: number;
  /** The draft would not fit on one line beside the arrow, so the arrow takes its own row. */
  needsOwnRow: boolean;
}

// Measure how many lines the draft takes: the taller of the newline count
// and the rendered height, which also counts lines that wrapped because the
// text ran out of width. The "beside the arrow" question is always asked at
// the narrower width the box has in the one-row layout, whichever layout is
// showing now, so the answer never flips back and forth as the layout
// changes. In a test DOM nothing is laid out, so the line height reads as
// missing and the newline count stands alone.
const measureDraft = (box: HTMLTextAreaElement, draft: string): Measured => {
  const newlineRows = draft.split('\n').length;
  const lineHeight = parseFloat(getComputedStyle(box).lineHeight);
  const lane = box.parentElement;
  if (!(lineHeight > 0) || !lane) {
    return { lines: newlineRows, needsOwnRow: newlineRows > 1 };
  }
  const laneStyle = getComputedStyle(lane);
  const laneWidth = lane.clientWidth - parseFloat(laneStyle.paddingLeft) - parseFloat(laneStyle.paddingRight);
  // Take the box out of the flex sizing while measuring so the forced
  // width holds; a flex item ignores its own width and height otherwise.
  box.style.flex = 'none';
  const linesAtWidth = (width: number) => {
    box.style.width = `${width}px`;
    // Collapse first so a deleted line shrinks the box; scrollHeight then
    // reports the full height of the current text.
    box.style.height = 'auto';
    return Math.max(newlineRows, Math.round(box.scrollHeight / lineHeight));
  };
  const linesBesideArrow = linesAtWidth(laneWidth - ARROW_LANE_PX);
  const needsOwnRow = linesBesideArrow > 1;
  const lines = needsOwnRow ? linesAtWidth(laneWidth) : linesBesideArrow;
  box.style.width = '';
  box.style.flex = '';
  box.style.height = `${Math.min(MAX_ROWS, lines) * lineHeight}px`;
  box.style.overflowY = lines > MAX_ROWS ? 'auto' : 'hidden';
  return { lines, needsOwnRow };
};

// The message box: Enter sends, Shift+Enter breaks a line, and the box
// grows upward with the text up to MAX_ROWS lines, then scrolls. The send
// arrow sits beside a one-line draft; once the text needs a second line
// (typed or wrapped) the arrow drops to its own row so text never runs
// into it. The draft stays when a send fails so nothing typed is lost.
// While a turn runs the arrow is a stop button in its place (owner
// request 2026-10-12, after Claude Code's Esc): one click asks the
// server to stop, and the button stays, disabled, until the turn comes
// back stopped.
export const ChatComposer = ({ disabled, disabledHint, working = false, stopping = false, onSend, onStop }: ChatComposerProps) => {
  const { t } = useUiLanguage();
  const [draft, setDraft] = useState('');
  const [isMultiline, setMultiline] = useState(false);
  const boxRef = useRef<HTMLTextAreaElement>(null);
  const canSend = !disabled && draft.trim().length > 0;

  useLayoutEffect(() => {
    if (boxRef.current) {
      setMultiline(measureDraft(boxRef.current, draft).needsOwnRow);
    }
  }, [draft]);

  const send = () => {
    if (!canSend) {
      return;
    }
    onSend(draft.trim());
    setDraft('');
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  };

  const rows = Math.min(MAX_ROWS, Math.max(1, draft.split('\n').length));

  return (
    <div className="flex flex-col gap-2">
      <div
        data-testid="chat-composer"
        data-multiline={isMultiline ? 'true' : 'false'}
        className={cn('flex gap-3 rounded px-4 py-3', CHAT_SURFACE_1, isMultiline ? 'flex-col' : 'flex-row items-end')}
      >
        <textarea
          ref={boxRef}
          data-testid="chat-input"
          value={draft}
          rows={rows}
          disabled={disabled}
          placeholder={t('chat.composer.placeholder')}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          className={cn(
            'min-h-[1.5rem] w-full resize-none bg-transparent text-sm leading-relaxed text-ink-1 outline-none placeholder:text-ink-5',
            // Beside the arrow the box takes the rest of the row; on its own
            // row it must not be a growing flex item, or the browser sizes
            // it from `rows` and ignores the measured height.
            !isMultiline && 'flex-1',
            disabled && 'opacity-60',
          )}
        />
        {working && stopping ? (
          <button
            type="button"
            data-testid="chat-stopping"
            disabled
            aria-label={t('chat.composer.stopping')}
            title={t('chat.composer.stopping')}
            className={cn(STOPPING_BUTTON, isMultiline && 'self-end')}
          >
            <Ellipsis className="h-4 w-4 animate-pulse" />
          </button>
        ) : working ? (
          <button
            type="button"
            data-testid="chat-stop"
            disabled={onStop == null}
            onClick={onStop}
            aria-label={t('chat.composer.stop')}
            title={t('chat.composer.stop')}
            className={cn(STOP_BUTTON, isMultiline && 'self-end')}
          >
            <Square className="h-3 w-3 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            data-testid="chat-send"
            disabled={!canSend}
            onClick={send}
            aria-label={t('chat.composer.send')}
            title={t('chat.composer.send')}
            className={cn(SEND_BUTTON, isMultiline && 'self-end')}
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        )}
      </div>
      {disabled && disabledHint ? <p className="text-xs text-ink-4">{disabledHint}</p> : null}
    </div>
  );
};
