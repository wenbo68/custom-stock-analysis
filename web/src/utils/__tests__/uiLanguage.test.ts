import { describe, expect, it } from 'vitest';
import { normalizeUiLanguage, resolveInitialUiLanguage } from '../uiLanguage';

function memoryStorage(initial: Record<string, string> = {}): Storage {
  const data = new Map(Object.entries(initial));
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (key) => data.get(key) ?? null,
    key: (index) => [...data.keys()][index] ?? null,
    removeItem: (key) => void data.delete(key),
    setItem: (key, value) => void data.set(key, value),
  };
}

describe('normalizeUiLanguage', () => {
  it('accepts each offered code and nothing else', () => {
    expect(normalizeUiLanguage('zh')).toBe('zh');
    expect(normalizeUiLanguage('en')).toBe('en');
    expect(normalizeUiLanguage('ko')).toBe('ko');
    expect(normalizeUiLanguage('fr')).toBeNull();
    expect(normalizeUiLanguage(null)).toBeNull();
  });
});

describe('resolveInitialUiLanguage', () => {
  it('prefers a saved choice over the browser', () => {
    const storage = memoryStorage({ uiLanguage: 'ko' });
    expect(resolveInitialUiLanguage({ storage, navigatorLike: { language: 'en-US', languages: ['en-US'] } })).toBe('ko');
  });

  it('reads the browser language when nothing is saved', () => {
    expect(resolveInitialUiLanguage({ navigatorLike: { language: 'ko-KR', languages: ['ko-KR', 'en'] } })).toBe('ko');
    expect(resolveInitialUiLanguage({ navigatorLike: { language: 'en-GB', languages: ['en-GB'] } })).toBe('en');
    expect(resolveInitialUiLanguage({ navigatorLike: { language: 'zh-TW', languages: ['zh-TW'] } })).toBe('zh');
  });

  it('falls back to Chinese for a browser language it does not speak', () => {
    expect(resolveInitialUiLanguage({ navigatorLike: { language: 'fr-FR', languages: ['fr-FR'] } })).toBe('zh');
  });
});
