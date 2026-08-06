import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request } from './client';
import { useSession } from '@/store/session';
import type {
  AvailabilitySlot,
  NewQuote,
  Certification,
  ContractType,
  Company,
  CompanyProfileUpdate,
  Customer,
  Hca,
  HcaPlanning,
  InterventionType,
  InterventionTypeUpdate,
  PricingRules,
  Notification,
  PlanningRun,
  User,
  UserRole,
  Quote,
  QuoteStatus,
} from './types';

/**
 * Every query key in one place.
 *
 * @remarks
 * A factory rather than string literals at the call sites: invalidating "the
 * quotes" after a mutation has to hit exactly the keys the lists were cached
 * under, and two components that spell the key slightly differently produce a
 * screen that does not refresh and no error anywhere.
 */
export const keys = {
  me: ['me'] as const,
  myAccount: ['me', 'account'] as const,
  myCompany: ['me', 'company'] as const,
  myProfile: ['me', 'hca'] as const,
  myCustomers: (search?: string) => ['me', 'customers', search ?? ''] as const,
  myQuotes: ['me', 'quotes'] as const,
  myPlanning: (hcaId: string, from: string, to: string) =>
    ['planning', hcaId, from, to] as const,
  allPlannings: (from: string, to: string) => ['planning', 'all', from, to] as const,
  quotes: (status?: QuoteStatus, search?: string) =>
    ['quotes', status ?? 'all', search ?? ''] as const,
  quote: (id: string) => ['quotes', id] as const,
  customer: (id: string) => ['customers', id] as const,
  customerQuotes: (id: string) => ['customers', id, 'quotes'] as const,
  users: ['users'] as const,
  planningRuns: ['planning', 'runs'] as const,
  hcas: (search?: string) => ['hcas', search ?? ''] as const,
  hca: (id: string) => ['hcas', id] as const,
  customers: (search?: string) => ['customers', search ?? ''] as const,
  interventionTypes: ['intervention-types'] as const,
  pricingRules: ['intervention-types', 'pricing-rules'] as const,
  notifications: ['notifications'] as const,
  unreadCount: ['notifications', 'unread'] as const,
};

/**
 * The caller's own account — the record every signed-in user has.
 *
 * @remarks
 * Distinct from `useMyProfile`, and deliberately so. An *account* is what signs
 * in; an *assistant record* is the person a manager schedules. Every caller has
 * the first, only assistants have the second, and conflating them is what left
 * managers and administrators looking at an error page where their details
 * should have been.
 */
export function useMyAccount() {
  return useQuery({
    queryKey: keys.myAccount,
    queryFn: () => request<User>('/api/v1/me/account'),
  });
}

/**
 * The agency the caller administers.
 *
 * @remarks
 * Read through `/me/company` rather than `/companies/{id}`: the identifier
 * comes from the credential, so the screen never holds one it could point at
 * the wrong tenant with.
 */
export function useMyCompany(enabled: boolean) {
  return useQuery({
    queryKey: keys.myCompany,
    queryFn: () => request<Company>('/api/v1/me/company'),
    enabled,
  });
}

/** Change the details of the agency the caller administers. */
export function useUpdateMyCompany() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CompanyProfileUpdate) =>
      request<Company>('/api/v1/me/company', { method: 'PUT', json: body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myCompany });
    },
  });
}

/**
 * The agency-wide rules a catalogue entry is priced against.
 *
 * @remarks
 * Read-only, and read from the running configuration rather than the database.
 * The screen needs them to say what an entry with no rate of its own costs,
 * and what VAT its category carries — a rate shown with neither is a number
 * with no meaning.
 */
export function usePricingRules() {
  return useQuery({
    queryKey: keys.pricingRules,
    queryFn: () => request<PricingRules>('/api/v1/intervention-types/pricing-rules'),
  });
}

/** Change what an intervention type is called, costs and covers. */
export function useUpdateInterventionType() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: InterventionTypeUpdate }) =>
      request<InterventionType>(`/api/v1/intervention-types/${id}`, {
        method: 'PATCH',
        json: body,
      }),
    onSuccess: () => {
      // Both keys: the catalog screen lists them, and the quote editor's
      // service dropdown is fed by the same query. A rate changed on one and
      // stale on the other is how a quote gets priced at yesterday's figure.
      void client.invalidateQueries({ queryKey: keys.interventionTypes });
    },
  });
}

/** Add an entry to the catalog. */
export function useCreateInterventionType() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: InterventionTypeUpdate & { code: string; name: string }) =>
      request<InterventionType>('/api/v1/intervention-types', {
        method: 'POST',
        json: body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.interventionTypes });
    },
  });
}

/** One customer, by identifier. */
export function useCustomer(customerId: string) {
  return useQuery({
    queryKey: keys.customer(customerId),
    queryFn: () => request<Customer>(`/api/v1/customers/${customerId}`),
    enabled: Boolean(customerId),
  });
}

/**
 * Every quote ever written for a customer.
 *
 * @remarks
 * Not filtered to the live ones here. Which quotes count as "ongoing" is a
 * reading of status and dates that the screen makes and explains; doing it in
 * the query would hide the rest of the history behind a rule nobody can see.
 */
export function useCustomerQuotes(customerId: string) {
  return useQuery({
    queryKey: keys.customerQuotes(customerId),
    queryFn: () => request<Quote[]>(`/api/v1/customers/${customerId}/quotes`),
    enabled: Boolean(customerId),
  });
}

/** End a running arrangement on a given day, repricing it. */
export function useInterruptQuote() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ quoteId, lastDay }: { quoteId: string; lastDay: string }) =>
      request<Quote>(`/api/v1/quotes/${quoteId}/interrupt`, {
        method: 'POST',
        json: { last_day: lastDay },
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['quotes'] });
      void client.invalidateQueries({ queryKey: ['customers'] });
    },
  });
}

/** Turn a quote's renewal on or off. */
export function useSetAutoRenew() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ quoteId, enabled }: { quoteId: string; enabled: boolean }) =>
      request<Quote>(`/api/v1/quotes/${quoteId}/auto-renew?enabled=${enabled}`, {
        method: 'PATCH',
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['quotes'] });
      void client.invalidateQueries({ queryKey: ['customers'] });
    },
  });
}

/** Change the caller's own display name and sign-in address. */
export function useUpdateMyAccount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { full_name: string; email: string }) =>
      request<User>('/api/v1/me/account', { method: 'PATCH', json: body }),
    onSuccess: () => {
      // Both: the account screen reads the query, and the top bar and the role
      // guards read the session. Refreshing one would leave the other showing
      // the old name until the next reload.
      void client.invalidateQueries({ queryKey: keys.myAccount });
      void useSession.getState().refresh();
    },
  });
}

/**
 * The caller's own assistant record, when they have one.
 *
 * @remarks
 * `enabled` is load-bearing rather than an optimisation. A manager's account is
 * bound to no assistant record, so this request answers 403 for them — and an
 * unconditional query would put the account screen into its error state for
 * every manager and administrator in the agency.
 */
export function useMyProfile(hcaId?: string | null) {
  return useQuery({
    queryKey: keys.myProfile,
    queryFn: () => request<Hca>('/api/v1/me/hca'),
    enabled: Boolean(hcaId),
  });
}

/** The caller's own customer portfolio. */
export function useMyCustomers(search?: string) {
  return useQuery({
    queryKey: keys.myCustomers(search),
    queryFn: () =>
      request<Customer[]>(
        `/api/v1/me/customers${search ? `?search=${encodeURIComponent(search)}` : ''}`,
      ),
  });
}

/** The quotes the caller wrote. */
export function useMyQuotes() {
  return useQuery({
    queryKey: keys.myQuotes,
    queryFn: () => request<Quote[]>('/api/v1/me/quotes'),
  });
}

/** One assistant's diary over a period. */
export function usePlanning(hcaId: string | null, from: string, to: string) {
  return useQuery({
    queryKey: keys.myPlanning(hcaId ?? '', from, to),
    enabled: Boolean(hcaId),
    queryFn: () =>
      request<HcaPlanning>(
        `/api/v1/planning/hcas/${hcaId}?period_start=${from}&period_end=${to}`,
      ),
  });
}

/** Every assistant's diary over a period. */
export function useAllPlannings(from: string, to: string) {
  return useQuery({
    queryKey: keys.allPlannings(from, to),
    queryFn: () =>
      request<HcaPlanning[]>(
        `/api/v1/planning/hcas?period_start=${from}&period_end=${to}`,
      ),
  });
}

/**
 * Every account in the agency.
 *
 * @param enabled - Whether to ask at all.
 * @returns The query.
 *
 * @remarks
 * The route is administrator-only, so a manager asking gets a 403. The caller
 * passes `false` rather than letting it fail quietly — a failed query renders
 * as "no accounts", which reads as a fact about the agency rather than about
 * the reader's permissions.
 */
export function useUsers(enabled = true) {
  return useQuery({
    queryKey: keys.users,
    queryFn: () => request<User[]>('/api/v1/users?size=500'),
    enabled,
  });
}

/**
 * Change what an account is allowed to do.
 *
 * @returns The mutation.
 *
 * @remarks
 * The account list *and* the workforce are invalidated. A promotion changes the
 * role shown beside an assistant on the workforce screen, and leaving that
 * stale is how somebody promotes the same person twice.
 */
export function usePromoteUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: UserRole }) =>
      request<User>(`/api/v1/users/${userId}/promote`, {
        method: 'POST',
        json: { role },
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.users });
      void client.invalidateQueries({ queryKey: ['hcas'] });
    },
  });
}

/**
 * Create a quote.
 *
 * @returns The mutation.
 *
 * @remarks
 * The server prices the lines it receives, so nothing here computes amounts —
 * a figure calculated in the browser is a figure that disagrees with the
 * catalogue the moment a rate changes.
 */
export function useCreateQuote() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (quote: NewQuote) =>
      request<Quote>('/api/v1/quotes', { method: 'POST', json: quote }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['quotes'] });
    },
  });
}

/**
 * The planning runs, newest first.
 *
 * @param polling - Whether to keep asking while one is in flight.
 * @param enabled - Whether to ask at all; the route is administrator-only.
 * @returns The query.
 */
export function usePlanningRuns(polling = false, enabled = true) {
  return useQuery({
    queryKey: keys.planningRuns,
    queryFn: () => request<PlanningRun[]>('/api/v1/planning/runs?size=20'),
    // Administrator-only, like starting one. A manager asking gets a 403, and
    // a failed query renders as "no runs" — which reads as a fact about the
    // agency rather than about the reader.
    enabled,
    // A solve takes up to thirty seconds on a worker, so the screen has to ask
    // again rather than leave the operator wondering. Only while one is running:
    // polling a finished run for ever is a request every two seconds, all day.
    refetchInterval: polling ? 2000 : false,
  });
}

/**
 * Ask for a planning to be computed.
 *
 * @returns The mutation.
 *
 * @remarks
 * Answers 202, not 200: the run is queued on the broker and solved by a worker.
 * What comes back is a `pending` run to watch, not a planning.
 */
export function useStartPlanningRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ from, to }: { from: string; to: string }) =>
      request<PlanningRun>(
        `/api/v1/planning/runs?period_start=${from}&period_end=${to}`,
        { method: 'POST' },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.planningRuns });
    },
  });
}

/**
 * Cancel one visit, and stop billing for it.
 *
 * @returns The mutation.
 *
 * @remarks
 * Answers 202 with the replan it queued, because cancelling a visit changes
 * what the solver has to place. The quote is already repriced by the time this
 * resolves; the calendar catches up when the worker finishes, which is why the
 * planning runs are invalidated as well as the plannings themselves.
 */
export function useDeleteIntervention() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, from, to }: { id: string; from: string; to: string }) =>
      request<PlanningRun>(
        `/api/v1/planning/interventions/${id}?period_start=${from}&period_end=${to}`,
        { method: 'DELETE' },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['planning'] });
      void client.invalidateQueries({ queryKey: ['quotes'] });
    },
  });
}

/**
 * Sell one visit as a different service, and reprice its quote.
 *
 * @returns The mutation.
 *
 * @remarks
 * No replan follows: the service changes what the hour costs, not when it
 * happens, so every constraint the solver placed it under still holds. The
 * plannings are still invalidated — the visit's label follows the catalogue
 * entry, and the calendar would otherwise go on naming the old service.
 */
export function useChangeInterventionType() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, typeId }: { id: string; typeId: string }) =>
      request<Quote>(`/api/v1/planning/interventions/${id}/type`, {
        method: 'PATCH',
        json: { intervention_type_id: typeId },
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['planning'] });
      void client.invalidateQueries({ queryKey: ['quotes'] });
    },
  });
}

/** Quotes, optionally narrowed to one status. */
export function useQuotes(status?: QuoteStatus) {
  return useQuery({
    queryKey: keys.quotes(status),
    queryFn: () =>
      request<Quote[]>(`/api/v1/quotes?size=200${status ? `&status=${status}` : ''}`),
  });
}

/** The workforce. */
export function useHcas(search?: string) {
  return useQuery({
    queryKey: keys.hcas(search),
    queryFn: () =>
      request<Hca[]>(
        `/api/v1/hcas?size=200${search ? `&search=${encodeURIComponent(search)}` : ''}`,
      ),
  });
}

/** The people served. */
export function useCustomers(search?: string) {
  return useQuery({
    queryKey: keys.customers(search),
    queryFn: () =>
      request<Customer[]>(
        `/api/v1/customers?size=200${
          search ? `&search=${encodeURIComponent(search)}` : ''
        }`,
      ),
  });
}

/** The service catalog. */
export function useInterventionTypes(includeInactive = false) {
  return useQuery({
    // Retired entries are part of the key. Without them the catalogue screen
    // and the quote editor would share one cache entry holding whichever list
    // was fetched first — and a quote could then be built from a service the
    // agency has stopped selling.
    queryKey: [...keys.interventionTypes, includeInactive] as const,
    queryFn: () =>
      request<InterventionType[]>(
        `/api/v1/intervention-types?size=200&include_inactive=${includeInactive}`,
      ),
  });
}

/** The caller's notifications. */
export function useNotifications() {
  return useQuery({
    queryKey: keys.notifications,
    queryFn: () => request<Notification[]>('/api/v1/notifications?size=100'),
  });
}

/**
 * How many notifications the caller has not read.
 *
 * No poll sits behind this. The event stream reports `ready` on connect and on
 * every reconnect, which refetches it — so a dropped stream catches up when it
 * comes back rather than on the next tick of a timer.
 */
export function useUnreadCount() {
  return useQuery({
    queryKey: keys.unreadCount,
    queryFn: () => request<{ unread: number }>('/api/v1/notifications/unread-count'),
  });
}

/** Submit one of the caller's own drafts for validation. */
export function useSubmitQuote() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (quoteId: string) =>
      request<Quote>(`/api/v1/me/quotes/${quoteId}/submit`, { method: 'POST' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myQuotes });
    },
  });
}

/** Approve a submitted quote. */
export function useValidateQuote() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (quoteId: string) =>
      request<Quote>(`/api/v1/quotes/${quoteId}/validate`, { method: 'POST' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['quotes'] });
      void client.invalidateQueries({ queryKey: keys.notifications });
    },
  });
}

/**
 * Issue a hand-written draft to the customer.
 *
 * @returns The mutation.
 *
 * @remarks
 * Sending accepts the quote server-side, so the row leaves the draft tab for
 * the accepted one and its visits enter the next planning run. The planning
 * queries are invalidated for that reason: a schedule on screen was computed
 * without these hours.
 */
export function useSendQuote() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (quoteId: string) =>
      request<Quote>(`/api/v1/quotes/${quoteId}/send`, { method: 'POST' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['quotes'] });
      void client.invalidateQueries({ queryKey: ['planning'] });
    },
  });
}

/** Send a submitted quote back to its author. */
export function useRefuseQuote() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (quoteId: string) =>
      request<Quote>(`/api/v1/quotes/${quoteId}/refuse-validation`, { method: 'POST' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['quotes'] });
    },
  });
}

/**
 * Rewrite a draft quote's services and reprice it.
 *
 * @param scope - `manager` saves through the agency-wide route; `own` through
 *   the self-service one, which the server narrows to the caller's own quotes
 *   against the stored author.
 *
 * @remarks
 * The scope decides the *endpoint*, not the permission. A caller who picked
 * `manager` without the role is refused by the guard, and one who picked `own`
 * on somebody else's quote is refused by the authorship check — so the choice
 * here is about which surface to use, never about what is allowed.
 */
export function useReplaceQuoteLines(scope: 'manager' | 'own') {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ quoteId, quote }: { quoteId: string; quote: Partial<Quote> }) =>
      request<Quote>(
        scope === 'manager'
          ? `/api/v1/quotes/${quoteId}/lines`
          : `/api/v1/me/quotes/${quoteId}/lines`,
        { method: 'PUT', json: quote },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['quotes'] });
      void client.invalidateQueries({ queryKey: keys.myQuotes });
    },
  });
}

/** Change the caller's own contact details, address and licence. */
export function useUpdateMyProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: unknown) =>
      request<Hca>('/api/v1/me/hca', { method: 'PATCH', json: body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myProfile });
    },
  });
}

/**
 * Replace the caller's own photograph.
 *
 * @remarks
 * Sent as multipart, never as a URL. The API detects the content type from the
 * file's magic bytes rather than trusting the header, so the `Content-Type` is
 * deliberately left for the browser to set with its boundary.
 */
export function useUploadMyPhoto() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append('photo', file);
      return request<Hca>('/api/v1/me/hca/photo', { method: 'PUT', body });
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myProfile });
    },
  });
}

/** Remove the caller's own photograph. */
export function useRemoveMyPhoto() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => request<Hca>('/api/v1/me/hca/photo', { method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myProfile });
    },
  });
}

/**
 * Change an assistant's contract type and qualifications.
 *
 * @remarks
 * The manager-gated route, used here for a manager editing their *own* record.
 * The self-service payload deliberately has no such fields — so rather than
 * widening it, the screen calls the endpoint that already exists and is already
 * guarded. A manager editing themselves goes through exactly the same check as
 * a manager editing anybody else.
 */
export function useUpdateEmployment(hcaId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      contract_type: ContractType;
      certifications: Certification[];
    }) =>
      request<Hca>(`/api/v1/hcas/${hcaId}/employment`, {
        method: 'PATCH',
        json: body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myProfile });
      void client.invalidateQueries({ queryKey: ['hcas'] });
    },
  });
}

/** Declare a period the caller cannot work. */
export function useAddAbsence(hcaId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (slot: Omit<AvailabilitySlot, 'id'>) =>
      request<AvailabilitySlot>(`/api/v1/hcas/${hcaId}/availability`, {
        method: 'POST',
        json: slot,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myProfile });
    },
  });
}

/** Withdraw a declared absence. */
export function useRemoveAbsence(hcaId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (slotId: string) =>
      request<void>(`/api/v1/hcas/${hcaId}/availability/${slotId}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myProfile });
    },
  });
}

/** Mark every notification read. */
export function useMarkAllRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      request<{ marked: number }>('/api/v1/notifications/read-all', { method: 'POST' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.notifications });
      void client.invalidateQueries({ queryKey: keys.unreadCount });
    },
  });
}
