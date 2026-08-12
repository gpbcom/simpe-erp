import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import Container from '@mui/material/Container';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import LoginIcon from '@mui/icons-material/Login';
import LogoutIcon from '@mui/icons-material/Logout';
import { alpha, useTheme } from '@mui/material/styles';
import { AppIcon } from '@/components/icons/AppIcon';
import type { AppIconName } from '@/components/icons/AppIcon';
import { BRAND } from '@/theme/palette';
import { useSession } from '@/store/session';
import logo from '@/assets/brand/logo-full.svg';

/** One capability, as a card in the grid. */
interface Feature {
  /** Glyph from the application's own set. */
  icon: AppIconName;
  /** Translation key of the heading. */
  title: string;
  /** Translation key of the paragraph. */
  body: string;
}

/**
 * What the application does, in the order the work flows through it.
 *
 * @remarks
 * Ordered as the agency experiences it — quote, approve, plan, deliver, bill —
 * rather than grouped by screen. Somebody deciding whether this software fits
 * their agency is asking "does it do my job", not "how many pages are there".
 */
const FEATURES: Feature[] = [
  { icon: 'quote', title: 'welcome.quoting', body: 'welcome.quotingBody' },
  {
    icon: 'quoteValidate',
    title: 'welcome.validation',
    body: 'welcome.validationBody',
  },
  { icon: 'planning', title: 'welcome.planning', body: 'welcome.planningBody' },
  { icon: 'hca', title: 'welcome.workforce', body: 'welcome.workforceBody' },
  {
    icon: 'certification',
    title: 'welcome.qualifications',
    body: 'welcome.qualificationsBody',
  },
  { icon: 'customer', title: 'welcome.customers', body: 'welcome.customersBody' },
  { icon: 'mapPin', title: 'welcome.map', body: 'welcome.mapBody' },
  // The price-tag glyph, not the download tray: `export` reads as "get a
  // file", and this card is about money owed.
  {
    icon: 'interventionType',
    title: 'welcome.billing',
    body: 'welcome.billingBody',
  },
  {
    icon: 'notification',
    title: 'welcome.notifications',
    body: 'welcome.notificationsBody',
  },
];

/** What each role sees when they sign in. */
const ROLES: Feature[] = [
  { icon: 'hca', title: 'welcome.forAssistant', body: 'welcome.forAssistantBody' },
  { icon: 'dashboard', title: 'welcome.forManager', body: 'welcome.forManagerBody' },
  {
    icon: 'company',
    title: 'welcome.forAdministrator',
    body: 'welcome.forAdministratorBody',
  },
];

/**
 * The public landing page: what the application does, and a way in.
 *
 * @returns The rendered page.
 *
 * @remarks
 * Rendered **outside** `AppShell`, deliberately. The shell is a signed-in
 * chrome — navigation rail, notification bell, account menu — and none of it
 * means anything to somebody who has not signed in yet. Full-bleed also lets
 * the hero use the brand teal edge to edge, which a page inset into the shell
 * cannot.
 *
 * **One button, two meanings.** Signed out it reads "Sign in" and goes to the
 * sign-in screen; signed in it reads "Sign out" and returns here. That is the
 * whole session control on this page: the page itself is public, so the button
 * describes what the visitor can do next rather than who they are.
 *
 * The palette is the application's own — teal for the product, amber for
 * anything waiting on a person — and the glyphs are the same `AppIcon` set the
 * signed-in screens use. A landing page drawn with a different icon library is
 * how a product starts looking like two products.
 */
export function WelcomePage() {
  const { t } = useTranslation();
  const theme = useTheme();
  const navigate = useNavigate();
  const user = useSession((state) => state.user);
  const signOut = useSession((state) => state.signOut);

  const dark = theme.palette.mode === 'dark';

  const enter = () => {
    if (!user) {
      void navigate('/login');
      return;
    }
    // Sign out, then stay here — and navigate explicitly rather than relying
    // on the re-render. Signed out, `/welcome` is one of only two paths that
    // still resolve to this page; every other one falls to the sign-in form,
    // so ending the session without moving would show the form to somebody
    // who was reading about the product.
    signOut();
    void navigate('/welcome');
  };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      {/* ── Hero ─────────────────────────────────────────────────────── */}
      <Box
        sx={{
          // A quiet gradient rather than a flat block: the mark's own teal
          // into its darker shade, so the header reads as the product's
          // colour and not as a coloured rectangle placed on top of it.
          background: `linear-gradient(135deg, ${BRAND.primary} 0%, ${BRAND.primaryDark} 100%)`,
          color: '#fff',
          px: 2,
          py: { xs: 6, md: 10 },
        }}
        data-testid="welcome-hero"
      >
        <Container maxWidth="lg">
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            sx={{ mb: { xs: 4, md: 6 } }}
          >
            <Box
              component="img"
              src={logo}
              alt="SimpleERP"
              sx={{
                height: 36,
                // The mark is drawn for a light ground; on the teal it is
                // inverted rather than given a second file to keep in step.
                filter: 'brightness(0) invert(1)',
              }}
            />
            <Button
              variant="contained"
              color="inherit"
              startIcon={user ? <LogoutIcon /> : <LoginIcon />}
              onClick={enter}
              data-testid="welcome-session-button"
              sx={{
                bgcolor: '#fff',
                color: BRAND.primaryDark,
                '&:hover': { bgcolor: alpha('#fff', 0.88) },
              }}
            >
              {user ? t('welcome.signOut') : t('welcome.signIn')}
            </Button>
          </Stack>

          <Stack spacing={2} sx={{ maxWidth: 720 }}>
            <Chip
              label={t('welcome.kicker')}
              size="small"
              sx={{
                alignSelf: 'flex-start',
                bgcolor: alpha('#fff', 0.16),
                color: '#fff',
                fontWeight: 600,
              }}
            />
            <Typography variant="h1" sx={{ fontSize: { xs: '2rem', md: '2.75rem' } }}>
              {t('welcome.title')}
            </Typography>
            <Typography sx={{ fontSize: '1.05rem', opacity: 0.92 }}>
              {t('welcome.subtitle')}
            </Typography>
            {user ? (
              <Typography
                variant="body2"
                sx={{ opacity: 0.85 }}
                data-testid="welcome-signed-in-as"
              >
                {t('welcome.signedInAs', { name: user.full_name })}
              </Typography>
            ) : null}
          </Stack>
        </Container>
      </Box>

      {/* ── What it does ─────────────────────────────────────────────── */}
      <Container maxWidth="lg" sx={{ py: { xs: 5, md: 8 } }}>
        <Typography variant="h2" sx={{ mb: 1 }}>
          {t('welcome.featuresTitle')}
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 4, maxWidth: 640 }}>
          {t('welcome.featuresLead')}
        </Typography>

        <Grid container spacing={2.5} data-testid="welcome-features">
          {FEATURES.map((feature) => (
            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={feature.title}>
              <Card
                variant="outlined"
                sx={{
                  height: '100%',
                  transition: 'border-color .15s, transform .15s',
                  '&:hover': {
                    borderColor: BRAND.primary,
                    transform: 'translateY(-2px)',
                  },
                }}
                data-testid={`feature-${feature.icon}`}
              >
                <CardContent>
                  <Box
                    sx={{
                      width: 40,
                      height: 40,
                      borderRadius: 1.5,
                      display: 'grid',
                      placeItems: 'center',
                      color: BRAND.primary,
                      bgcolor: alpha(BRAND.primary, dark ? 0.24 : 0.1),
                      mb: 1.5,
                    }}
                  >
                    <AppIcon name={feature.icon} />
                  </Box>
                  <Typography variant="h3" sx={{ mb: 0.5 }}>
                    {t(feature.title)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {t(feature.body)}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Container>

      {/* ── Who it is for ────────────────────────────────────────────── */}
      <Box
        sx={{ bgcolor: alpha(BRAND.primary, dark ? 0.12 : 0.05), py: { xs: 5, md: 8 } }}
      >
        <Container maxWidth="lg">
          <Typography variant="h2" sx={{ mb: 1 }}>
            {t('welcome.rolesTitle')}
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 4, maxWidth: 640 }}>
            {t('welcome.rolesLead')}
          </Typography>

          <Grid container spacing={2.5} data-testid="welcome-roles">
            {ROLES.map((role) => (
              <Grid size={{ xs: 12, md: 4 }} key={role.title}>
                <Stack direction="row" spacing={1.5} data-testid={`role-${role.icon}`}>
                  <Box sx={{ color: BRAND.secondary, pt: 0.25 }}>
                    <AppIcon name={role.icon} />
                  </Box>
                  <Box>
                    <Typography variant="h3" sx={{ mb: 0.5 }}>
                      {t(role.title)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t(role.body)}
                    </Typography>
                  </Box>
                </Stack>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* ── Closing call to action ───────────────────────────────────── */}
      <Container maxWidth="lg" sx={{ py: { xs: 5, md: 8 }, textAlign: 'center' }}>
        <Typography variant="h2" sx={{ mb: 1 }}>
          {user ? t('welcome.ctaSignedIn') : t('welcome.cta')}
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 3 }}>
          {user ? t('welcome.ctaSignedInBody') : t('welcome.ctaBody')}
        </Typography>
        <Button
          variant="contained"
          size="large"
          startIcon={user ? <LogoutIcon /> : <LoginIcon />}
          onClick={enter}
          data-testid="welcome-session-button-footer"
        >
          {user ? t('welcome.signOut') : t('welcome.signIn')}
        </Button>
      </Container>

      <Box
        sx={{
          borderTop: 1,
          borderColor: 'divider',
          py: 3,
          textAlign: 'center',
        }}
      >
        <Typography variant="body2" color="text.secondary">
          {t('welcome.footer')}
        </Typography>
      </Box>
    </Box>
  );
}
