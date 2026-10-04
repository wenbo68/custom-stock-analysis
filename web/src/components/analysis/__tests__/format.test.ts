import { describe, expect, it } from 'vitest';
import { formatDateTime, parseUtc, queuePosition } from '../format';

describe('queuePosition', () => {
  it('turns the count ahead into an English ordinal position', () => {
    expect(queuePosition(1, 'en')).toBe('1st');
    expect(queuePosition(2, 'en')).toBe('2nd');
    expect(queuePosition(3, 'en')).toBe('3rd');
    expect(queuePosition(4, 'en')).toBe('4th');
    // 11th-13th keep "th"; 21st, 22nd and 23rd go back to the short endings
    expect(queuePosition(11, 'en')).toBe('11th');
    expect(queuePosition(12, 'en')).toBe('12th');
    expect(queuePosition(13, 'en')).toBe('13th');
    expect(queuePosition(21, 'en')).toBe('21st');
    expect(queuePosition(22, 'en')).toBe('22nd');
    expect(queuePosition(23, 'en')).toBe('23rd');
    expect(queuePosition(111, 'en')).toBe('111th');
  });

  it('writes the position in Chinese', () => {
    expect(queuePosition(1, 'zh')).toBe('第 1 位');
    expect(queuePosition(3, 'zh')).toBe('第 3 位');
    expect(queuePosition(1, 'ko')).toBe('1번째');
    expect(queuePosition(3, 'ko')).toBe('3번째');
  });
});

describe('formatDateTime', () => {
  it('writes a stored UTC stamp as yyyy/mm/dd, hh:mm in local time', () => {
    const stamp = '2026-09-18T23:30:00';
    const local = parseUtc(stamp)!;
    const pad = (part: number) => String(part).padStart(2, '0');
    expect(formatDateTime(stamp)).toBe(
      `${local.getFullYear()}/${pad(local.getMonth() + 1)}/${pad(local.getDate())}, ` +
        `${pad(local.getHours())}:${pad(local.getMinutes())}`,
    );
    // The same instant whether or not the stamp carries its zone.
    expect(formatDateTime('2026-09-18T23:30:00Z')).toBe(formatDateTime(stamp));
  });

  it('shows a dash for a missing or unreadable stamp', () => {
    expect(formatDateTime(null)).toBe('—');
    expect(formatDateTime(undefined)).toBe('—');
    expect(formatDateTime('junk')).toBe('—');
    expect(parseUtc('junk')).toBeNull();
  });
});
