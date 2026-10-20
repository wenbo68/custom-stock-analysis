import { useEffect } from 'react';
import { Bot, Hand, SlidersHorizontal } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import { getSessionStorage, readStoredValue, writeStoredValue } from '../../utils/storedValue';
import type { Choice } from '../common/choice';

// The two ways to use the app, each a page: the manual analysis page
// and the agent that drives it.
export type ModePath = '/' | '/chat';

const MODE_OPTIONS: Array<{ value: ModePath; labelKey: UiTextKey; icon: typeof Hand }> = [
  { value: '/', labelKey: 'mode.manual', icon: Hand },
  { value: '/chat', labelKey: 'mode.agentic', icon: Bot },
];

const isChatPath = (pathname: string): boolean => pathname.startsWith('/chat');

const activeMode = (pathname: string): ModePath => (isChatPath(pathname) ? '/chat' : '/');

/** Where the tab keeps the chat URL it last showed (sessionStorage). */
export const CHAT_PATH_STORAGE_KEY = 'chat.path';

// The chat URL the switch returns to: the one with the conversation
// the user was in, kept by this tab (owner request 2026-10-20). Before
// that, the open conversation rode only in the URL, so going manual and
// back always landed on a new, empty conversation. A path from storage
// is trusted only if it is a chat path, else a bad value would move
// the user elsewhere.
const chatPathToReturnTo = (): string => {
  const stored = readStoredValue(getSessionStorage(), CHAT_PATH_STORAGE_KEY);
  return stored && isChatPath(stored) ? stored : '/chat';
};

// The mode (owner request 2026-09-26): one "Mode" setting in place of
// the two page links, offering manual and agentic; picking the other
// one opens that page.
export function useModeChoice(): Choice<ModePath> {
  const { t } = useUiLanguage();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const value = activeMode(pathname);

  // Every chat URL shown is remembered as it is shown, the empty page's
  // included: a "new conversation" started there is where the user was.
  useEffect(() => {
    if (isChatPath(pathname)) {
      writeStoredValue(getSessionStorage(), CHAT_PATH_STORAGE_KEY, pathname);
    }
  }, [pathname]);

  return {
    icon: SlidersHorizontal,
    label: t('mode.mode'),
    triggerLabel: t('mode.toggle'),
    menuLabel: t('mode.menu'),
    options: MODE_OPTIONS.map(({ value: path, labelKey, icon }) => ({ value: path, label: t(labelKey), icon })),
    value,
    onSelect: (path) => {
      if (path !== value) {
        void navigate(path === '/chat' ? chatPathToReturnTo() : path);
      }
    },
  };
}
