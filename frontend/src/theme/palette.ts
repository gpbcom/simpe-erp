/**
 * The application's colours.
 *
 * Deep teal reads as care and health without the clinical coldness of a pure
 * medical blue; warm amber marks everything that is *waiting for somebody* —
 * which in this product is almost always a quote awaiting validation, and is
 * the state the whole workflow exists to make visible.
 *
 * The status maps are exhaustive over their enums on purpose. A status added to
 * the backend without a colour here is a TypeScript error rather than a grey
 * chip nobody can interpret.
 */

/** The brand colours, shared by both themes. */
export const BRAND = {
  primary: '#0F6E6E',
  primaryLight: '#12A19A',
  primaryDark: '#0A4F4F',
  secondary: '#C8791A',
  secondaryLight: '#E39B3E',
  secondaryDark: '#9A5B10',
} as const;

/** Colour and label for one quote status. */
/**
 * Colour for one invoice's commercial status.
 *
 * @remarks
 * `to-be-validated` is the amber one, for the same reason a quote awaiting
 * validation is: it is the only state waiting on a person, and nothing has
 * reached the customer while an invoice sits in it. `waiting-payment` is
 * informational rather than a warning — the agency has done its part and the
 * money is simply outstanding.
 */
export const BILL_STATUS_COLOUR = {
  'to-be-validated': 'warning',
  accepted: 'info',
  'waiting-payment': 'primary',
  paid: 'success',
} as const;

export const QUOTE_STATUS_COLOUR = {
  draft: 'default',
  'pending-validation': 'warning',
  sent: 'info',
  accepted: 'success',
  rejected: 'error',
  expired: 'default',
} as const;

/**
 * Colour for one customer's standing with the agency.
 *
 * @remarks
 * `prospect` is the amber one, for the same reason `pending-validation` is: it
 * is the state waiting on a person. A prospect may already hold accepted,
 * priced work that every planning run deliberately leaves out, and the only
 * thing standing between that work and the calendar is somebody pressing
 * *promote*. Drawn grey it would read as a customer like any other.
 */
export const REGISTRATION_STATUS_COLOUR = {
  active: 'success',
  prospect: 'warning',
  stopped: 'default',
} as const;

/** Colour for one intervention status. */
export const INTERVENTION_STATUS_COLOUR = {
  planned: '#12A19A',
  confirmed: '#0F6E6E',
  completed: '#5B7B7A',
  cancelled: '#C0392B',
} as const;

/**
 * The colours that tell assistants apart on a shared calendar.
 *
 * @remarks
 * Used only when *everybody* is shown at once, where the question the screen
 * answers is "whose visit is that?" rather than "what state is it in" — a grid
 * of forty blocks in the four status colours is unreadable. One assistant at a
 * time keeps the status colours above, because then "who" is already answered
 * by the rail.
 *
 * Twelve hues, walked round the wheel rather than listed by family, so two
 * assistants next to each other in the rail never come out nearly the same. The
 * list is indexed modulo its length: a thirteenth assistant repeats the first
 * colour, which is a legible collision because the rail carries the same swatch
 * as a legend.
 */
export const PLANNING_HCA_COLOURS = [
  '#0F6E6E',
  '#C8791A',
  '#4A6FA5',
  '#8E5AA8',
  '#2E7D32',
  '#B4436C',
  '#12A19A',
  '#9A5B10',
  '#5B7B7A',
  '#7A5C3E',
  '#3F7CAC',
  '#A03E3E',
] as const;

/** Colour for one notification kind. */
export const NOTIFICATION_KIND_COLOUR = {
  'quote-submitted': BRAND.secondary,
  'quote-validated': '#2E7D32',
  'quote-refused': '#C0392B',
  'planning-completed': BRAND.primary,
} as const;
