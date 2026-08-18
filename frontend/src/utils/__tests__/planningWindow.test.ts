import { describe, expect, it } from 'vitest';
import { addDays, differenceInCalendarDays, startOfWeek } from 'date-fns';
import {
  CUSTOMER_WINDOW_LOOKAHEAD_DAYS,
  CUSTOMER_WINDOW_LOOKBACK_DAYS,
  PLANNING_WINDOW_DAYS,
  customerPlanningWindow,
  planningWindow,
} from '../planningWindow';
import { toIsoDate } from '../format';

const monday = (): Date => startOfWeek(new Date(), { weekStartsOn: 1 });

describe('planningWindow', () => {
  it('opens on the Monday of the current week', () => {
    // Anchored to Monday rather than to today, so a visit earlier this week is
    // still on screen for somebody looking on Wednesday.
    expect(planningWindow().from).toBe(toIsoDate(monday()));
  });

  it('covers six weeks', () => {
    const { from, to } = planningWindow();

    expect(differenceInCalendarDays(new Date(to), new Date(from))).toBe(
      PLANNING_WINDOW_DAYS - 1,
    );
  });
});

describe('customerPlanningWindow', () => {
  it('reaches back two months and forward four', () => {
    const { from, to } = customerPlanningWindow();

    expect(from).toBe(toIsoDate(addDays(monday(), -CUSTOMER_WINDOW_LOOKBACK_DAYS)));
    expect(to).toBe(toIsoDate(addDays(monday(), CUSTOMER_WINDOW_LOOKAHEAD_DAYS)));
  });

  it('is stable within a session', () => {
    // Held in state by both callers, but the helper itself must be the same
    // answer twice: a window that moved between two renders would produce a new
    // query key and refetch the whole screen under the reader.
    expect(customerPlanningWindow()).toEqual(customerPlanningWindow());
  });

  it('is not the staff window', () => {
    // **The two answer different questions and share no number.** A household's
    // arrangement is measured in months. A scheduler works to a fortnight. What
    // they share is that each is defined exactly once.
    expect(customerPlanningWindow()).not.toEqual(planningWindow());
  });

  it('reaches into the past, which the staff window never does', () => {
    // The distinguishing property, asserted rather than described: a family
    // rings about a visit in June, and a window starting this Monday cannot
    // show it.
    //
    // Compared as ISO strings, not as epoch millis: `new Date('2026-08-03')`
    // is parsed as midnight *UTC* while `startOfWeek` returns midnight local,
    // so the two disagree by the offset in every timezone east or west of
    // Greenwich. These are calendar days, and this is how the code compares
    // them.
    const { from } = customerPlanningWindow();

    expect(from < toIsoDate(monday())).toBe(true);
    expect(planningWindow().from).toBe(toIsoDate(monday()));
  });
});
