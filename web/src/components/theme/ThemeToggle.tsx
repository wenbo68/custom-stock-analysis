import type React from 'react';
import { HeaderMenu } from '../common/HeaderMenu';
import { useThemeChoice } from './useThemeChoice';

/** The color-scheme dropdown in the header. */
export const ThemeToggle: React.FC = () => <HeaderMenu {...useThemeChoice()} testId="theme-menu" />;
