import { describe, expect, it } from 'vitest';
import { resultError, sizeText } from '../chatFormat';

describe('sizeText', () => {
  it('words bytes and kilobytes', () => {
    expect(sizeText(0)).toBe('0 B');
    expect(sizeText(900)).toBe('900 B');
    expect(sizeText(1536)).toBe('1.5 KB');
    expect(sizeText(20 * 1024)).toBe('20 KB');
    expect(sizeText(null)).toBe('0 B');
  });
});

describe('resultError', () => {
  it('reads an error code out of a tool result', () => {
    expect(resultError({ error: 'not_found' })).toBe('not_found');
    expect(resultError({ items: [] })).toBeNull();
    expect(resultError('text')).toBeNull();
  });
});
