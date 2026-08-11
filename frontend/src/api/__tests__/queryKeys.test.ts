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

/**
 * The billing keys.
 *
 * The same collision the customer keys were namespaced against: a disabled
 * query still reads whatever sits at its key, so `bill('')` — what the closed
 * drawer asks for — must not spell the unfiltered list.
 */
describe('billing query keys', () => {
  it('keeps a closed drawer from reading the list', () => {
    expect(keys.bill('')).not.toEqual(keys.bills(undefined));
  });

  it('keeps one invoice distinct from another', () => {
    expect(keys.bill('bill-1')).not.toEqual(keys.bill('bill-2'));
  });

  it('gives two filters that narrow the same way one entry', () => {
    expect(keys.bills({ status: 'paid', search: 'FA' })).toEqual(
      keys.bills({ search: 'FA', status: 'paid' }),
    );
  });

  it('gives two different filters two entries', () => {
    expect(keys.bills({ status: 'paid' })).not.toEqual(
      keys.bills({ status: 'accepted' }),
    );
  });

  it('keeps every bill key under one prefix, so invalidation still works', () => {
    // Starting a run invalidates `['bills']` wholesale. Namespacing the leaves
    // must not put any of them outside that prefix.
    for (const key of [
      keys.bills(undefined),
      keys.bills({ status: 'paid' }),
      keys.bill('bill-1'),
    ]) {
      expect(key[0]).toBe('bills');
    }
  });

  it('keeps the runs and the settings apart from each other', () => {
    expect(keys.billingRuns).not.toEqual(keys.billingSettings);
    expect(keys.billingRun('run-1')).not.toEqual(keys.billingRuns);
  });

  it('keeps the billing keys off the planning prefix', () => {
    // Both are "settings" and "runs"; sharing a prefix would mean a planning
    // mutation quietly emptying the billing caches.
    expect(keys.billingSettings[0]).toBe('billing');
    expect(keys.planningSettings[0]).toBe('planning');
  });
});
