import { addDays, startOfWeek } from 'date-fns';
import { toIsoDate } from './format';

/**
 * How many days of planning the application shows at once.
 *
 * @remarks
 * Six weeks. Long enough that the month view has a full grid and the week
 * arrows have somewhere to go without a refetch on every click, short enough
 * that the request stays one page.
 */
export const PLANNING_WINDOW_DAYS = 42;

/** A span of days, as the API's date parameters want them. */
export interface PlanningWindow {
  /** First day, inclusive, as `YYYY-MM-DD`. */
  from: string;
  /** Last day, inclusive, as `YYYY-MM-DD`. */
  to: string;
}

/**
 * The span of planning every screen reads.
 *
 * @param days - How many days to cover. Defaults to the full window.
 * @returns The window, anchored to the Monday of the current week.
 *
 * @remarks
 * **One definition, shared, and that is the point.** The map and the team
 * planning both draw the same interventions, and when they each worked out
 * their own span they disagreed: the planning showed six weeks while the map
 * opened on the current week, so a manager who had just watched a run place
 * seventy-seven visits next week opened the map and found it empty. Nothing was
 * broken — the two screens were answering different questions and neither said
 * so.
 *
 * Anchored to **Monday of the current week** rather than to today, so a visit
 * earlier this week is still on screen. A window starting today would hide
 * Monday's round from anybody looking on Wednesday.
 */
export function planningWindow(days: number = PLANNING_WINDOW_DAYS): PlanningWindow {
  const monday = startOfWeek(new Date(), { weekStartsOn: 1 });
  return { from: toIsoDate(monday), to: toIsoDate(addDays(monday, days - 1)) };
}

/**
 * How far back a household's own calendar reaches.
 *
 * @remarks
 * Two months, because a family looks *backwards* far more often than the agency
 * does — "who came in June?" is the question behind most of the telephone calls
 * this screen exists to answer.
 */
export const CUSTOMER_WINDOW_LOOKBACK_DAYS = 60;

/** How far ahead a household's own calendar reaches. */
export const CUSTOMER_WINDOW_LOOKAHEAD_DAYS = 120;

/**
 * The span of care a household and the agency both read.
 *
 * @returns The window, anchored to the Monday of the current week.
 *
 * @remarks
 * **The same failure as {@link planningWindow}, one axis over.** That helper
 * exists because the map and the team planning each worked out their own span
 * and disagreed. This one exists because the household's portal and the
 * agency's customers view would do exactly the same: a family ringing about a
 * visit in June, looking at a screen that shows it, while the manager on the
 * telephone reads a six-week window that does not.
 *
 * So it is deliberately **not** {@link planningWindow}. The two answer different
 * questions and have no business sharing a number — what they must share is
 * that each is defined once.
 *
 * Wider than the staff window in both directions, and asymmetric on purpose: a
 * household's arrangement is measured in months, not in the fortnight a
 * scheduler works to.
 */
export function customerPlanningWindow(): PlanningWindow {
  const monday = startOfWeek(new Date(), { weekStartsOn: 1 });
  return {
    from: toIsoDate(addDays(monday, -CUSTOMER_WINDOW_LOOKBACK_DAYS)),
    to: toIsoDate(addDays(monday, CUSTOMER_WINDOW_LOOKAHEAD_DAYS)),
  };
}
