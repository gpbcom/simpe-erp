import { describe, expect, it } from 'vitest';
import { hasAtLeast, isStaff } from '../session';
import type { UserRole } from '@/api/types';

describe('the two axes of UserRole', () => {
  it('ranks the staff ladder', () => {
    expect(hasAtLeast('admin', 'manager')).toBe(true);
    expect(hasAtLeast('manager', 'manager')).toBe(true);
    expect(hasAtLeast('hca', 'manager')).toBe(false);
  });

  it('answers false for a customer on every staff check', () => {
    // The right answer to "may they see the agency's screens". A customer is
    // not a low rung, so they satisfy none of them.
    expect(hasAtLeast('customer', 'hca')).toBe(false);
    expect(hasAtLeast('customer', 'manager')).toBe(false);
    expect(hasAtLeast('customer', 'admin')).toBe(false);
  });

  it('separates the two axes', () => {
    expect(isStaff('customer')).toBe(false);
    expect(isStaff('hca')).toBe(true);
    expect(isStaff('manager')).toBe(true);
    expect(isStaff('admin')).toBe(true);
    expect(isStaff(undefined)).toBe(false);
  });

  it('cannot be asked whether somebody is "at least a customer"', () => {
    // The real control is the *type*: `hasAtLeast(role, 'customer')` does not
    // compile, because `minimum` is `StaffRole`. That is what stops the call
    // being written at all — below the ladder it would be true for every
    // employee, admitting staff to a household's private space.
    //
    // This assertion is the runtime backstop for a caller that reached it
    // through an `any`, and the comment is the record of why the type is
    // narrow. Both ends agree: the server's `rank()` raises rather than
    // answering.
    const asAny = hasAtLeast as (a: UserRole, b: string) => boolean;

    expect(asAny('admin', 'customer')).toBe(false);
    expect(asAny('hca', 'customer')).toBe(false);
  });
});
