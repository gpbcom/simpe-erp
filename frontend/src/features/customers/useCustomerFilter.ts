import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { customerFilterQuery } from '@/api/queries';
import type { CustomerFilter, RegistrationStatus } from '@/api/types';

/** The filters somebody types into, and which therefore wait for a pause. */
const TEXT_FIELDS = ['search', 'city', 'postal_code', 'email', 'phone'] as const;

/** The three-state flags, which are clicked rather than typed. */
const FLAG_FIELDS = ['has_ongoing_arrangement', 'is_geocoded'] as const;

/** Every status the server will accept as a filter. */
const STATUSES: RegistrationStatus[] = ['active', 'prospect', 'stopped'];

/**
 * How long typing pauses before the book is re-fetched, in milliseconds.
 *
 * The search box used to fire a request per keystroke; with six text filters
 * that is materially worse, and every one of those requests scans the whole
 * customer table.
 */
const SETTLE_MS = 300;

/** A filter field that holds text. */
export type CustomerTextField = (typeof TEXT_FIELDS)[number];

/** What the customers screen gets back. */
export interface CustomerFilterState {
  /** What the book is actually narrowed by — the URL, settled. */
  filter: CustomerFilter;
  /** What the inputs show, which runs ahead of `filter` while typing. */
  draft: CustomerFilter;
  /** Set a text filter. Applied after a pause. */
  setText: (field: CustomerTextField, value: string) => void;
  /** Set the status filter, or clear it with `undefined`. Applied at once. */
  setStatus: (status: RegistrationStatus | undefined) => void;
  /** Set a three-state flag. Applied at once. */
  setFlag: (field: (typeof FLAG_FIELDS)[number], value: boolean | undefined) => void;
  /** Clear everything. */
  reset: () => void;
  /** Whether anything is currently narrowing the book. */
  isFiltered: boolean;
}

/**
 * Read a customer filter out of a query string.
 *
 * @param params - The URL's search parameters.
 * @returns The filter they describe.
 *
 * @remarks
 * Deliberately forgiving about rubbish. A hand-edited or stale link carrying
 * `?status=lapsed` drops the status rather than sending it on: the server would
 * answer 422 and the screen would show an error where a customer book belongs.
 * A flag is only a flag when it reads exactly `true` or `false`, so `?
 * is_geocoded=maybe` is no filter rather than a truthy one.
 */
export function parseCustomerFilter(params: URLSearchParams): CustomerFilter {
  const parsed: CustomerFilter = {};
  for (const field of TEXT_FIELDS) {
    const value = params.get(field)?.trim();
    if (value) parsed[field] = value;
  }
  const status = params.get('status');
  if (status && STATUSES.includes(status as RegistrationStatus)) {
    parsed.status = status as RegistrationStatus;
  }
  for (const field of FLAG_FIELDS) {
    const value = params.get(field);
    if (value === 'true' || value === 'false') parsed[field] = value === 'true';
  }
  return parsed;
}

/**
 * Turn a filter back into a query string.
 *
 * @param filter - The filter to write.
 * @returns The search parameters describing it.
 *
 * @remarks
 * Built from {@link customerFilterQuery} rather than field by field, so the URL
 * and the request that the URL causes are spelled by the same code. Two ways of
 * writing the same filter is how a shared link comes back showing something
 * else.
 */
export function customerFilterParams(filter: CustomerFilter): URLSearchParams {
  return new URLSearchParams(customerFilterQuery(filter));
}

/**
 * The customers screen's filter, held in the URL.
 *
 * @returns The current filter, the draft the inputs show, and the setters.
 *
 * @remarks
 * **The URL is the state.** A manager who has narrowed the book to the
 * prospects in Lyon can send that link to a colleague, reload without losing
 * it, and use the back button to undo a filter — none of which works when the
 * same thing lives in a `useState`.
 *
 * Two speeds, because the controls are two different gestures. Typing settles
 * for {@link SETTLE_MS} before the URL moves; a status tab or a flag applies at
 * once, since a click is already a finished decision and delaying it reads as
 * the control not working.
 *
 * History entries are **replaced**, not pushed. Pushing would make the back
 * button walk backwards through every intermediate filter, so leaving the
 * screen would take a dozen presses.
 */
export function useCustomerFilter(): CustomerFilterState {
  const [params, setParams] = useSearchParams();
  const filter = useMemo(() => parseCustomerFilter(params), [params]);
  const [draft, setDraft] = useState<CustomerFilter>(filter);
  // What we last wrote. Distinguishes the URL moving because of us from the URL
  // moving on its own — a back button, or a link somebody pasted.
  const written = useRef<string>(customerFilterQuery(filter));

  const commit = useCallback(
    (next: CustomerFilter) => {
      written.current = customerFilterQuery(next);
      setParams(customerFilterParams(next), { replace: true });
    },
    [setParams],
  );

  useEffect(() => {
    const arrived = customerFilterQuery(filter);
    if (arrived === written.current) return;
    // The URL moved without us: adopt it, and drop whatever was half-typed.
    written.current = arrived;
    setDraft(filter);
  }, [filter]);

  useEffect(() => {
    const query = customerFilterQuery(draft);
    if (query === written.current) return;
    const timer = window.setTimeout(() => commit(draft), SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [draft, commit]);

  const setText = useCallback((field: CustomerTextField, value: string) => {
    // Emptied rather than kept as `''`: an input box somebody cleared is not a
    // filter on the empty string, and leaving it in would put `?city=` in every
    // link the screen produces from then on.
    setDraft((current) => ({ ...current, [field]: value || undefined }));
  }, []);

  // Built from `draft` rather than inside a `setDraft` updater: an updater is
  // expected to be pure and React runs it twice in development, which would
  // send the URL two rewrites for one click.
  const setStatus = useCallback(
    (status: RegistrationStatus | undefined) => {
      const next = { ...draft, status };
      setDraft(next);
      commit(next);
    },
    [draft, commit],
  );

  const setFlag = useCallback(
    (field: (typeof FLAG_FIELDS)[number], value: boolean | undefined) => {
      const next = { ...draft, [field]: value };
      setDraft(next);
      commit(next);
    },
    [draft, commit],
  );

  const reset = useCallback(() => {
    setDraft({});
    commit({});
  }, [commit]);

  return {
    filter,
    draft,
    setText,
    setStatus,
    setFlag,
    reset,
    isFiltered: customerFilterQuery(filter) !== '',
  };
}
