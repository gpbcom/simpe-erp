import { describe, expect, it } from 'vitest';
import { formatMoney, formatTime, initialsOf } from '../format';

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
