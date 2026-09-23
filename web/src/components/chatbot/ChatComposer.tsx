import { useState, type KeyboardEvent } from 'react';
import { SendHorizontal } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { ALT_COLOR } from '../tiered-alt/altStyles';

export interface ChatComposerProps {
  /** Nothing can be sent right now: a turn is running or a question waits. */
  disabled: boolean;
  /** Why, shown under the box when disabled. */
  disabledHint?: string | null;
  onSend: (text: string) => void;
}

const SEND_PILL = `inline-flex cursor-pointer items-center gap-1.5 rounded px-[9px] py-1 text-xs font-semibold ring-1 ring-inset transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50 ${ALT_COLOR[7]}`;
const MAX_ROWS = 8;

// The message box: Enter sends, Shift+Enter breaks a line, and the box
// grows with the text up to a few lines. The draft stays when a send
// fails so nothing typed is lost.
export const ChatComposer = ({ disabled, disabledHint, onSend }: ChatComposerProps) => {
  const { t } = useUiLanguage();
  const [draft, setDraft] = useState('');
  const canSend = !disabled && draft.trim().length > 0;

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
      <div className="flex items-end gap-3 rounded bg-gray-800 px-4 py-3">
        <textarea
          data-testid="chat-input"
          value={draft}
          rows={rows}
          disabled={disabled}
          placeholder={t('chat.composer.placeholder')}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          className={cn(
            'min-h-[1.5rem] flex-1 resize-none bg-transparent text-sm leading-relaxed text-gray-200 outline-none placeholder:text-gray-600',
            disabled && 'opacity-60',
          )}
        />
        <button type="button" data-testid="chat-send" disabled={!canSend} onClick={send} className={SEND_PILL}>
          <SendHorizontal className="h-3 w-3" />
          {t('chat.composer.send')}
        </button>
      </div>
      {disabled && disabledHint ? <p className="text-xs text-gray-500">{disabledHint}</p> : null}
    </div>
  );
};
