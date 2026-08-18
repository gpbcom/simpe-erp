import { describe, expect, it } from 'vitest';
import {
  formatMoney,
  formatTime,
  initialsOf,
  minutesToTime,
  timeToMinutes,
} from '../format';

describe('formatMoney', () => {
  it('formats an amount as euros', () => {
    // The API sends money as a *string* because it is a Decimal server-side;
    // parsing to a float any earlier than display would lose cents.
    const formatted = formatMoney('1234.5', 'fr');

    expect(formatted).toContain('1');
    expect(formatted).toContain('€');
  });

  it('shows a dash rather than zero when there is no amount', () => {
    // An unpriced quote line has no total. Showing "0,00 €" would state a
    // price nobody has computed.
    expect(formatMoney(null)).toBe('—');
  });
});

describe('formatTime', () => {
  it('trims the seconds off a clock time', () => {
    expect(formatTime('09:30:00')).toBe('09:30');
  });
});

describe('initialsOf', () => {
  it('takes at most two initials', () => {
    expect(initialsOf('Marie Claire Durand')).toBe('MC');
  });

  it('survives a single name', () => {
    // Used by the map pins: an assistant with no photograph must still be a
    // distinguishable pin rather than a blank circle.
    expect(initialsOf('Luc')).toBe('L');
  });
});

describe('minutesToTime', () => {
  it('zero-pads both halves', () => {
    // The planning rules are minutes from midnight because that is the unit
    // the solver works in. A `<input type="time">` needs `HH:MM`.
    expect(minutesToTime(9 * 60)).toBe('09:00');
    expect(minutesToTime(19 * 60 + 30)).toBe('19:30');
  });

  it('renders midnight rather than an empty string', () => {
    expect(minutesToTime(0)).toBe('00:00');
  });
});

describe('timeToMinutes', () => {
  it('parses a clock time into minutes from midnight', () => {
    expect(timeToMinutes('08:00')).toBe(480);
    expect(timeToMinutes('19:30')).toBe(1170);
  });

  it('round-trips every minute of the day', () => {
    for (const minute of [0, 1, 59, 540, 1170, 1439]) {
      expect(timeToMinutes(minutesToTime(minute))).toBe(minute);
    }
  });

  it('returns null rather than zero for an unparseable value', () => {
    // **The case that would save a day nobody chose.** A cleared time input
    // reads as an empty string, and returning 0 would store it as a working
    // day starting at midnight — a plausible-looking number, silently wrong.
    expect(timeToMinutes('')).toBeNull();
    expect(timeToMinutes('morning')).toBeNull();
    expect(timeToMinutes('25:00')).toBeNull();
    expect(timeToMinutes('09:75')).toBeNull();
  });
});
