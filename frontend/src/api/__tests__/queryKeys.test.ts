import { describe, expect, it } from 'vitest';
import { customerFilterQuery, keys } from '../queries';

/**
 * The cache keys, asserted where they can collide.
 *
 * @remarks
 * TanStack Query hands a hook whatever sits at its key, **including when the
 * hook is disabled**. Two different things sharing one key is therefore not a
 * stale-data bug, it is a type confusion: the reader gets a value of a shape it
 * never asked for and dereferences it.
 *
 * That is not hypothetical here. `customer('')` — what the detail drawer asks
 * for while nothing is selected — used to spell `['customers', '']`, which is
 * exactly where the *unfiltered list* was cached. The drawer was handed the
 * whole array, read `.address` off it, and blanked the customers page on every
 * first visit.
 */
describe('customer query keys', () => {
  it('never lets the closed drawer collide with the unfiltered list', () => {
    expect(keys.customer('')).not.toEqual(keys.customers(undefined));
    expect(keys.customer('')).not.toEqual(keys.customers({}));
  });

  it('separates a detail from a list however the filter is spelled', () => {
    const filters = [
      undefined,
      {},
      { search: '' },
      { search: 'adam' },
      { status: 'prospect' as const },
    ];

    for (const filter of filters) {
      const list = JSON.stringify(keys.customers(filter));
      for (const id of ['', 'customer-1', customerFilterQuery(filter)]) {
        expect(JSON.stringify(keys.customer(id))).not.toEqual(list);
      }
    }
  });

  it('keeps a customer\'s quotes distinct from the customer', () => {
    expect(keys.customerQuotes('c-1')).not.toEqual(keys.customer('c-1'));
  });

  it('keeps every customer key under one prefix, so invalidation still works', () => {
    // Every mutation invalidates `['customers']` wholesale. Namespacing the
    // leaves must not put any of them outside that prefix.
    for (const key of [
      keys.customers(undefined),
      keys.customers({ search: 'x' }),
      keys.customer('c-1'),
      keys.customerQuotes('c-1'),
    ]) {
      expect(key[0]).toBe('customers');
    }
  });

  it('gives two filters that narrow the same way one entry', () => {
    // The ordering guarantee `customerFilterQuery` exists for: the boxes can be
    // filled in either order and must not produce two cache entries.
    expect(customerFilterQuery({ search: 'a', status: 'active' })).toEqual(
      customerFilterQuery({ status: 'active', search: 'a' }),
    );
  });
});
