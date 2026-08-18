/**
 * One filter mechanism for every list screen.
 *
 * @remarks
 * The customer book had all of this to itself: a filter held in the URL, typed
 * boxes that settle before they fetch, clicked controls that apply at once, and
 * a query string spelled by one function so the link and the request cannot
 * disagree. Six more screens now want the same thing, and six more copies of a
 * 180-line hook is six places for the debounce, the history handling or the
 * blank-clearing to drift.
 *
 * What differs per screen is only *which fields it has* — so that is what a
 * screen supplies, as a spec.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

export type FilterValue = string | boolean | undefined;
export type EntityFilterRecord = Record<string, FilterValue>;

/**
 * Which of a screen's fields are text, which are flags, and which are closed
 * lists.
 *
 * @remarks
 * Declared rather than inferred. A hook that guessed from the values would stop
 * validating a field the moment it happened to be empty, and an enum whose
 * allowed values it did not know is an enum it cannot protect the screen from.
 */
export interface EntityFilterSpec {
  /** Fields somebody types into, which therefore wait for a pause. */
  readonly textFields: readonly string[];
  /** Three-state flags, which are clicked and apply at once. */
  readonly flagFields: readonly string[];
  /** Closed lists, mapped to every value the server will accept. */
  readonly enumFields: Readonly<Record<string, readonly string[]>>;
}

/**
 * How long typing pauses before the list is re-fetched, in milliseconds.
 *
 * @remarks
 * A request per keystroke is materially worse once a screen has five text
 * filters, and every one of those requests scans the whole table.
 */
export const SETTLE_MS = 300;

/**
 * Turn a filter into the query string that fetches it.
 *
 * @param filter - The filter to spell.
 * @returns The query string, with the fields in a stable order.
 *
 * @remarks
 * Sorted, so two filters that narrow the same way share one cache entry
 * whatever order the boxes were filled in. Empty and `undefined` values are
 * dropped: a box somebody cleared is not a filter on the empty string, and
 * leaving it in would put `?city=` in every link the screen produces from then
 * on — and, on an enumerated field, would be refused by the server outright.
 */
export function filterQuery(filter?: EntityFilterRecord): string {
  return Object.entries(filter ?? {})
    .filter(([, value]) => value !== undefined && value !== '')
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([field, value]) => `${field}=${encodeURIComponent(String(value))}`)
    .join('&');
}

/**
 * Read a filter out of a query string, forgivingly.
 *
 * @param params - The URL's search parameters.
 * @param spec - Which fields the screen has.
 * @returns The filter they describe.
 *
 * @remarks
 * Deliberately forgiving about rubbish. A hand-edited or stale link carrying
 * `?status=lapsed` drops the status rather than sending it on: the server would
 * answer 422 and the screen would show an error where a list belongs. A flag is
 * only a flag when it reads exactly `true` or `false`.
 */
export function parseFilter(
  params: URLSearchParams,
  spec: EntityFilterSpec,
): EntityFilterRecord {
  const parsed: EntityFilterRecord = {};
  for (const field of spec.textFields) {
    const value = params.get(field)?.trim();
    if (value) parsed[field] = value;
  }
  for (const [field, allowed] of Object.entries(spec.enumFields)) {
    const value = params.get(field);
    if (value && allowed.includes(value)) parsed[field] = value;
  }
  for (const field of spec.flagFields) {
    const value = params.get(field);
    if (value === 'true' || value === 'false') parsed[field] = value === 'true';
  }
  return parsed;
}

/** What a list screen gets back from {@link useEntityFilter}. */
export interface EntityFilterState {
  filter: EntityFilterRecord;
  draft: EntityFilterRecord;
  setText: (field: string, value: string) => void;
  setChoice: (field: string, value: string | undefined) => void;
  setFlag: (field: string, value: boolean | undefined) => void;
  reset: () => void;
  isFiltered: boolean;
}

/**
 * A list screen's filter, held in the URL.
 *
 * @param spec - Which fields this screen filters on.
 * @returns The current filter, the draft the inputs show, and the setters.
 *
 * @remarks
 * **The URL is the state.** Somebody who has narrowed a list can send that link
 * to a colleague, reload without losing it, and use the back button to undo a
 * filter — none of which works when the same thing lives in a `useState`.
 *
 * Two speeds, because the controls are two different gestures. Typing settles
 * for {@link SETTLE_MS} before the URL moves. A tab, a select or a flag applies
 * at once, since a click is already a finished decision and delaying it reads
 * as the control not working.
 *
 * History entries are **replaced**, not pushed. Pushing would make the back
 * button walk backwards through every intermediate filter, so leaving the
 * screen would take a dozen presses.
 */
export function useEntityFilter(spec: EntityFilterSpec): EntityFilterState {
  const [params, setParams] = useSearchParams();
  const filter = useMemo(() => parseFilter(params, spec), [params, spec]);
  const [draft, setDraft] = useState<EntityFilterRecord>(filter);
  const written = useRef<string>(filterQuery(filter));

  const commit = useCallback(
    (next: EntityFilterRecord) => {
      written.current = filterQuery(next);
      const rest = new URLSearchParams(params);
      const owned = [
        ...spec.textFields,
        ...spec.flagFields,
        ...Object.keys(spec.enumFields),
      ];
      for (const field of owned) rest.delete(field);
      const merged = new URLSearchParams(filterQuery(next));
      for (const [key, value] of rest.entries()) merged.append(key, value);
      setParams(merged, { replace: true });
    },
    [params, setParams, spec],
  );

  useEffect(() => {
    const arrived = filterQuery(filter);
    if (arrived === written.current) return;
    written.current = arrived;
    setDraft(filter);
  }, [filter]);

  useEffect(() => {
    const query = filterQuery(draft);
    if (query === written.current) return;
    const timer = window.setTimeout(() => commit(draft), SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [draft, commit]);

  const setText = useCallback((field: string, value: string) => {
    setDraft((current) => ({ ...current, [field]: value || undefined }));
  }, []);

  const setChoice = useCallback(
    (field: string, value: string | undefined) => {
      const next = { ...draft, [field]: value };
      setDraft(next);
      commit(next);
    },
    [draft, commit],
  );

  const setFlag = useCallback(
    (field: string, value: boolean | undefined) => {
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
    setChoice,
    setFlag,
    reset,
    isFiltered: filterQuery(filter) !== '',
  };
}
