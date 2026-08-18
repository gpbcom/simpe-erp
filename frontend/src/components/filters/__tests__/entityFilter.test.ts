import { describe, expect, it } from 'vitest';
import { filterQuery, parseFilter } from '../entityFilter';
import type { EntityFilterSpec } from '../entityFilter';

const SPEC: EntityFilterSpec = {
  textFields: ['search', 'city'],
  flagFields: ['is_active'],
  enumFields: { status: ['draft', 'sent'] },
};

/**
 * The two pure halves of the shared filter: what a filter spells, and what a
 * URL is read back as.
 *
 * @remarks
 * These are the parts seven screens now share, so a mistake here is a mistake
 * everywhere. The hook itself needs a router and is covered by the screens'
 * own tests. This is the logic that has no excuse for being untested.
 */
describe('filterQuery', () => {
  it('drops what nobody filtered on', () => {
    // An absent field and a cleared box are the same thing: not a filter.
    expect(filterQuery({ search: undefined, city: '' })).toBe('');
    expect(filterQuery(undefined)).toBe('');
    expect(filterQuery({})).toBe('');
  });

  it('keeps `false`, which is a filter', () => {
    // The trap a falsy check falls into: "only the retired ones" would become
    // "everything", which reads as a filter that does not work.
    expect(filterQuery({ is_active: false })).toBe('is_active=false');
  });

  it('spells two orderings of one filter the same way', () => {
    // Two filters that narrow identically must share one cache entry, whatever
    // order the boxes were filled in.
    expect(filterQuery({ city: 'lyon', search: 'a' })).toBe(
      filterQuery({ search: 'a', city: 'lyon' }),
    );
  });

  it('escapes what a URL cannot carry raw', () => {
    expect(filterQuery({ search: 'a&b=c' })).toBe('search=a%26b%3Dc');
  });
});

describe('parseFilter', () => {
  it('reads back exactly what filterQuery wrote', () => {
    const filter = { search: 'amina', city: 'lyon', is_active: true, status: 'sent' };

    expect(parseFilter(new URLSearchParams(filterQuery(filter)), SPEC)).toEqual(filter);
  });

  it('drops an enum value the server would refuse', () => {
    // **A stale or hand-edited link.** Sent on, the server answers 422 and the
    // screen shows an error where a list belongs.
    const parsed = parseFilter(new URLSearchParams('status=lapsed'), SPEC);

    expect(parsed.status).toBeUndefined();
  });

  it('treats anything but true or false as no flag at all', () => {
    expect(parseFilter(new URLSearchParams('is_active=maybe'), SPEC).is_active).toBe(
      undefined,
    );
    expect(parseFilter(new URLSearchParams('is_active=false'), SPEC).is_active).toBe(
      false,
    );
  });

  it('ignores fields this screen does not have', () => {
    // One screen's link opened on another must not smuggle in a filter the
    // second screen cannot draw and the server would reject.
    const parsed = parseFilter(new URLSearchParams('phone=06&search=a'), SPEC);

    expect(parsed).toEqual({ search: 'a' });
  });

  it('trims a fragment and drops one that is only space', () => {
    expect(parseFilter(new URLSearchParams('search=%20%20'), SPEC).search).toBe(
      undefined,
    );
    expect(parseFilter(new URLSearchParams('search=%20a%20'), SPEC).search).toBe('a');
  });
});
