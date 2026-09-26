import type React from 'react';
import { HeaderMenu } from '../common/HeaderMenu';
import { useLanguageChoice } from './useLanguageChoice';

/** The language dropdown in the header. */
export const UiLanguageToggle: React.FC = () => <HeaderMenu {...useLanguageChoice()} testId="language-menu" />;
