import { Languages } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiLanguage } from '../../i18n/uiText';
import type { Choice } from '../common/choice';

// Each language is named in itself, so a reader who does not know the
// current language can still find their own.
const LANGUAGE_OPTIONS: Array<{ value: UiLanguage; label: string }> = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
  { value: 'ko', label: '한국어' },
];

// The UI language. Its word names the setting — "语言" / "Language" —
// in both languages (owner request 2026-09-26; before that the English
// side named the current language instead).
export function useLanguageChoice(): Choice<UiLanguage> {
  const { language, setLanguage, t } = useUiLanguage();
  return {
    icon: Languages,
    label: t('language.uiLanguage'),
    triggerLabel: t('language.toggle'),
    menuLabel: t('language.menu'),
    options: LANGUAGE_OPTIONS.map((option) => ({ ...option, icon: Languages })),
    value: language,
    onSelect: setLanguage,
  };
}
