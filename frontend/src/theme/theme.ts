import { createTheme, type Theme } from '@mui/material/styles';
import { frFR as coreFrFR } from '@mui/material/locale';
import { frFR as gridFrFR } from '@mui/x-data-grid/locales';
import { BRAND } from './palette';

/**
 * Build the application theme.
 *
 * @param mode - Whether to build the light or the dark theme.
 * @param locale - The active UI language, so MUI's own strings match.
 * @returns The MUI theme.
 *
 * @remarks
 * Two things here are deliberate and worth knowing:
 *
 * - **The density is dialled up.** An ERP is read, not browsed: an operator
 *   scanning ninety quotes wants ninety rows on screen, not thirty with
 *   generous whitespace between them. Hence the smaller base font, the tighter
 *   table rows, and `size="small"` as the default on inputs and buttons.
 * - **Buttons do not shout in capitals.** MUI uppercases button text by
 *   default, which turns "Valider le devis" into something that reads as a
 *   warning. In a screen where most buttons are ordinary actions, that is
 *   noise.
 */
export function buildTheme(mode: 'light' | 'dark', locale: string): Theme {
  const isDark = mode === 'dark';
  const localeBundles = locale.startsWith('fr') ? [coreFrFR, gridFrFR] : [];

  return createTheme(
    {
      palette: {
        mode,
        primary: {
          main: isDark ? BRAND.primaryLight : BRAND.primary,
          light: BRAND.primaryLight,
          dark: BRAND.primaryDark,
        },
        secondary: {
          main: isDark ? BRAND.secondaryLight : BRAND.secondary,
          light: BRAND.secondaryLight,
          dark: BRAND.secondaryDark,
        },
        background: {
          default: isDark ? '#0E1414' : '#F4F6F6',
          paper: isDark ? '#161D1D' : '#FFFFFF',
        },
      },
      typography: {
        fontFamily: 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif',
        // 14px rather than 16: the whole point of this interface is fitting a
        // working day's data on one screen.
        fontSize: 14,
        h1: { fontSize: '1.75rem', fontWeight: 600, letterSpacing: '-0.02em' },
        h2: { fontSize: '1.375rem', fontWeight: 600, letterSpacing: '-0.01em' },
        h3: { fontSize: '1.125rem', fontWeight: 600 },
        button: { textTransform: 'none', fontWeight: 500 },
      },
      shape: { borderRadius: 8 },
      components: {
        MuiButton: {
          defaultProps: { size: 'small', disableElevation: true },
        },
        MuiTextField: {
          defaultProps: { size: 'small', fullWidth: true },
        },
        MuiAppBar: {
          // Flat and bordered rather than shadowed: a shadow under a bar that
          // never scrolls away is decoration paid for on every repaint.
          defaultProps: { elevation: 0, color: 'inherit' },
          styleOverrides: {
            root: ({ theme }) => ({
              borderBottom: `1px solid ${theme.palette.divider}`,
              backgroundImage: 'none',
            }),
          },
        },
        MuiPaper: {
          styleOverrides: { root: { backgroundImage: 'none' } },
        },
        MuiCard: {
          defaultProps: { variant: 'outlined' },
        },
        MuiChip: {
          defaultProps: { size: 'small' },
          styleOverrides: { root: { fontWeight: 500 } },
        },
        MuiTableCell: {
          styleOverrides: { root: { paddingTop: 8, paddingBottom: 8 } },
        },
        MuiTooltip: {
          defaultProps: { arrow: true, enterDelay: 400 },
        },
      },
    },
    ...localeBundles,
  );
}
