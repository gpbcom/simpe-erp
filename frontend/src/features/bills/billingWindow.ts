import type { BillingPeriodicity } from '@/api/types';

/**
 * Resolve the window a day falls in, under one periodicity.
 *
 * @param day - Any day inside the wanted period.
 * @param periodicity - The agency's rule.
 * @returns The first and last day, both inclusive, as ISO strings.
 *
 * @remarks
 * A **preview**, not the decision. The server resolves the real window from the
 * stored rule and the invoices carry that one. This is here so a manager sees
 * which month they are about to bill *before* pressing, rather than reading it
 * off the run afterwards.
 *
 * Mirrors `BillingPeriodicity.window_for`: Monday-anchored weeks, calendar
 * months and calendar years, with both bounds inclusive. The month's last day
 * is "the first of next month minus one", so February and leap years need no
 * special case here either.
 */
export function windowFor(
  day: string,
  periodicity: BillingPeriodicity,
): { start: string; end: string } {
  const iso = (value: Date): string => value.toISOString().slice(0, 10);
  const anchor = new Date(`${day}T00:00:00Z`);
  if (periodicity === 'weekly') {
    const weekday = anchor.getUTCDay() === 0 ? 7 : anchor.getUTCDay();
    const start = new Date(anchor);
    start.setUTCDate(anchor.getUTCDate() - (weekday - 1));
    const end = new Date(start);
    end.setUTCDate(start.getUTCDate() + 6);
    return { start: iso(start), end: iso(end) };
  }
  if (periodicity === 'monthly') {
    const start = new Date(Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth(), 1));
    const end = new Date(
      Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth() + 1, 0),
    );
    return { start: iso(start), end: iso(end) };
  }
  return {
    start: `${anchor.getUTCFullYear()}-01-01`,
    end: `${anchor.getUTCFullYear()}-12-31`,
  };
}
