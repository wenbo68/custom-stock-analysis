import type React from 'react';
import { UiLanguageToggle } from '../i18n/UiLanguageToggle';
import { ModeToggle } from '../mode/ModeToggle';
import { ThemeToggle } from '../theme/ThemeToggle';

// The header's set of menus, in the owner's order (2026-09-26): mode,
// then language, then theme. The analysis page shows it in the header
// row; the chat page floats it over the conversation's top right corner
// (owner request 2026-09-27), so the history column can start at the top.
export const HeaderControls: React.FC = () => (
  <div className="flex items-center gap-2" data-testid="header-controls">
    <ModeToggle />
    <UiLanguageToggle />
    <ThemeToggle />
  </div>
);
