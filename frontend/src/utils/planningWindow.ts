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
