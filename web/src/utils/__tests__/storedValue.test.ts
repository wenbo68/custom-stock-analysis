import { describe, expect, it } from 'vitest';
import { readStoredValue } from '../storedValue';

const memoryStorage = (initial: Record<string, string>): Storage => {
  const data = new Map(Object.entries(initial));
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => void data.set(key, value),
    removeItem: (key) => void data.delete(key),
    clear: () => data.clear(),
    key: (index) => [...data.keys()][index] ?? null,
    get length() {
      return data.size;
    },
  };
};

describe('readStoredValue', () => {
  it('prefers the current key', () => {
    const storage = memoryStorage({ 'run.capital': '5000', 'tiered.sizing.capital': '100' });
    expect(readStoredValue(storage, 'run.capital', 'tiered.sizing.capital')).toBe('5000');
    expect(storage.getItem('tiered.sizing.capital')).toBe('100');
  });

  it('reads a value saved under the pre-rename key once and moves it', () => {
    const storage = memoryStorage({ 'dsa.uiLanguage': 'en' });
    expect(readStoredValue(storage, 'uiLanguage', 'dsa.uiLanguage')).toBe('en');
    expect(storage.getItem('uiLanguage')).toBe('en');
    expect(storage.getItem('dsa.uiLanguage')).toBeNull();
  });

  it('is null without a value, without storage, or when storage throws', () => {
    expect(readStoredValue(memoryStorage({}), 'run.capital', 'tiered.sizing.capital')).toBeNull();
    expect(readStoredValue(memoryStorage({}), 'run.capital')).toBeNull();
    expect(readStoredValue(null, 'run.capital')).toBeNull();
    const broken = { ...memoryStorage({}), getItem: () => { throw new Error('blocked'); } } as Storage;
    expect(readStoredValue(broken, 'run.capital', 'tiered.sizing.capital')).toBeNull();
  });
});
