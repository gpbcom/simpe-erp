import { describe, expect, it } from 'vitest';
import { windowFor } from '../billingWindow';

/**
 * The window preview a manager sees before pressing Generate.
 *
 * A preview, not the decision — the server resolves the real window from the
 * stored rule. It still has to agree with it, because a preview that named
 * March while the run billed April would be worse than none at all. These
 * mirror the backend's own boundary cases one for one.
 */
describe('windowFor', () => {
  it('anchors a week on its Monday', () => {
    expect(windowFor('2026-08-13', 'weekly')).toEqual({
      start: '2026-08-10',
      end: '2026-08-16',
    });
  });

  it('keeps a Sunday in the week it ends', () => {
    // Off by one at this bound and a visit is billed twice: once at the end of
    // a week and again at the start of the next.
    expect(windowFor('2026-08-16', 'weekly')).toEqual({
      start: '2026-08-10',
      end: '2026-08-16',
    });
  });

  it('gives a 31-day month all of its days', () => {
    expect(windowFor('2026-01-15', 'monthly')).toEqual({
      start: '2026-01-01',
      end: '2026-01-31',
    });
  });

  it('gives a leap February its 29th', () => {
    // The last day is "the first of next month, minus one", so February needs
    // no special case here either.
    expect(windowFor('2024-02-10', 'monthly')).toEqual({
      start: '2024-02-01',
      end: '2024-02-29',
    });
  });

  it('rolls the year over in December', () => {
    expect(windowFor('2026-12-03', 'monthly')).toEqual({
      start: '2026-12-01',
      end: '2026-12-31',
    });
  });

  it('gives a year 1 January to 31 December', () => {
    expect(windowFor('2026-07-07', 'yearly')).toEqual({
      start: '2026-01-01',
      end: '2026-12-31',
    });
  });

  it('contains both of its own bounds', () => {
    // The property the whole pro-rata rests on: a day on either end resolves
    // to the same window, so no day falls between two periods.
    const window = windowFor('2026-05-20', 'monthly');

    expect(windowFor(window.start, 'monthly')).toEqual(window);
    expect(windowFor(window.end, 'monthly')).toEqual(window);
  });
});
