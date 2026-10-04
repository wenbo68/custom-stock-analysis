import { describe, expect, it } from 'vitest';
import { UI_TEXT, formatUiText, type UiLanguage, type UiTextKey } from '../uiText';

// A key present in one language and absent in the other is invisible to
// TypeScript (the dictionaries are plain records) and to every component
// test that renders only one language. It surfaces at RUNTIME as
// "Cannot read properties of undefined (reading 'replace')" inside
// formatUiText — which is how a title key deleted during the 2026-08-08
// modal rework took down the legacy /tiered page while the whole page
// suite stayed green.
describe('UI_TEXT — every language stays in step with English', () => {
  const en = Object.keys(UI_TEXT.en) as UiTextKey[];
  const others = (Object.keys(UI_TEXT) as UiLanguage[]).filter((language) => language !== 'en');

  it('offers the three languages the backend offers', () => {
    expect(Object.keys(UI_TEXT).sort()).toEqual(['en', 'ko', 'zh']);
  });

  it.each(others)('every English key has a %s one', (language) => {
    expect(en.filter((key) => !(key in UI_TEXT[language]))).toEqual([]);
  });

  it.each(others)('every %s key has an English one', (language) => {
    const keys = Object.keys(UI_TEXT[language]) as UiTextKey[];
    expect(keys.filter((key) => !(key in UI_TEXT.en))).toEqual([]);
  });

  it.each(others)('no entry is an empty string in English or %s', (language) => {
    const blank = en.filter(
      (key) => !UI_TEXT.en[key]?.trim() || !UI_TEXT[language][key]?.trim(),
    );
    expect(blank).toEqual([]);
  });

  it.each(others)('a placeholder in English appears in %s', (language) => {
    // "{label}" in English but not in the other language means that
    // string silently drops the value it was meant to interpolate.
    const slots = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
    const mismatched = en.filter(
      (key) => slots(UI_TEXT.en[key]).join() !== slots(UI_TEXT[language][key]).join(),
    );
    expect(mismatched).toEqual([]);
  });

  it('formatUiText fills a slot and leaves unknown ones alone', () => {
    expect(formatUiText('{a} and {b}', { a: 'x' })).toBe('x and {b}');
  });
});
