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
  return user?.role === 'customer' ? (
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
        // **Routed, where this used to be two pieces of state.** The landing
        // page has to be linkable and has to survive a sign-out, and a
        // boolean cannot express "somewhere to come back to".
        //
        // The landing page is named, and the sign-in form is the fallback —
        // deliberately that way round. Somebody arriving at the root, or
        // returning here after signing out, is being asked what this is;
        // somebody whose session expired on `/quotes` is not, and putting the
        // product tour in front of them would cost them the click that gets
        // them back to work.
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
        // Nothing else is reachable while the flag is set: the server answers
        // 403 on every other route, so routing anywhere else would show a
        // screen full of errors.
        <ChangePasswordPage />
      ) : (
        <Routes>
          {/* Outside the shell on purpose: the navigation rail and the
              account menu mean nothing on a page that describes the product,
              and the hero needs the full width. */}
          <Route path="/welcome" element={<WelcomePage />} />
          <Route element={<AppShell />}>
            <Route path="/" element={<Navigate to={home} replace />} />
            <Route path="/me" element={<MyAccountPage />} />
            <Route path="/me/planning" element={<MyPlanningPage />} />
            <Route path="/me/customers" element={<MyCustomersPage />} />
            <Route path="/me/quotes" element={<MyQuotesPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            {/* The household's own space. Behind `CustomerRoute`, which
                compares by identity — a customer is a different axis rather
                than a lower rung, so `RoleRoute minimum="customer"` does not
                even type-check. */}
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
            <Route
              path="/plannings"
              element={
                <RoleRoute minimum="manager">
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
            <Route path="*" element={<Navigate to={home} replace />} />
          </Route>
        </Routes>
      )}
    </ThemeProvider>
  );
}
