import { Bot, Hand, SlidersHorizontal } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import type { Choice } from '../common/choice';

// The two ways to use the app, each a page: the manual analysis page
// and the agent that drives it.
export type ModePath = '/' | '/chat';

const MODE_OPTIONS: Array<{ value: ModePath; labelKey: UiTextKey; icon: typeof Hand }> = [
  { value: '/', labelKey: 'mode.manual', icon: Hand },
  { value: '/chat', labelKey: 'mode.agentic', icon: Bot },
];

const activeMode = (pathname: string): ModePath => (pathname.startsWith('/chat') ? '/chat' : '/');

// The mode (owner request 2026-09-26): one "Mode" setting in place of
// the two page links, offering manual and agentic; picking the other
// one opens that page.
export function useModeChoice(): Choice<ModePath> {
  const { t } = useUiLanguage();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const value = activeMode(pathname);
  return {
    icon: SlidersHorizontal,
    label: t('mode.mode'),
    triggerLabel: t('mode.toggle'),
    menuLabel: t('mode.menu'),
    options: MODE_OPTIONS.map(({ value: path, labelKey, icon }) => ({ value: path, label: t(labelKey), icon })),
    value,
    onSelect: (path) => {
      if (path !== value) {
        void navigate(path);
      }
    },
  };
}
