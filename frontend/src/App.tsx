import { useEffect, useMemo, useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import { useTranslation } from 'react-i18next';
import { AppShell } from '@/components/layout/AppShell';
import { LoginPage } from '@/features/auth/LoginPage';
import { PortalBillsPage } from '@/features/portal/PortalBillsPage';
import { PortalPlanningPage } from '@/features/portal/PortalPlanningPage';
import { PortalProfilePage } from '@/features/portal/PortalProfilePage';
import { PortalQuotesPage } from '@/features/portal/PortalQuotesPage';
import { WelcomePage } from '@/features/welcome/WelcomePage';
import { RegisterCompanyPage } from '@/features/auth/RegisterCompanyPage';
import { ChangePasswordPage } from '@/features/auth/ChangePasswordPage';
import { MyAccountPage } from '@/features/me/MyAccountPage';
import { AgenciesPage } from '@/features/agencies/AgenciesPage';
import { CompanyPage } from '@/features/company/CompanyPage';
import { MyTeamPage } from '@/features/teams/MyTeamPage';
import { TeamsPage } from '@/features/teams/TeamsPage';
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
import { BillingSettingsPage } from '@/features/bills/BillingSettingsPage';
import { BillsPage } from '@/features/bills/BillsPage';
import { PlanningSettingsPage } from '@/features/plannings/PlanningSettingsPage';
import { TeamPlanningPage } from '@/features/plannings/TeamPlanningPage';
import { buildTheme } from '@/theme/theme';
import { hasAtLeast, useSession } from '@/store/session';
import type { StaffRole } from '@/store/session';

interface GuardProps {
  /**
   * The lowest **staff** role that may see the route.
   *
   * @remarks
   * `StaffRole`, not `UserRole`, so `minimum="customer"` is a compile error.
   * A customer is a different axis rather than a lower rung — see
   * `hasAtLeast`. The portal uses `CustomerRoute` below instead.
   */
  minimum: StaffRole;
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
 * Hide the household's own space from everybody else.
 *
 * @param props - The route to guard.
 * @returns The route, or a redirect.
 *
 * @remarks
 * **Compares by identity, and it cannot be written any other way.** A customer
 * is not a rung of the staff ladder — see `hasAtLeast`, whose `minimum` is
 * typed `StaffRole` precisely so `RoleRoute minimum="customer"` is a compile
 * error. Written that way it would admit every employee to a household's
 * calendar, address and invoices.
 *
 * A convenience, like `RoleRoute`: the server's `get_customer_user` is what
 * actually refuses staff, on every request.
 */
function CustomerRoute({ children }: { children: React.ReactNode }) {
  const user = useSession((state) => state.user);
  return user?.role === 'customer' ? <>{children}</> : <Navigate to="/" replace />;
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

  // Three landings, not two. A household has none of the staff screens, so
  // sending them to the assistant's diary would be a redirect loop through a
  // page that answers 403.
  const home =
    user?.role === 'customer'
      ? '/portal/planning'
      : hasAtLeast(user?.role, 'manager')
        ? '/quotes'
        : '/me/planning';

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {loading ? (
        <Box sx={{ display: 'grid', placeItems: 'center', minHeight: '100vh' }}>
          <CircularProgress />
        </Box>
      ) : !user ? (
        <Routes>
          <Route path="/" element={<WelcomePage />} />
          <Route path="/welcome" element={<WelcomePage />} />
          <Route
            path="/register-company"
            element={<RegisterCompanyPage onCancel={() => setFounding(false)} />}
          />
          <Route
            path="*"
            element={
              founding ? (
                <RegisterCompanyPage onCancel={() => setFounding(false)} />
              ) : (
                <LoginPage onRegisterCompany={() => setFounding(true)} />
              )
            }
          />
        </Routes>
      ) : user.must_change_password ? (
        <ChangePasswordPage />
      ) : (
        <Routes>
          {}
          <Route path="/welcome" element={<WelcomePage />} />
          <Route element={<AppShell />}>
            <Route path="/" element={<Navigate to={home} replace />} />
            <Route path="/me" element={<MyAccountPage />} />
            <Route path="/me/planning" element={<MyPlanningPage />} />
            <Route path="/me/customers" element={<MyCustomersPage />} />
            <Route path="/me/quotes" element={<MyQuotesPage />} />
            {}
            <Route path="/me/team" element={<MyTeamPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            {}
            <Route
              path="/portal/planning"
              element={
                <CustomerRoute>
                  <PortalPlanningPage />
                </CustomerRoute>
              }
            />
            <Route
              path="/portal/profile"
              element={
                <CustomerRoute>
                  <PortalProfilePage />
                </CustomerRoute>
              }
            />
            <Route
              path="/portal/quotes"
              element={
                <CustomerRoute>
                  <PortalQuotesPage />
                </CustomerRoute>
              }
            />
            <Route
              path="/portal/bills"
              element={
                <CustomerRoute>
                  <PortalBillsPage />
                </CustomerRoute>
              }
            />
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
            {}
            <Route
              path="/plannings"
              element={
                <RoleRoute minimum="hca">
                  <TeamPlanningPage />
                </RoleRoute>
              }
            />
            <Route
              path="/bills"
              element={
                <RoleRoute minimum="manager">
                  <BillsPage />
                </RoleRoute>
              }
            />
            <Route
              path="/billing-settings"
              element={
                <RoleRoute minimum="manager">
                  <BillingSettingsPage />
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
            {}
            <Route
              path="/agencies"
              element={
                <RoleRoute minimum="admin">
                  <AgenciesPage />
                </RoleRoute>
              }
            />
            <Route
              path="/teams"
              element={
                <RoleRoute minimum="admin">
                  <TeamsPage />
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
