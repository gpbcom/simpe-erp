import { useEffect, useMemo, useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import { useTranslation } from 'react-i18next';
import { AppShell } from '@/components/layout/AppShell';
import { LoginPage } from '@/features/auth/LoginPage';
import { RegisterCompanyPage } from '@/features/auth/RegisterCompanyPage';
import { ChangePasswordPage } from '@/features/auth/ChangePasswordPage';
import { MyAccountPage } from '@/features/me/MyAccountPage';
import { CompanyPage } from '@/features/company/CompanyPage';
import { CustomersPage } from '@/features/customers/CustomersPage';
import { CertificationsPage } from '@/features/certifications/CertificationsPage';
import { SkillsPage } from '@/features/skills/SkillsPage';
import { InterventionTypesPage } from '@/features/catalog/InterventionTypesPage';
import { MyCustomersPage } from '@/features/me/MyCustomersPage';
import { MyPlanningPage } from '@/features/me/MyPlanningPage';
import { MyQuotesPage } from '@/features/me/MyQuotesPage';
import { QuotesPage } from '@/features/quotes/QuotesPage';
import { HcasPage } from '@/features/hcas/HcasPage';
import { InterventionMapPage } from '@/features/map/InterventionMapPage';
import { NotificationsPage } from '@/features/notifications/NotificationsPage';
import { PlanningSettingsPage } from '@/features/plannings/PlanningSettingsPage';
import { TeamPlanningPage } from '@/features/plannings/TeamPlanningPage';
import { buildTheme } from '@/theme/theme';
import { hasAtLeast, useSession } from '@/store/session';
import type { UserRole } from '@/api/types';

interface GuardProps {
  /** The lowest role that may see the route. */
  minimum: UserRole;
  /** What to render when the check passes. */
  children: React.ReactNode;
}

/**
 * Hide a route from a role that may not use it.
 *
 * @param props - The minimum role, and the route.
 * @returns The route, or a redirect.
 *
 * @remarks
 * A convenience, not a control. The server checks every request regardless —
 * anything decided here can be edited in a browser console, so this exists to
 * keep an assistant from landing on a screen that would only show them errors.
 */
function RoleRoute({ minimum, children }: GuardProps) {
  const user = useSession((state) => state.user);
  return hasAtLeast(user?.role, minimum) ? (
    <>{children}</>
  ) : (
    <Navigate to="/" replace />
  );
}

/**
 * The application.
 *
 * @returns The rendered application.
 */
export function App() {
  const { i18n } = useTranslation();
  const user = useSession((state) => state.user);
  const loading = useSession((state) => state.loading);
  const restore = useSession((state) => state.restore);
  const [founding, setFounding] = useState(false);

  useEffect(() => {
    void restore();
  }, [restore]);

  const theme = useMemo(() => {
    const mode = (window.localStorage.getItem('simple-erp.theme') ?? 'light') as
      'light' | 'dark';
    return buildTheme(mode, i18n.language);
  }, [i18n.language]);

  const home = hasAtLeast(user?.role, 'manager') ? '/quotes' : '/me/planning';

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {loading ? (
        <Box sx={{ display: 'grid', placeItems: 'center', minHeight: '100vh' }}>
          <CircularProgress />
        </Box>
      ) : !user ? (
        // Two screens rather than a route, because neither is reachable
        // once signed in and the router below only exists for a session.
        founding ? (
          <RegisterCompanyPage onCancel={() => setFounding(false)} />
        ) : (
          <LoginPage onRegisterCompany={() => setFounding(true)} />
        )
      ) : user.must_change_password ? (
        // Nothing else is reachable while the flag is set: the server answers
        // 403 on every other route, so routing anywhere else would show a
        // screen full of errors.
        <ChangePasswordPage />
      ) : (
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<Navigate to={home} replace />} />
            <Route path="/me" element={<MyAccountPage />} />
            <Route path="/me/planning" element={<MyPlanningPage />} />
            <Route path="/me/customers" element={<MyCustomersPage />} />
            <Route path="/me/quotes" element={<MyQuotesPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route
              path="/quotes"
              element={
                <RoleRoute minimum="manager">
                  <QuotesPage />
                </RoleRoute>
              }
            />
            <Route
              path="/hcas"
              element={
                <RoleRoute minimum="manager">
                  <HcasPage />
                </RoleRoute>
              }
            />
            <Route
              path="/map"
              element={
                <RoleRoute minimum="manager">
                  <InterventionMapPage />
                </RoleRoute>
              }
            />
            <Route
              path="/plannings"
              element={
                <RoleRoute minimum="manager">
                  <TeamPlanningPage />
                </RoleRoute>
              }
            />
            <Route
              path="/planning-settings"
              element={
                <RoleRoute minimum="manager">
                  <PlanningSettingsPage />
                </RoleRoute>
              }
            />
            <Route
              path="/customers"
              element={
                <RoleRoute minimum="manager">
                  <CustomersPage />
                </RoleRoute>
              }
            />
            <Route
              path="/intervention-types"
              element={
                <RoleRoute minimum="manager">
                  <InterventionTypesPage />
                </RoleRoute>
              }
            />
            <Route
              path="/certifications"
              element={
                <RoleRoute minimum="manager">
                  <CertificationsPage />
                </RoleRoute>
              }
            />
            <Route
              path="/skills"
              element={
                <RoleRoute minimum="manager">
                  <SkillsPage />
                </RoleRoute>
              }
            />
            <Route
              path="/company"
              element={
                <RoleRoute minimum="admin">
                  <CompanyPage />
                </RoleRoute>
              }
            />
            <Route path="*" element={<Navigate to={home} replace />} />
          </Route>
        </Routes>
      )}
    </ThemeProvider>
  );
}
