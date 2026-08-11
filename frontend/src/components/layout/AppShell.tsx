import { useState } from 'react';
import { Link as RouterLink, Outlet, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import ListSubheader from '@mui/material/ListSubheader';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Toolbar from '@mui/material/Toolbar';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import LogoutIcon from '@mui/icons-material/Logout';
import TranslateIcon from '@mui/icons-material/Translate';
import DarkModeIcon from '@mui/icons-material/DarkMode';
import LightModeIcon from '@mui/icons-material/LightMode';
import { AppIcon, type AppIconName } from '@/components/icons/AppIcon';
import { NotificationBell } from '@/features/notifications/NotificationBell';
import { LANGUAGES, setLanguage } from '@/i18n';
import { useUpdateMyAccount } from '@/api/queries';
import { hasAtLeast, useSession } from '@/store/session';
import type { UserRole } from '@/api/types';
import logo from '@/assets/brand/logo-full.svg';

/** How wide the navigation rail is. */
const DRAWER_WIDTH = 248;

interface NavEntry {
  /** Where it goes. */
  to: string;
  /** The translation key for its label. */
  labelKey: string;
  /** Which glyph to draw. */
  icon: AppIconName;
  /** The lowest role that may see it. */
  minimum?: UserRole;
  /** Whether it is only for an account bound to an assistant record. */
  assistantOnly?: boolean;
}

/**
 * The navigation, in the order an operator's day runs.
 *
 * @remarks
 * Filtered by role rather than disabled: an entry a caller may not use is
 * absent, not greyed out. A greyed-out menu advertises what the person is not
 * allowed to do, which invites them to ask why rather than get on with the job.
 */
const NAV: { headingKey: string; entries: NavEntry[] }[] = [
  {
    headingKey: 'nav.myAccount',
    entries: [
      // Not `assistantOnly`. Every account has details, a sign-in address and a
      // password, and a manager who cannot reach their own account page cannot
      // change any of them. This entry was the door to a screen that already
      // rendered for them — hiding it made the fix on the page invisible.
      { to: '/me', labelKey: 'nav.myAccount', icon: 'hca' },
      {
        to: '/me/planning',
        labelKey: 'nav.myPlanning',
        icon: 'planning',
        assistantOnly: true,
      },
      {
        to: '/me/customers',
        labelKey: 'nav.myCustomers',
        icon: 'customer',
        assistantOnly: true,
      },
      { to: '/me/quotes', labelKey: 'nav.myQuotes', icon: 'quote' },
    ],
  },
  {
    // Not `nav.quotes`. This group holds the workforce, the plannings, the map
    // and the notifications as well, and heading it "Devis" named one entry
    // after another — the reader sees "Devis › Devis, Intervenants, Carte" and
    // cannot tell what the group is for.
    headingKey: 'nav.operations',
    entries: [
      { to: '/quotes', labelKey: 'nav.quotes', icon: 'quote', minimum: 'manager' },
      { to: '/bills', labelKey: 'nav.bills', icon: 'bill', minimum: 'manager' },
      { to: '/hcas', labelKey: 'nav.hcas', icon: 'hca', minimum: 'manager' },
      {
        to: '/plannings',
        labelKey: 'nav.teamPlanning',
        icon: 'planning',
        minimum: 'manager',
      },
      {
        // Back after being removed: the entry was here for a long time with no
        // route behind it, so clicking it fell through to the catch-all and
        // silently redirected home. It now has a screen.
        to: '/customers',
        labelKey: 'nav.customers',
        icon: 'customer',
        minimum: 'manager',
      },
      { to: '/map', labelKey: 'nav.map', icon: 'mapPin', minimum: 'manager' },
      {
        to: '/notifications',
        labelKey: 'nav.notifications',
        icon: 'notification',
      },
    ],
  },
  {
    headingKey: 'nav.administration',
    entries: [
      {
        to: '/intervention-types',
        labelKey: 'nav.interventionTypes',
        icon: 'interventionType',
        minimum: 'manager',
      },
      {
        to: '/certifications',
        labelKey: 'nav.certifications',
        icon: 'certification',
        minimum: 'manager',
      },
      {
        to: '/skills',
        labelKey: 'nav.skills',
        icon: 'skill',
        minimum: 'manager',
      },
      {
        to: '/billing-settings',
        labelKey: 'nav.billingSettings',
        icon: 'bill',
        minimum: 'manager',
      },
      {
        to: '/planning-settings',
        labelKey: 'nav.planningSettings',
        icon: 'planning',
        minimum: 'manager',
      },
      {
        to: '/company',
        labelKey: 'nav.company',
        icon: 'company',
        minimum: 'admin',
      },
    ],
  },
];

/**
 * The persistent frame every screen sits in.
 *
 * @returns The shell, with the active route rendered into it.
 */
export function AppShell() {
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const user = useSession((state) => state.user);
  const forgetSession = useSession((state) => state.signOut);
  const saveAccount = useUpdateMyAccount();
  const client = useQueryClient();

  /**
   * End the session, and forget everything it fetched.
   *
   * @remarks
   * **The cache has to go with the token.** Dropping the credential alone
   * leaves every answer the last person received sitting in memory — their
   * account, their customers, their quotes, their notifications — and the next
   * person to sign in on the same browser is shown all of it until each query
   * happens to refetch. In an agency office one machine is used by several
   * people, so that is not a hypothetical.
   */
  const signOut = () => {
    forgetSession();
    client.clear();
  };
  const [languageAnchor, setLanguageAnchor] = useState<null | HTMLElement>(null);
  const [mode, setMode] = useState(
    () => window.localStorage.getItem('simple-erp.theme') ?? 'light',
  );

  const toggleMode = () => {
    const next = mode === 'light' ? 'dark' : 'light';
    window.localStorage.setItem('simple-erp.theme', next);
    setMode(next);
    // A full reload rather than lifting the mode into context: the theme is
    // read once at start-up, and this screen is not one a user toggles often.
    window.location.reload();
  };

  const visible = (entry: NavEntry): boolean => {
    if (entry.assistantOnly && !user?.hca_id) return false;
    if (entry.minimum && !hasAtLeast(user?.role, entry.minimum)) return false;
    return true;
  };

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }} data-testid="app-shell">
      <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
        <Toolbar variant="dense" sx={{ gap: 1 }}>
          <Box
            component="img"
            src={logo}
            alt={t('app.name')}
            sx={{ height: 28, mr: 2 }}
            data-testid="app-logo"
          />
          <Box sx={{ flexGrow: 1 }} />

          <NotificationBell />

          <Tooltip title={t('common.theme')}>
            <IconButton onClick={toggleMode} size="small" data-testid="theme-toggle">
              {mode === 'light' ? (
                <DarkModeIcon fontSize="small" />
              ) : (
                <LightModeIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>

          <Tooltip title={t('common.language')}>
            <IconButton
              onClick={(event) => setLanguageAnchor(event.currentTarget)}
              size="small"
              data-testid="language-menu"
            >
              <TranslateIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Menu
            anchorEl={languageAnchor}
            open={Boolean(languageAnchor)}
            onClose={() => setLanguageAnchor(null)}
          >
            {LANGUAGES.map((language) => (
              <MenuItem
                key={language.code}
                selected={i18n.language.startsWith(language.code)}
                onClick={() => {
                  setLanguage(language.code);
                  // Persisted as well as switched. The language decides what
                  // the quotes emailed to customers are written in, and those
                  // are generated by a background webhook that cannot read a
                  // preference living in this browser.
                  if (user) {
                    saveAccount.mutate({
                      full_name: user.full_name,
                      email: user.email,
                      language: language.code,
                    });
                  }
                  setLanguageAnchor(null);
                }}
                data-testid={`language-${language.code}`}
              >
                {language.label}
              </MenuItem>
            ))}
          </Menu>

          <Typography variant="body2" sx={{ mx: 1 }} data-testid="current-user">
            {user?.full_name}
          </Typography>
          <Tooltip title={t('auth.signOut')}>
            <IconButton onClick={signOut} size="small" data-testid="sign-out">
              <LogoutIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Toolbar>
      </AppBar>

      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          '& .MuiDrawer-paper': { width: DRAWER_WIDTH, boxSizing: 'border-box' },
        }}
      >
        <Toolbar variant="dense" />
        <Box sx={{ overflow: 'auto' }}>
          {NAV.map((group) => {
            const entries = group.entries.filter(visible);
            if (entries.length === 0) return null;
            return (
              <List
                key={group.headingKey}
                dense
                subheader={
                  <ListSubheader disableSticky>{t(group.headingKey)}</ListSubheader>
                }
              >
                {entries.map((entry) => (
                  <ListItemButton
                    key={entry.to}
                    component={RouterLink}
                    to={entry.to}
                    selected={location.pathname === entry.to}
                    data-testid={`nav-${entry.to.replace(/\//g, '-')}`}
                  >
                    <ListItemIcon sx={{ minWidth: 36 }}>
                      <AppIcon name={entry.icon} fontSize="small" />
                    </ListItemIcon>
                    <ListItemText primary={t(entry.labelKey)} />
                  </ListItemButton>
                ))}
                <Divider sx={{ mt: 1 }} />
              </List>
            );
          })}
        </Box>
      </Drawer>

      <Box
        component="main"
        sx={{ flexGrow: 1, p: 3, width: 0 }}
        data-testid="main-content"
      >
        <Toolbar variant="dense" />
        <Outlet />
      </Box>
    </Box>
  );
}
