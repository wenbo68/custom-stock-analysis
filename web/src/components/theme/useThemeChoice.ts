import { Monitor, Moon, Palette, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import type { Choice } from '../common/choice';

export type ThemeOption = 'light' | 'dark' | 'system';

const THEME_OPTIONS: Array<{ value: ThemeOption; labelKey: UiTextKey; icon: typeof Sun }> = [
  { value: 'light', labelKey: 'theme.light', icon: Sun },
  { value: 'dark', labelKey: 'theme.dark', icon: Moon },
  { value: 'system', labelKey: 'theme.system', icon: Monitor },
];

// The color scheme: light, dark, or the system's choice. Called "Color"
// wherever it is offered (owner request 2026-09-26).
export function useThemeChoice(): Choice<ThemeOption> {
  const { theme, setTheme } = useTheme();
  const { t } = useUiLanguage();
  return {
    icon: Palette,
    label: t('theme.color'),
    triggerLabel: t('theme.toggle'),
    menuLabel: t('theme.menu'),
    options: THEME_OPTIONS.map(({ value, labelKey, icon }) => ({ value, label: t(labelKey), icon })),
    value: (theme as ThemeOption | undefined) ?? 'system',
    onSelect: setTheme,
  };
}
