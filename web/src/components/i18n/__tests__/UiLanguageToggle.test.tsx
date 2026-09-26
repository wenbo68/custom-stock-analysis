import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { UiLanguageToggle } from '../UiLanguageToggle';

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe('UiLanguageToggle', () => {
  it('names the setting in both languages and offers each language in its own name', () => {
    render(
      <UiLanguageProvider>
        <UiLanguageToggle />
      </UiLanguageProvider>,
    );
    // jsdom reports English, so the page opens in English.
    const trigger = screen.getByRole('button', { name: 'Switch UI language' });
    expect(trigger).toHaveTextContent('Language');

    fireEvent.click(trigger);
    expect(screen.getByRole('menu', { name: 'UI language options' })).toBeInTheDocument();
    expect(screen.getByRole('menuitemradio', { name: '中文' })).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('menuitemradio', { name: 'English' })).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(screen.getByRole('menuitemradio', { name: '中文' }));
    // The menu closes; the trigger still names the setting, now in Chinese.
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.getByRole('button', { name: '切换界面语言' })).toHaveTextContent('语言');
    expect(document.documentElement.lang).toBe('zh-CN');
  });
});
