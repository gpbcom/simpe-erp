import SvgIcon, { type SvgIconProps } from '@mui/material/SvgIcon';

/**
 * The application's own icon set.
 *
 * Every glyph is drawn on the same 24×24 grid with a 1.75 stroke and round
 * caps, so they sit correctly beside MUI's own icons rather than looking like
 * a second, slightly-wrong family. They are paths rather than a font: a font
 * is one more network request that can fail, and it cannot inherit
 * `currentColor` per-path the way these do.
 *
 * Reached through one facade rather than imported individually, so the set
 * stays consistent — adding a glyph means adding it here, where the others are
 * visible.
 */
const PATHS = {
  /** A document with a torn receipt foot and a euro stroke: the invoice. */
  bill:
    'M6 3h9l3 3v13.5l-2-1.2-2 1.2-2-1.2-2 1.2-2-1.2-2 1.2V4a1 1 0 0 1 1-1Z M15 3v3h3 M14 10.5h-3.2a1.8 1.8 0 0 0 0 3.6h1.6a1.8 1.8 0 0 1 0 3.6H9 M8 12.3h4.5',
  /** A document with a price line: the quote. */
  quote:
    'M6 3h8l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z M14 3v4h4 M8.5 13h7 M8.5 17h4',
  /** A quote with a tick: validated. */
  quoteValidate: 'M6 3h8l4 4v6 M14 3v4h4 M5 4v16a1 1 0 0 0 1 1h5 M13.5 18l2.5 2.5 5-5',
  /** A quote with a cross: sent back. */
  quoteRefuse:
    'M6 3h8l4 4v6 M14 3v4h4 M5 4v16a1 1 0 0 0 1 1h5 M14.5 16.5l6 6 M20.5 16.5l-6 6',
  /** A quote waiting: the clock face. */
  quotePending: 'M6 3h8l4 4v6 M14 3v4h4 M5 4v16a1 1 0 0 0 1 1h5 M17.5 14v3.5l2.5 1.5',
  /** A person with a care badge: the assistant. */
  hca: 'M12 3a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7Z M5 21v-1.5A5.5 5.5 0 0 1 10.5 14h3a5.5 5.5 0 0 1 5.5 5.5V21 M12 16.5v3 M10.5 18h3',
  /** A person in a doorway: the customer, at home. */
  customer:
    'M4 21V9.5L12 4l8 5.5V21 M9.5 21v-5.5a2.5 2.5 0 0 1 5 0V21 M12 9.5a1 1 0 1 0 0 .01',
  /** A calendar grid: the planning. */
  planning:
    'M4 6.5h16v14H4z M4 10.5h16 M8 3.5v4 M16 3.5v4 M8 14h2 M14 14h2 M8 17.5h2 M14 17.5h2',
  /** A map pin. */
  mapPin:
    'M12 21s7-6.4 7-11a7 7 0 1 0-14 0c0 4.6 7 11 7 11Z M12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z',
  /** A bell. */
  notification:
    'M18 16V10.5a6 6 0 0 0-12 0V16l-1.5 2.5h15L18 16Z M10 21.5a2.2 2.2 0 0 0 4 0',
  /** A rosette: the certification. */
  certification:
    'M12 3a5.5 5.5 0 1 1 0 11 5.5 5.5 0 0 1 0-11Z M9 13.5 8 21l4-2 4 2-1-7.5 M12 6.5l1.2 2.4 2.6.4-1.9 1.8.5 2.6-2.4-1.3-2.4 1.3.5-2.6L8.2 9.3l2.6-.4Z',
  /** A hand holding a spark: the skill somebody declares about themselves. */
  skill:
    'M6.5 20.5v-6.5a2 2 0 0 1 2-2h5.5a2 2 0 0 1 0 4h-2.5 M4 20.5h2.5 M17 3.5l1 2.5 2.5 1-2.5 1-1 2.5-1-2.5-2.5-1 2.5-1Z',
  /** A crossed-out day: an absence. */
  availability:
    'M4 6.5h16v14H4z M4 10.5h16 M8 3.5v4 M16 3.5v4 M9.5 14.5l5 5 M14.5 14.5l-5 5',
  /** An office block: the company. */
  company:
    'M5 21V4.5h9V21 M14 10h5v11 M8 8h3 M8 12h3 M8 16h3 M16.5 13.5h.01 M16.5 17h.01',
  /** A tagged service: the catalog entry. */
  interventionType: 'M3.5 12.5 12 4h7.5v7.5L11 20l-7.5-7.5Z M16 8h.01',
  /** A tray with an arrow: export. */
  export:
    'M12 3.5v10 M8.5 10l3.5 3.5 3.5-3.5 M4.5 16v3.5a1 1 0 0 0 1 1h13a1 1 0 0 0 1-1V16',
  /** A house: the dashboard. */
  dashboard: 'M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-9.5Z M9.5 21v-6h5v6',
} as const;

/** The name of an icon in the application's own set. */
export type AppIconName = keyof typeof PATHS;

interface AppIconProps extends SvgIconProps {
  /** Which glyph to draw. */
  name: AppIconName;
}

/**
 * Draw one of the application's own icons.
 *
 * @param props - The icon name, plus anything `SvgIcon` accepts.
 * @returns The rendered icon.
 */
export function AppIcon({ name, ...props }: AppIconProps) {
  return (
    <SvgIcon
      viewBox="0 0 24 24"
      // Stroked rather than filled, matching MUI's outlined variants. A filled
      // glyph beside an outlined one is the difference a user notices without
      // being able to say why.
      sx={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.75 }}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {PATHS[name].split(' M').map((segment, index) => (
        <path key={index} d={index === 0 ? segment : `M${segment}`} />
      ))}
    </SvgIcon>
  );
}
