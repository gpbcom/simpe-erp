import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { customerFilterParams, parseCustomerFilter, useCustomerFilter } from '../useCustomerFilter';

/**
 * Render the hook under a router started at one URL.
 *
 * @param initial - The URL the screen is opened at.
 * @returns The hook result, and the location so a test can read the URL back.
 */
function atUrl(initial: string) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>
  );
  return renderHook(
    () => ({ filter: useCustomerFilter(), location: useLocation() }),
    { wrapper },
  );
}

describe('parseCustomerFilter', () => {
  it('reads every filter out of a query string', () => {
    const parsed = parseCustomerFilter(
      new URLSearchParams(
        'search=Durand&status=prospect&city=Paris&postal_code=75004' +
          '&email=example.com&phone=0612&has_ongoing_arrangement=true' +
          '&is_geocoded=false',
      ),
    );

    expect(parsed).toEqual({
      search: 'Durand',
      status: 'prospect',
      city: 'Paris',
      postal_code: '75004',
      email: 'example.com',
      phone: '0612',
      has_ongoing_arrangement: true,
      is_geocoded: false,
    });
  });

  it('keeps a false flag, which is a filter rather than an absence', () => {
    // "Whose address failed to resolve" is the question this one exists to
    // answer — those are the customers nothing can ever be planned for. Dropped
    // as falsy it would return the whole book instead.
    expect(parseCustomerFilter(new URLSearchParams('is_geocoded=false'))).toEqual({
      is_geocoded: false,
    });
  });

  it('drops a status the application has no word for', () => {
    // A stale or hand-edited link. Sent on, the server answers 422 and the
    // screen shows an error where a customer book belongs.
    expect(parseCustomerFilter(new URLSearchParams('status=lapsed'))).toEqual({});
  });

  it('drops a flag that is neither true nor false', () => {
    expect(parseCustomerFilter(new URLSearchParams('is_geocoded=maybe'))).toEqual({});
  });

  it('treats a blank box as no filter at all', () => {
    expect(parseCustomerFilter(new URLSearchParams('city=&search=%20%20'))).toEqual({});
  });

  it('round-trips through the query string', () => {
    const filter = { search: 'Durand', status: 'active' as const, is_geocoded: false };

    expect(parseCustomerFilter(customerFilterParams(filter))).toEqual(filter);
  });
});

describe('useCustomerFilter', () => {
  it('starts from the URL, so a shared link opens filtered', () => {
    const { result } = atUrl('/customers?status=prospect&city=Lyon');

    expect(result.current.filter.filter).toEqual({ status: 'prospect', city: 'Lyon' });
    expect(result.current.filter.isFiltered).toBe(true);
  });

  it('narrows nothing when the screen is opened plain', () => {
    const { result } = atUrl('/customers');

    expect(result.current.filter.filter).toEqual({});
    expect(result.current.filter.isFiltered).toBe(false);
  });

  it('applies a status tab at once', async () => {
    // A click is a finished decision. Delaying it the way typing is delayed
    // reads as the tab not working.
    const { result } = atUrl('/customers');

    act(() => result.current.filter.setStatus('prospect'));

    await waitFor(() =>
      expect(result.current.filter.filter).toEqual({ status: 'prospect' }),
    );
    expect(result.current.location.search).toBe('?status=prospect');
  });

  it('waits for typing to settle before narrowing the book', async () => {
    const { result } = atUrl('/customers');

    act(() => result.current.filter.setText('city', 'Par'));

    // Shown at once, so the box is not laggy to type in...
    expect(result.current.filter.draft.city).toBe('Par');
    // ...but not yet fetched, which is the request per keystroke this avoids.
    expect(result.current.filter.filter).toEqual({});

    await waitFor(() => expect(result.current.filter.filter).toEqual({ city: 'Par' }));
  });

  it('clears a text filter rather than sending an empty one', async () => {
    const { result } = atUrl('/customers?city=Paris');

    act(() => result.current.filter.setText('city', ''));

    await waitFor(() => expect(result.current.filter.filter).toEqual({}));
    // Not `?city=`, which would ride along in every link the screen produces.
    expect(result.current.location.search).toBe('');
  });

  it('writes a false flag to the URL', async () => {
    const { result } = atUrl('/customers');

    act(() => result.current.filter.setFlag('is_geocoded', false));

    await waitFor(() =>
      expect(result.current.location.search).toBe('?is_geocoded=false'),
    );
  });

  it('sorts the query string, so one filter is one cache entry', async () => {
    const { result } = atUrl('/customers');

    act(() => result.current.filter.setStatus('active'));
    act(() => result.current.filter.setFlag('is_geocoded', true));

    await waitFor(() =>
      expect(result.current.location.search).toBe('?is_geocoded=true&status=active'),
    );
  });

  it('clears everything at once', async () => {
    const { result } = atUrl('/customers?status=active&city=Lyon&is_geocoded=true');

    act(() => result.current.filter.reset());

    await waitFor(() => expect(result.current.filter.filter).toEqual({}));
    expect(result.current.filter.draft).toEqual({});
    expect(result.current.location.search).toBe('');
  });

  it('replaces history rather than pushing, so back leaves the screen', async () => {
    // Pushed, the back button would walk backwards through every intermediate
    // filter and leaving the page would take a dozen presses.
    const { result } = atUrl('/customers');
    const before = window.history.length;

    act(() => result.current.filter.setStatus('stopped'));
    await waitFor(() => expect(result.current.location.search).toBe('?status=stopped'));

    expect(window.history.length).toBe(before);
  });
});
