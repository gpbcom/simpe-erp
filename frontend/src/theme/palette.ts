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
export const QUOTE_STATUS_COLOUR = {
  draft: 'default',
  'pending-validation': 'warning',
  sent: 'info',
  accepted: 'success',
  rejected: 'error',
  expired: 'default',
} as const;

/** Colour for one intervention status. */
export const INTERVENTION_STATUS_COLOUR = {
  planned: '#12A19A',
  confirmed: '#0F6E6E',
  completed: '#5B7B7A',
  cancelled: '#C0392B',
} as const;

/** Colour for one notification kind. */
export const NOTIFICATION_KIND_COLOUR = {
  'quote-submitted': BRAND.secondary,
  'quote-validated': '#2E7D32',
  'quote-refused': '#C0392B',
  'planning-completed': BRAND.primary,
} as const;
