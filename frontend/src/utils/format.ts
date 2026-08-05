import { format, parseISO } from 'date-fns';
import { fr, enUS } from 'date-fns/locale';

/**
 * Formatting helpers, shared so every screen agrees.
 *
 * @remarks
 * Money and dates are the two things an ERP is judged on. A quote total shown
 * as `1234.5` on one screen and `1 234,50 €` on another reads as two different
 * numbers, and a French operator reading `08/12/2026` as 8 December when it
 * meant 12 August is a scheduling error, not a cosmetic one.
 */

/** The date-fns locale for a UI language. */
function localeFor(language: string) {
  return language.startsWith('fr') ? fr : enUS;
}

/**
 * Format an amount as euros.
 *
 * @param amount - The amount, as the decimal string the API sends.
 * @param language - The active UI language.
 * @returns The formatted amount, or a dash when there is none.
 *
 * @remarks
 * The API sends money as a **string**, because it is a `Decimal` server-side
 * and JSON numbers are binary floats. Parsing to a float here is safe only
 * because it happens at the very last step, for display.
 */
export function formatMoney(amount: string | null, language = 'fr'): string {
  if (amount === null) return '—';
  return new Intl.NumberFormat(language.startsWith('fr') ? 'fr-FR' : 'en-GB', {
    style: 'currency',
    currency: 'EUR',
  }).format(Number(amount));
}

/**
 * Format an ISO date as a readable day.
 *
 * @param iso - The ISO date, or null.
 * @param language - The active UI language.
 * @returns The formatted date, or a dash.
 */
export function formatDate(iso: string | null, language = 'fr'): string {
  if (!iso) return '—';
  return format(parseISO(iso), 'PP', { locale: localeFor(language) });
}

/**
 * Format an ISO timestamp as a day and time.
 *
 * @param iso - The ISO timestamp, or null.
 * @param language - The active UI language.
 * @returns The formatted timestamp, or a dash.
 */
export function formatDateTime(iso: string | null, language = 'fr'): string {
  if (!iso) return '—';
  return format(parseISO(iso), 'PPp', { locale: localeFor(language) });
}

/**
 * Format a `HH:MM:SS` clock time as `HH:MM`.
 *
 * @param value - The clock time from the API.
 * @returns The trimmed time.
 */
export function formatTime(value: string): string {
  return value.slice(0, 5);
}

/**
 * Return somebody's initials, for a photograph that will not load.
 *
 * @param fullName - The person's full name.
 * @returns Up to two upper-case initials.
 *
 * @remarks
 * Used by the map pins. An assistant with no photograph must still be a
 * distinguishable pin rather than a blank circle — the manager needs to know
 * who is where, and "nobody" is not an answer.
 */
export function initialsOf(fullName: string): string {
  return fullName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

/** An ISO date string for a `Date`, as the API expects. */
export function toIsoDate(value: Date): string {
  return format(value, 'yyyy-MM-dd');
}
