import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request, requestBlob } from './client';
import { filterQuery } from '@/components/filters/entityFilter';
import type { EntityFilterRecord } from '@/components/filters/entityFilter';
import { saveBlob } from '@/utils/download';
import { useSession } from '@/store/session';
import type {
  Agency,
  AgencyBody,
  OrganisationMember,
  Team,
  TeamBody,
  TeamDocument,
  TeamDocumentConstraints,
  Bill,
  BillingPeriodicity,
  BillingRun,
  BillingSettings,
  BillStatus,
  AvailabilitySlot,
  NewQuote,
  NewQuoteLine,
  QuoteHeaderEdit,
  QuoteLinesEdit,
  Certification,
  CertificationType,
  CertificationTypeUpdate,
  Skill,
  SkillCreate,
  SkillType,
  SkillTypeUpdate,
  ContractType,
  Company,
  CompanyProfileUpdate,
  Customer,
  CustomerFilter,
  CustomerPlanning,
  CustomerProfileUpdate,
  NewCustomer,
  RegistrationStatus,
  Hca,
  Intervention,
  InterventionReschedule,
  HcaPlanning,
  InterventionType,
  Language,
  InterventionTypeUpdate,
  PricingRules,
  Notification,
  PlanningRun,
  PlanningSettings,
  User,
  UserRole,
  Weekday,
  Quote,
  QuoteReschedule,
  QuoteStatus,
  EInvoicingProvider,
  IntegrationCard,
  IntegrationCredentialsBody,
} from './types';

/**
 * Serialise a customer filter into a sorted query string.
 *
 * @param filter - The filter, or `undefined` for the whole book.
 * @returns The query string, without a leading `?`, empty when nothing narrows.
 *
 * @remarks
 * One function for two jobs — the request and the cache key — so the two can
 * never disagree about what a filter means. Two filters narrowing the same way
 * must produce the same string, which is why the fields are sorted rather than
 * walked in insertion order: `{city, search}` and `{search, city}` are the same
 * question and must not be fetched twice.
 *
 * `false` is kept and only `undefined` is dropped. A falsy check here would
 * turn "whose address failed to resolve" into "everybody", which looks like a
 * filter that does not work rather than a wrong one.
 */
export function customerFilterQuery(filter?: CustomerFilter): string {
  const entries = Object.entries(filter ?? {})
    .filter(([, value]) => value !== undefined && value !== '')
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([field, value]) => `${field}=${encodeURIComponent(String(value))}`);
  return entries.join('&');
}

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
  customerPlannings: (from: string, to: string) =>
    ['planning', 'customers', from, to] as const,
  customerPlanning: (customerId: string, from: string, to: string) =>
    ['planning', 'customers', customerId, from, to] as const,
  quotes: (status?: QuoteStatus, filter?: EntityFilterRecord) =>
    // `list` for the same reason the customer keys carry it: without it a
    // quote whose identifier happened to equal a filter string would share a
    // cache entry with the list itself.
    ['quotes', 'list', status ?? 'all', filterQuery(filter)] as const,
  quote: (id: string) => ['quotes', 'detail', id] as const,
  // `detail` is not decoration. Without it, `customer('')` — what the drawer
  // asks for while it is closed — is `['customers', '']`, which is exactly the
  // key the *unfiltered list* is cached under. A disabled query still reads
  // whatever sits at its key, so the drawer was handed the whole array and blew
  // up dereferencing `.address` on it, blanking the page on first load.
  customer: (id: string) => ['customers', 'detail', id] as const,
  customerQuotes: (id: string) => ['customers', 'detail', id, 'quotes'] as const,
  users: ['users'] as const,
  planningRuns: ['planning', 'runs'] as const,
  planningSettings: ['planning', 'settings'] as const,
  hcas: (search?: string, filter?: EntityFilterRecord) =>
    ['hcas', 'list', search ?? '', filterQuery(filter)] as const,
  hca: (id: string) => ['hcas', 'detail', id] as const,
  customers: (filter?: CustomerFilter) =>
    ['customers', 'list', customerFilterQuery(filter)] as const,
  interventionTypes: ['intervention-types'] as const,
  certificationTypes: ['certification-types'] as const,
  skillTypes: ['skill-types'] as const,
  pricingRules: ['intervention-types', 'pricing-rules'] as const,
  notifications: (filter?: EntityFilterRecord) =>
    ['notifications', 'list', filterQuery(filter)] as const,
  unreadCount: ['notifications', 'unread'] as const,
  bills: (filter?: EntityFilterRecord) =>
    ['bills', 'list', filterQuery(filter)] as const,
  bill: (id: string) => ['bills', 'detail', id] as const,
  billingRuns: ['billing', 'runs'] as const,
  billingRun: (id: string) => ['billing', 'runs', 'detail', id] as const,
  billingSettings: ['billing', 'settings'] as const,
  integrations: ['billing', 'integrations'] as const,
  portalProfile: ['portal', 'profile'] as const,
  portalPlanning: (from: string, to: string) =>
    ['portal', 'planning', from, to] as const,
  portalQuotes: ['portal', 'quotes'] as const,
  portalBills: ['portal', 'bills'] as const,
  agencies: ['agencies', 'list'] as const,
  agency: (id: string) => ['agencies', 'detail', id] as const,
  agencyMembers: (id: string) => ['agencies', 'detail', id, 'members'] as const,
  teams: ['teams', 'list'] as const,
  team: (id: string) => ['teams', 'detail', id] as const,
  teamMembers: (id: string) => ['teams', 'detail', id, 'members'] as const,
  teamDocuments: (id: string) => ['teams', 'detail', id, 'documents'] as const,
  teamDocumentConstraints: ['teams', 'document-constraints'] as const,
  myTeam: ['me', 'team'] as const,
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
 * Replace the agency's logo.
 *
 * @returns The mutation.
 *
 * @remarks
 * Sent as multipart, never as a URL. The API detects the content type from the
 * file's magic bytes rather than trusting the header, so the `Content-Type` is
 * deliberately left for the browser to set with its boundary.
 *
 * The response carries the updated agency, but the query is invalidated rather
 * than written into: the logo lands under a freshly generated key each time, so
 * the screen has to re-read to learn the new URL — an unchanged one behind a
 * changed image is how a browser keeps showing the old mark.
 */
export function useUploadCompanyLogo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append('logo', file);
      return request<Company>('/api/v1/me/company/logo', { method: 'PUT', body });
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myCompany });
    },
  });
}

/** Remove the agency's logo. */
export function useRemoveCompanyLogo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => request<Company>('/api/v1/me/company/logo', { method: 'DELETE' }),
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

/**
 * The qualifications the agency recognises.
 *
 * @param includeInactive - Whether retired entries are listed too.
 * @returns The query.
 *
 * @remarks
 * Readable by any signed-in caller, not just a manager: an assistant's own
 * account screen names the qualifications they hold, and without this it would
 * have to print `DEAES` at them and hope.
 */
export function useCertificationTypes(
  includeInactive = false,
  filter?: EntityFilterRecord,
) {
  const query = filterQuery(filter);
  return useQuery({
    queryKey: [...keys.certificationTypes, includeInactive, query] as const,
    queryFn: () =>
      request<CertificationType[]>(
        `/api/v1/certifications?size=500&include_inactive=${includeInactive}` +
          (query ? `&${query}` : ''),
      ),
  });
}

/** Add a qualification to the catalogue. */
export function useCreateCertificationType() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { code: string; label: string; description?: string | null }) =>
      request<CertificationType>('/api/v1/certifications', {
        method: 'POST',
        json: body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.certificationTypes });
    },
  });
}

/**
 * Change what a catalogue entry says.
 *
 * @returns The mutation.
 *
 * @remarks
 * `PATCH`, and the body carries no `code`. The code is what every stored
 * qualification and every service requirement is matched on, so renaming one
 * would disqualify its holders on the next planning run — the server refuses
 * it, and the form locks the input to say so before anybody tries.
 */
export function useUpdateCertificationType() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: CertificationTypeUpdate }) =>
      request<CertificationType>(`/api/v1/certifications/${id}`, {
        method: 'PATCH',
        json: body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.certificationTypes });
      void client.invalidateQueries({ queryKey: ['hcas'] });
    },
  });
}

/**
 * Remove a catalogue entry that nothing refers to.
 *
 * @returns The mutation.
 *
 * @remarks
 * Answers 409 when an assistant holds it or a service requires it, with both
 * counts in the message and retirement offered instead. No foreign key
 * protects those references, so letting the delete through would leave a
 * requirement pointing at nothing — which fails every planning run it touches.
 */
export function useDeleteCertificationType() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      request<void>(`/api/v1/certifications/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.certificationTypes });
    },
  });
}

/**
 * The skill catalogue.
 *
 * @returns The query, holding every skill the agency recognises.
 *
 * @remarks
 * Readable by any signed-in caller, and that matters more here than for the
 * qualifications: an assistant declares their own skills from their own
 * account screen, so this is the list they pick from. Retired entries are
 * hidden unless asked for, so the picker offers only what may still be
 * declared.
 */
export function useSkillTypes(includeInactive = false, filter?: EntityFilterRecord) {
  const query = filterQuery(filter);
  return useQuery({
    queryKey: [...keys.skillTypes, includeInactive, query] as const,
    queryFn: () =>
      request<SkillType[]>(
        `/api/v1/skills?size=500&include_inactive=${includeInactive}` +
          (query ? `&${query}` : ''),
      ),
  });
}

/**
 * Add a skill to the catalogue.
 *
 * @returns The mutation.
 *
 * @remarks
 * Manager-gated, even though the declarations are not. An assistant says what
 * they can do; what the agency is willing to recognise and plan against is the
 * agency's decision.
 */
export function useCreateSkillType() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { code: string; label: string; description?: string | null }) =>
      request<SkillType>('/api/v1/skills', {
        method: 'POST',
        json: body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.skillTypes });
    },
  });
}

/**
 * Change what a skill-catalogue entry says.
 *
 * @returns The mutation.
 *
 * @remarks
 * `PATCH`, and the body carries no `code`. The code is what every declared
 * skill and every service requirement is matched on, so renaming one would
 * un-skill its holders on the next planning run — the server refuses it, and
 * the form locks the input to say so before anybody tries.
 */
export function useUpdateSkillType() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: SkillTypeUpdate }) =>
      request<SkillType>(`/api/v1/skills/${id}`, {
        method: 'PATCH',
        json: body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.skillTypes });
      void client.invalidateQueries({ queryKey: ['hcas'] });
      void client.invalidateQueries({ queryKey: keys.myProfile });
    },
  });
}

/**
 * Remove a skill-catalogue entry that nothing refers to.
 *
 * @returns The mutation.
 *
 * @remarks
 * Answers 409 when an assistant has declared it or a service requires it, with
 * both counts in the message and retirement offered instead. No foreign key
 * protects those references, so letting the delete through would leave a
 * requirement pointing at nothing — which fails every planning run it touches.
 */
export function useDeleteSkillType() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      request<void>(`/api/v1/skills/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.skillTypes });
    },
  });
}

/**
 * Declare a skill about yourself.
 *
 * @returns The mutation.
 *
 * @remarks
 * The one planner-visible thing an assistant may write about their own record,
 * and the reason it is not the qualifications beside it: what somebody was
 * *awarded* is a manager's record, what they *can do* is their own. It takes
 * effect at once — every manager and administrator is notified rather than
 * asked to approve — so the calendars stop agreeing with the workforce until
 * the next run, which is why `planning` is invalidated too.
 */
export function useDeclareMySkill() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: SkillCreate) =>
      request<Skill>('/api/v1/me/hca/skills', { method: 'POST', json: body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myProfile });
      void client.invalidateQueries({ queryKey: ['hcas'] });
      void client.invalidateQueries({ queryKey: ['planning'] });
    },
  });
}

/**
 * Withdraw a skill you declared about yourself.
 *
 * @returns The mutation.
 *
 * @remarks
 * The assistant comes from the credential and is part of the server's lookup,
 * so knowing a skill identifier is not enough to strip a colleague of one. A
 * manager or an administrator removes anybody's through
 * {@link useRemoveSkill}.
 */
export function useWithdrawMySkill() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (skillId: string) =>
      request<void>(`/api/v1/me/hca/skills/${skillId}`, { method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myProfile });
      void client.invalidateQueries({ queryKey: ['hcas'] });
      void client.invalidateQueries({ queryKey: ['planning'] });
    },
  });
}

/**
 * Withdraw a skill an assistant declared, as a manager or an administrator.
 *
 * @returns The mutation.
 *
 * @remarks
 * The supervisors' half of the pair. A declaration needs no approval, so this
 * is the correction: somebody who believes a skill has been over-claimed can
 * remove it without waiting for its owner.
 */
export function useRemoveSkill() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ hcaId, skillId }: { hcaId: string; skillId: string }) =>
      request<void>(`/api/v1/hcas/${hcaId}/skills/${skillId}`, { method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['hcas'] });
      void client.invalidateQueries({ queryKey: keys.myProfile });
      void client.invalidateQueries({ queryKey: ['planning'] });
    },
  });
}

/**
 * Register a customer.
 *
 * @returns The mutation.
 *
 * @remarks
 * The whole `['customers']` prefix is invalidated rather than one key, because
 * the directory is cached per search term: a customer added while a filter is
 * typed would otherwise be absent from the list the manager is looking at, and
 * present the moment they clear the box.
 *
 * The call can take a second or two. The server geocodes the address while it
 * validates the payload, and an address the map does not know is still stored —
 * with the failure recorded on it — so this resolving is not the same as the
 * home being routable.
 */
export function useCreateCustomer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (customer: NewCustomer) =>
      request<Customer>('/api/v1/customers', { method: 'POST', json: customer }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['customers'] });
    },
  });
}

/**
 * Promote a prospect to an active customer.
 *
 * @returns The mutation.
 *
 * @remarks
 * **This is what puts a customer into the planning.** A prospect may already
 * hold accepted, priced work that every run has deliberately left out; nothing
 * about that work changes here, only the agency's agreement to deliver it.
 *
 * The customer's own key is invalidated as well as the prefix, because the
 * drawer showing the promote button reads `useCustomer` — leaving it stale
 * would keep the button on screen for somebody who is no longer a prospect.
 *
 * A 409 comes back if they were not a prospect. Two managers pressing at once
 * is the case: the second gets a refusal rather than a silent no-op, so nobody
 * is left wondering which press took effect.
 */
export function usePromoteCustomer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (customerId: string) =>
      request<Customer>(`/api/v1/customers/${customerId}/promote`, { method: 'POST' }),
    onSuccess: (customer) => {
      void client.invalidateQueries({ queryKey: ['customers'] });
      if (customer.id) {
        void client.invalidateQueries({ queryKey: keys.customer(customer.id) });
      }
    },
  });
}

/**
 * Change a customer's standing with the agency.
 *
 * @returns The mutation.
 *
 * @remarks
 * The general route, for the transitions promotion does not cover: stopping
 * somebody who has left, reinstating somebody who came back, and sending a
 * customer back to prospect when a signature turns out never to have arrived.
 * Promoting goes through {@link usePromoteCustomer} instead, so the one
 * transition with a rule has one place enforcing it.
 *
 * Stopping a customer does **not** cancel their scheduled visits; it stops the
 * next run planning new ones.
 */
export function useSetCustomerStatus() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      customerId,
      status,
    }: {
      customerId: string;
      status: RegistrationStatus;
    }) =>
      request<Customer>(`/api/v1/customers/${customerId}/status`, {
        method: 'PATCH',
        json: { registration_status: status },
      }),
    onSuccess: (customer) => {
      void client.invalidateQueries({ queryKey: ['customers'] });
      if (customer.id) {
        void client.invalidateQueries({ queryKey: keys.customer(customer.id) });
      }
    },
  });
}

/**
 * Give a customer their own invoicing granularity, or take it away.
 *
 * @returns The mutation.
 *
 * @remarks
 * A route of its own rather than a field on the customer PUT: the drawer holds
 * a record that may be minutes old, and sending the whole of it back would let
 * that stale copy overwrite an address somebody else corrected meanwhile.
 *
 * **`null` is a value, not an omission.** Sending it puts the customer back on
 * the agency's own rule, which is the only way an override comes off again.
 *
 * Nothing is re-issued. The change decides what the next generation run bills
 * them over, so the bill queries are deliberately **not** invalidated — an
 * invoice already written keeps the period it was written for.
 */
export function useSetCustomerBillingPeriodicity() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      customerId,
      periodicity,
    }: {
      customerId: string;
      periodicity: BillingPeriodicity | null;
    }) =>
      request<Customer>(`/api/v1/customers/${customerId}/billing-periodicity`, {
        method: 'PATCH',
        json: { periodicity },
      }),
    onSuccess: (customer) => {
      void client.invalidateQueries({ queryKey: ['customers'] });
      if (customer.id) {
        void client.invalidateQueries({ queryKey: keys.customer(customer.id) });
      }
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
    mutationFn: (body: { full_name: string; email: string; language: Language }) =>
      request<User>('/api/v1/me/account', { method: 'PATCH', json: body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myAccount });
      void useSession.getState().refresh();
    },
  });
}

/**
 * Replace the caller's own portrait.
 *
 * @returns The mutation.
 *
 * @remarks
 * Bound to the *account*, not to the assistant record, so a manager and an
 * administrator can set one too. The assistant-scoped route this replaces
 * (`PUT /me/hca/photo`, still there for any client that used it) answers 403
 * for them, which is what left them with no portrait at all.
 *
 * Sent as multipart, never as a URL. The API detects the content type from the
 * file's magic bytes rather than trusting the header, so the `Content-Type` is
 * deliberately left for the browser to set with its boundary.
 *
 * The assistant record's own query is invalidated as well: when the account is
 * bound to one, the server writes the same portrait there so the manager's map
 * pin follows.
 */
export function useUploadMyAccountPhoto() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append('photo', file);
      return request<User>('/api/v1/me/account/photo', { method: 'PUT', body });
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myAccount });
      void client.invalidateQueries({ queryKey: keys.myProfile });
      void client.invalidateQueries({ queryKey: ['hcas'] });
      void useSession.getState().refresh();
    },
  });
}

/** Remove the caller's own portrait. */
export function useRemoveMyAccountPhoto() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => request<User>('/api/v1/me/account/photo', { method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myAccount });
      void client.invalidateQueries({ queryKey: keys.myProfile });
      void client.invalidateQueries({ queryKey: ['hcas'] });
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

/**
 * Every assistant's diary over a period.
 *
 * @param from - First day, inclusive.
 * @param to - Last day, inclusive.
 * @param enabled - Whether to fetch at all.
 *
 * @remarks
 * Disabled rather than left to 403 when the caller may not read it. A failed
 * query renders as an empty roster, which states a fact about the agency when
 * it is really one about the reader's permissions.
 */
export function useAllPlannings(from: string, to: string, enabled = true) {
  return useQuery({
    queryKey: keys.allPlannings(from, to),
    enabled,
    queryFn: () =>
      request<HcaPlanning[]>(
        `/api/v1/planning/hcas?period_start=${from}&period_end=${to}`,
      ),
  });
}

/**
 * Every household's care the caller may see, over a period.
 *
 * @param from - First day, inclusive.
 * @param to - Last day, inclusive.
 * @param enabled - Whether to fetch at all.
 *
 * @remarks
 * **The same visits the household reads in its own space**, grouped by who
 * receives the care. The server reads both through one query, so the agency and
 * the family cannot be shown different weeks.
 *
 * The narrowing happens server-side: a manager gets every household with care
 * in the period, an assistant only their own portfolio. Nothing here filters.
 *
 * Keyed under the `['planning']` prefix that a dozen mutations already
 * invalidate, so a replan refreshes this view too.
 */
export function useCustomerPlannings(from: string, to: string, enabled = true) {
  return useQuery({
    queryKey: keys.customerPlannings(from, to),
    enabled,
    queryFn: () =>
      request<CustomerPlanning[]>(
        `/api/v1/planning/customers?period_start=${from}&period_end=${to}`,
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
 * Remove an assistant, their sign-in account, and replan what they were due.
 *
 * @returns The mutation.
 *
 * @remarks
 * Answers **202** with the replan it queued, or **204** when the person had no
 * future visit and nothing needed recomputing. The account goes with the
 * record — one naming a record that no longer exists cannot sign in usefully
 * and cannot be repaired from any screen.
 *
 * The plannings are invalidated as well as the workforce: the visits are
 * rewritten by a worker behind the screen's back, so nothing else would
 * refresh them.
 */
export function useDeleteHca() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      request<PlanningRun | undefined>(`/api/v1/hcas/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['hcas'] });
      void client.invalidateQueries({ queryKey: keys.users });
      void client.invalidateQueries({ queryKey: ['planning'] });
    },
  });
}

/**
 * Remove a customer, every quote written for them, and replan.
 *
 * @returns The mutation.
 *
 * @remarks
 * **Irreversible, and it destroys billing history**, which is why the dialog
 * that offers it counts the quotes first. Stopping a customer remains the
 * right answer for one who was really served and has left; this is for a
 * household entered by mistake.
 */
export function useDeleteCustomer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      request<PlanningRun | undefined>(`/api/v1/customers/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['customers'] });
      void client.invalidateQueries({ queryKey: ['quotes'] });
      void client.invalidateQueries({ queryKey: ['planning'] });
    },
  });
}

/**
 * Remove a sign-in account outright.
 *
 * @returns The mutation.
 *
 * @remarks
 * No replan follows, and that is not an oversight: an account is not
 * scheduled — the assistant record is — so removing one cannot change a
 * calendar. Deactivating is the ordinary way to stop somebody signing in;
 * this is for accounts that should never have existed.
 */
export function useDeleteUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      request<void>(`/api/v1/users/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.users });
      void client.invalidateQueries({ queryKey: ['hcas'] });
    },
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
    enabled,
    refetchInterval: polling ? 2000 : false,
  });
}

/**
 * Ask for a planning to be computed.
 *
 * @returns The mutation.
 *
 * @remarks
 * Answers 202, not 200: each run is queued on the broker and solved by a
 * worker. What comes back is a list of `pending` runs to watch, not a planning.
 *
 * **A list, because a run rebuilds one team's week.** Naming a team plans that
 * team; naming none plans every team the caller runs — a fan-out for an
 * administrator, and the caller's own teams for a manager. Returning one run
 * would have meant silently planning only the first.
 *
 * Requesting one is a **manager's** act now, not an administrator's: it rewrites
 * the calendars of one team, which is exactly the thing a manager is
 * responsible for. Which teams they may name is checked on the server, because
 * nothing here can stop one manager typing another's team.
 */
export function useStartPlanningRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      from,
      to,
      teamId,
      agencyId,
    }: {
      from: string;
      to: string;
      teamId?: string;
      agencyId?: string;
    }) =>
      request<PlanningRun[]>(
        `/api/v1/planning/runs?period_start=${from}&period_end=${to}` +
          (teamId ? `&team_id=${encodeURIComponent(teamId)}` : '') +
          (agencyId ? `&agency_id=${encodeURIComponent(agencyId)}` : ''),
        { method: 'POST' },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['planning'] });
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

/**
 * Quotes, narrowed by whichever filters the screen holds.
 *
 * @remarks
 * `status` survives as its own argument because callers that want one status
 * and nothing else — the validation queue — still pass it alone. When a filter
 * carries one too it wins, which is what the server does with the same pair.
 */
export function useQuotes(status?: QuoteStatus, filter?: EntityFilterRecord) {
  const query = filterQuery({ ...filter, status: filter?.status ?? status });
  return useQuery({
    queryKey: keys.quotes(status, filter),
    queryFn: () =>
      request<Quote[]>(`/api/v1/quotes?size=200${query ? `&${query}` : ''}`),
  });
}

/** The workforce, narrowed by whichever filters the screen holds. */
export function useHcas(search?: string, filter?: EntityFilterRecord) {
  const query = filterQuery({ ...filter, search: filter?.search ?? search });
  return useQuery({
    queryKey: keys.hcas(search, filter),
    queryFn: () => request<Hca[]>(`/api/v1/hcas?size=200${query ? `&${query}` : ''}`),
  });
}

/** The people served. */
export function useCustomers(filter?: CustomerFilter, enabled = true) {
  const query = customerFilterQuery(filter);
  return useQuery({
    queryKey: keys.customers(filter),
    enabled,
    queryFn: () =>
      request<Customer[]>(`/api/v1/customers?size=200${query ? `&${query}` : ''}`),
  });
}

/** The service catalog. */
export function useInterventionTypes(
  includeInactive = false,
  filter?: EntityFilterRecord,
) {
  const query = filterQuery(filter);
  return useQuery({
    queryKey: [...keys.interventionTypes, includeInactive, query] as const,
    queryFn: () =>
      request<InterventionType[]>(
        `/api/v1/intervention-types?size=200&include_inactive=${includeInactive}` +
          (query ? `&${query}` : ''),
      ),
  });
}

/** The caller's notifications, narrowed by whichever filters are held. */
export function useNotifications(filter?: EntityFilterRecord) {
  const query = filterQuery(filter);
  return useQuery({
    queryKey: keys.notifications(filter),
    queryFn: () =>
      request<Notification[]>(
        `/api/v1/notifications?size=100${query ? `&${query}` : ''}`,
      ),
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
      void client.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}

/**
 * Move one line of a returned quote onto a time the planner offered.
 *
 * @returns The mutation.
 *
 * @remarks
 * **The status deliberately does not change.** The quote came back because its
 * work would not fit; accepting a slot answers *when*, not *whether*, so it
 * stays in the validation queue for somebody to validate.
 *
 * The whole `['quotes']` family is invalidated rather than one entry: the
 * server reprices from the day the work lands on — a Sunday costs more than a
 * Tuesday — so the total in the grid moves too, and it clears the planning
 * note, which is what makes the warning panel disappear.
 */
export function useRescheduleQuoteLine(quoteId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: QuoteReschedule) =>
      request<Quote>(`/api/v1/quotes/${quoteId}/reschedule`, {
        method: 'POST',
        json: body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['quotes'] });
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

/**
 * Record that the customer accepted a quote that was sent to them.
 *
 * @returns The mutation.
 *
 * @remarks
 * **Acceptance is what makes a quote's lines schedulable**, so this is the step
 * that puts work into the next planning run. Validation does not: it issues the
 * offer and leaves the quote at `sent`, waiting on the customer.
 *
 * Without this, `sent` was a dead end. The backend has had
 * `POST /quotes/{id}/accept` all along and nothing in the interface called it,
 * so a validated quote could never reach `accepted` — and a manager who
 * validated a fortnight of work and re-ran the planning saw the same visit
 * count every time, with nothing on screen explaining why.
 *
 * Invalidates the planning queries as well as the quotes, because a schedule
 * already on screen was computed without these hours.
 */
export function useAcceptQuote() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (quoteId: string) =>
      request<Quote>(`/api/v1/quotes/${quoteId}/accept`, { method: 'POST' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['quotes'] });
      void client.invalidateQueries({ queryKey: ['planning'] });
    },
  });
}

/** Record that the customer declined a quote that was sent to them. */
export function useRejectQuote() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (quoteId: string) =>
      request<Quote>(`/api/v1/quotes/${quoteId}/reject`, { method: 'POST' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['quotes'] });
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
 *
 * The body is {@link QuoteLinesEdit} rather than a partial quote. It used to be
 * the latter, which let this send a reference and a customer the server then
 * ignored — a contract nobody could read off the types.
 */
/**
 * Change everything about a quote except its lines and its status.
 *
 * @remarks
 * The lines have their own mutation because replacing them reprices the
 * quote, and the status has one route per transition — "send", "validate" and
 * "accept" mean different things and are not interchangeable with setting a
 * field.
 *
 * `['planning']` is invalidated as well as the quotes: reassigning a customer
 * or moving a date changes what the next run will schedule, and the calendars
 * stop agreeing with the quote until they are refetched.
 */
export function useUpdateQuoteHeader() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ quoteId, header }: { quoteId: string; header: QuoteHeaderEdit }) =>
      request<Quote>(`/api/v1/quotes/${quoteId}`, {
        method: 'PATCH',
        json: header,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['quotes'] });
      void client.invalidateQueries({ queryKey: keys.myQuotes });
      void client.invalidateQueries({ queryKey: ['planning'] });
    },
  });
}

export function useReplaceQuoteLines(scope: 'manager' | 'own') {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ quoteId, lines }: { quoteId: string; lines: NewQuoteLine[] }) =>
      request<Quote>(
        scope === 'manager'
          ? `/api/v1/quotes/${quoteId}/lines`
          : `/api/v1/me/quotes/${quoteId}/lines`,
        { method: 'PUT', json: { lines } satisfies QuoteLinesEdit },
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
      field_employee: boolean;
    }) =>
      request<Hca>(`/api/v1/hcas/${hcaId}/employment`, {
        method: 'PATCH',
        json: body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myProfile });
      void client.invalidateQueries({ queryKey: ['hcas'] });
      void client.invalidateQueries({ queryKey: ['planning'] });
    },
  });
}

/**
 * Read the planning rules in force.
 *
 * @returns The query, holding the agency's radius, working day and lunch rules.
 *
 * @remarks
 * Manager-gated on the server, so this is only mounted behind a manager route.
 * The row is seeded from configuration on first read, so this never returns
 * "no rules yet" for a caller to handle.
 */
export function usePlanningSettings() {
  return useQuery({
    queryKey: keys.planningSettings,
    queryFn: () => request<PlanningSettings>('/api/v1/planning/settings'),
  });
}

/**
 * Change the planning rules.
 *
 * @returns The mutation.
 *
 * @remarks
 * The whole rule set is sent, not the field that changed. The server's payload
 * defaults every field but the radius, so a partial body would silently reset
 * the working day to 09:00–20:00 — which looks like a successful save.
 *
 * **A change does not re-plan anything.** It applies to the next planning run,
 * so the cached calendars are deliberately left alone: recomputing this week
 * because somebody widened a radius would move assistants who have already been
 * told where to go. Only the runs list is invalidated, because the next run
 * will read the new rules.
 */
export function useUpdatePlanningSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      max_intervention_radius_km: number;
      day_start_minute: number;
      day_end_minute: number;
      lunch_break_minutes: number;
      lunch_window_start_minute: number;
      lunch_window_end_minute: number;
    }) =>
      request<PlanningSettings>('/api/v1/planning/settings', {
        method: 'PUT',
        json: body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.planningSettings });
      void client.invalidateQueries({ queryKey: keys.planningRuns });
    },
  });
}

/**
 * Declare which days of the week an assistant works.
 *
 * @param hcaId - The assistant whose working week is being set.
 * @returns The mutation.
 *
 * @remarks
 * The assistant is named by the path, never by the payload: the server refuses
 * a week filed against a colleague, and taking the identifier from the body
 * would mean guarding the wrong person.
 *
 * The whole week is sent rather than the day that changed. Two tabs open on the
 * same screen would otherwise race, and last-write-wins on a delta produces a
 * week nobody chose.
 */
export function useSetWorkingDays(hcaId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (workingWeekdays: Weekday[]) =>
      request<Hca>(`/api/v1/hcas/${hcaId}/working-days`, {
        method: 'PUT',
        json: { working_weekdays: workingWeekdays },
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myProfile });
      void client.invalidateQueries({ queryKey: ['hcas'] });
      void client.invalidateQueries({ queryKey: ['planning'] });
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
      void client.invalidateQueries({ queryKey: ['notifications'] });
      void client.invalidateQueries({ queryKey: keys.unreadCount });
    },
  });
}

/**
 * An agency's invoices, most recent period first.
 *
 * @param filter - What the filter bar is narrowing by.
 * @returns The query.
 *
 * @remarks
 * The agency is not a parameter: the server takes it from the credential, so a
 * client cannot widen its own scope by asking.
 */
export function useBills(filter?: EntityFilterRecord) {
  return useQuery({
    queryKey: keys.bills(filter),
    queryFn: () => {
      const query = filterQuery(filter);
      return request<Bill[]>(`/api/v1/bills${query ? `?${query}` : ''}`);
    },
  });
}

/**
 * One invoice with its charges.
 *
 * @param id - The invoice to read, or `''` while the drawer is closed.
 * @returns The query.
 *
 * @remarks
 * The drawer re-reads rather than trusting the grid row, which is a snapshot
 * taken when the page loaded.
 */
export function useBill(id: string) {
  return useQuery({
    queryKey: keys.bill(id),
    queryFn: () => request<Bill>(`/api/v1/bills/${id}`),
    enabled: Boolean(id),
  });
}

/** An agency's bill-generation runs, most recently requested first. */
export function useBillingRuns() {
  return useQuery({
    queryKey: keys.billingRuns,
    queryFn: () => request<BillingRun[]>('/api/v1/bills/runs'),
  });
}

/**
 * One generation run, polled while it is working.
 *
 * @param id - The run to poll, or `''` when nothing is running.
 * @returns The query.
 *
 * @remarks
 * Refetches every two seconds until the run is terminal, then stops. A
 * **partial** run is terminal: the invoices that could be written are written,
 * so polling on would wait for ever.
 */
export function useBillingRun(id: string) {
  return useQuery({
    queryKey: keys.billingRun(id),
    queryFn: () => request<BillingRun>(`/api/v1/bills/runs/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      const finished =
        status === 'succeeded' || status === 'partial' || status === 'failed';
      return finished ? false : 2000;
    },
  });
}

/**
 * Ask for a period to be billed.
 *
 * @returns The mutation.
 *
 * @remarks
 * Answers 202 with a run to poll; the invoices are written by a worker. Both
 * the run list and the bill list are invalidated, because the run will produce
 * rows in the second.
 */
export function useStartBillingRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { reference_date: string }) =>
      request<BillingRun>('/api/v1/bills/runs', { method: 'POST', json: body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.billingRuns });
      void client.invalidateQueries({ queryKey: ['bills'] });
    },
  });
}

/**
 * Move an invoice along its commercial lifecycle.
 *
 * @param billId - The invoice being moved.
 * @returns The mutation.
 *
 * @remarks
 * **Moving to `accepted` is what sends the invoice.** The server publishes the
 * announcement after the record says a manager approved it, so this is not a
 * cosmetic status change — it is the act that emails a customer.
 *
 * Whether a move is legal is the server's decision, taken against the *stored*
 * status. A row rendered a minute ago may have moved since, so the screen
 * offers the neighbours it believes in and lets a 409 correct it.
 */
export function useSetBillStatus(billId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { status: BillStatus }) =>
      request<Bill>(`/api/v1/bills/${billId}/status`, {
        method: 'PATCH',
        json: body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.bill(billId) });
      void client.invalidateQueries({ queryKey: ['bills'] });
    },
  });
}

/**
 * Download an invoice's PDF.
 *
 * @returns The mutation.
 *
 * @remarks
 * A **mutation**, not a query. A download has a side effect on the user's disk,
 * and a query would re-fire it on every window refocus — handing somebody a
 * second copy of the same invoice for coming back to the tab.
 *
 * The filename comes back with the bytes, from the server's own
 * `Content-Disposition`. Derived here it would be the route path.
 */
export function useDownloadBill() {
  return useMutation({
    mutationFn: async (bill: { id: string; number: string }) => {
      const { blob, filename } = await requestBlob(
        `/api/v1/bills/${bill.id}/document`,
        `${bill.number}.pdf`,
      );
      saveBlob(blob, filename);
      return filename;
    },
  });
}

/** The agency's invoicing rules, seeded by the server on first read. */
export function useBillingSettings() {
  return useQuery({
    queryKey: keys.billingSettings,
    queryFn: () => request<BillingSettings>('/api/v1/billing/settings'),
  });
}

/**
 * Change the invoicing rules.
 *
 * @returns The mutation.
 *
 * @remarks
 * The whole rule set is sent, not the field that changed. Every field on the
 * server's payload carries a default, so a partial body would silently reset
 * the others — on values printed on every invoice the agency sends.
 *
 * **A change re-issues nothing.** It applies to the next generation run, so the
 * cached bills are deliberately left alone: an invoice already issued keeps the
 * terms it was printed with, because those terms are part of what the customer
 * was told.
 */
export function useUpdateBillingSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      periodicity: BillingPeriodicity;
      payment_terms_days: number;
      late_penalty_multiplier: number;
      recovery_indemnity_eur: string;
      escompte_offered: boolean;
    }) =>
      request<BillingSettings>('/api/v1/billing/settings', {
        method: 'PUT',
        json: body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.billingSettings });
    },
  });
}

/* ------------------------------------------------------------------------ *
 *  The customer portal
 *
 *  Every hook here reads the household from the credential — no identifier is
 *  ever sent — so there is nothing a browser console could edit to reach
 *  somebody else's file.
 * ------------------------------------------------------------------------ */

/** The household's own record. */
export function usePortalProfile() {
  return useQuery({
    queryKey: keys.portalProfile,
    queryFn: () => request<Customer>('/api/v1/portal/profile'),
  });
}

/**
 * Correct the household's own contact details.
 *
 * @returns The mutation.
 *
 * @remarks
 * The payload carries the contact block and nothing else — no status, no
 * billing periodicity. Those are the agency's to set, and a household that
 * could change the first would put their own work into the next planning run.
 */
export function useUpdatePortalProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CustomerProfileUpdate) =>
      request<Customer>('/api/v1/portal/profile', { method: 'PUT', json: body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.portalProfile });
    },
  });
}

/**
 * The household's visits over a period.
 *
 * @param from - First day of interest, inclusive.
 * @param to - Last day of interest, inclusive.
 * @returns The query.
 *
 * @remarks
 * The period is required by the server rather than defaulted: the calendar
 * always knows which weeks it is showing, and an unbounded read would return
 * every visit the household has ever had in order to draw seven days.
 */
export function usePortalPlanning(from: string, to: string) {
  return useQuery({
    queryKey: keys.portalPlanning(from, to),
    queryFn: () =>
      request<Intervention[]>(
        `/api/v1/portal/planning?period_start=${from}&period_end=${to}`,
      ),
    enabled: Boolean(from && to),
  });
}

/** Every quote ever written for the household, newest first. */
export function usePortalQuotes() {
  return useQuery({
    queryKey: keys.portalQuotes,
    queryFn: () => request<Quote[]>('/api/v1/portal/quotes'),
  });
}

/** Every invoice issued to the household. */
export function usePortalBills() {
  return useQuery({
    queryKey: keys.portalBills,
    queryFn: () => request<Bill[]>('/api/v1/portal/bills'),
  });
}

/**
 * Cancel one visit.
 *
 * @returns The mutation.
 *
 * @remarks
 * **This does more than remove a block from a calendar.** The line goes off the
 * quote, the quote is repriced and sent back to the agency for validation, and
 * a replan is queued. Until a manager re-validates it, nothing on that quote is
 * scheduled — which the screen has to say, because an empty calendar and a
 * calendar waiting for approval look identical.
 *
 * The whole `['portal']` prefix is invalidated: the planning, the quotes and
 * the profile can all have changed.
 */
export function useCancelVisit() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (interventionId: string) =>
      request<Quote>(`/api/v1/portal/interventions/${interventionId}/cancel`, {
        method: 'POST',
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['portal'] });
    },
  });
}

/**
 * Move one visit to a day and a window that suit better.
 *
 * @returns The mutation.
 *
 * @remarks
 * A **window**, not a time: the solver picks the moment inside it against the
 * assistant's round. Like cancelling, it reprices and returns the quote to the
 * agency — a visit moved onto a Sunday costs more, so the household cannot
 * change the work without the agency seeing the new price.
 */
export function useRescheduleVisit() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      interventionId,
      ...body
    }: InterventionReschedule & { interventionId: string }) =>
      request<Quote>(`/api/v1/portal/interventions/${interventionId}/reschedule`, {
        method: 'POST',
        json: body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['portal'] });
    },
  });
}

/**
 * Download one of the household's quotes as a PDF.
 *
 * @returns The mutation.
 *
 * @remarks
 * Streamed through the API rather than fetched from a bucket, so the bearer
 * guard is the only way to the document. Rendered on demand and in the
 * household's own language.
 */
export function useDownloadPortalQuote() {
  return useMutation({
    mutationFn: async (quote: { id: string; reference: string }) => {
      const { blob, filename } = await requestBlob(
        `/api/v1/portal/quotes/${quote.id}/document`,
        `${quote.reference}.pdf`,
      );
      saveBlob(blob, filename);
      return filename;
    },
  });
}

/** Download one of the household's invoices as a PDF. */
export function useDownloadPortalBill() {
  return useMutation({
    mutationFn: async (bill: { id: string; number: string }) => {
      const { blob, filename } = await requestBlob(
        `/api/v1/portal/bills/${bill.id}/document`,
        `${bill.number}.pdf`,
      );
      saveBlob(blob, filename);
      return filename;
    },
  });
}

/**
 * The certified platforms, with this agency's state against each.
 *
 * @returns The query.
 *
 * @remarks
 * Always four cards, configured or not: the gallery's job is to get something
 * connected, so a list of only what already is would be empty on exactly the
 * screen that matters.
 */
export function useIntegrations() {
  return useQuery({
    queryKey: keys.integrations,
    queryFn: () => request<IntegrationCard[]>('/api/v1/billing/integrations'),
  });
}

/**
 * Connect a platform, making it the one this agency transmits through.
 *
 * @returns The mutation.
 *
 * @remarks
 * **The server proves the credentials against the live platform before storing
 * them**, so a rejected key surfaces here as an error while the dialog is still
 * open — which is the whole reason enabling is one round trip rather than a
 * save followed by a separate test.
 *
 * Enabling one platform disables the previous one server-side, in the same
 * transaction, so the whole list is invalidated rather than one card patched.
 */
export function useEnableIntegration() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      provider: EInvoicingProvider;
      body: IntegrationCredentialsBody;
    }) =>
      request<IntegrationCard>(`/api/v1/billing/integrations/${input.provider}`, {
        method: 'PUT',
        json: input.body,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.integrations });
    },
  });
}

/**
 * Stop transmitting through a platform, keeping its credentials.
 *
 * @returns The mutation.
 *
 * @remarks
 * The stored key survives, so switching back does not mean finding it again.
 */
export function useDisableIntegration() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (provider: EInvoicingProvider) =>
      request<IntegrationCard>(`/api/v1/billing/integrations/${provider}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.integrations });
    },
  });
}

/**
 * Prove stored credentials again and record what happened.
 *
 * @returns The mutation.
 *
 * @remarks
 * Answers 200 even when the platform refuses — the check *ran*, and what it
 * found belongs on the card. A key rotated at the far end shows up here rather
 * than as an invoice that silently never left.
 */
export function useCheckIntegration() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (provider: EInvoicingProvider) =>
      request<IntegrationCard>(`/api/v1/billing/integrations/${provider}/check`, {
        method: 'POST',
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.integrations });
    },
  });
}

/**
 * The sites the caller's company operates from.
 *
 * @returns The query.
 *
 * @remarks
 * Readable by any signed-in account, not just an administrator: an assistant's
 * own team screen names the site it works from, and the team dialog picks from
 * this list. What that costs is bounded by the response — see {@link Agency},
 * which publishes no part of the company's legal identity.
 */
export function useAgencies() {
  return useQuery({
    queryKey: keys.agencies,
    queryFn: () => request<Agency[]>('/api/v1/agencies?size=500'),
  });
}

/**
 * Open a new site.
 *
 * @returns The mutation.
 *
 * @remarks
 * The type in the body is a request, not a decision: the server makes the first
 * site of a company its head office whatever was asked for, and refuses a
 * second. That rule is a question about other rows, which no form can answer.
 */
export function useCreateAgency() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: AgencyBody) =>
      request<Agency>('/api/v1/agencies', { method: 'POST', json: body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.agencies });
    },
  });
}

/**
 * Change a site's name, address or type.
 *
 * @returns The mutation.
 */
export function useUpdateAgency() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AgencyBody }) =>
      request<Agency>(`/api/v1/agencies/${id}`, { method: 'PUT', json: body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.agencies });
    },
  });
}

/**
 * Close a site nobody works at.
 *
 * @returns The mutation.
 *
 * @remarks
 * Also invalidates the teams, because a site that has just gone cannot be the
 * one a team is listed under — and the refusal that stops this happening is
 * itself computed from the team count.
 */
export function useDeleteAgency() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      request<void>(`/api/v1/agencies/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.agencies });
      void client.invalidateQueries({ queryKey: keys.teams });
    },
  });
}

/**
 * Everybody attached to one site.
 *
 * @param agencyId - The site to read, or `''` while a dialog is closed.
 * @returns The query.
 */
export function useAgencyMembers(agencyId: string) {
  return useQuery({
    queryKey: keys.agencyMembers(agencyId),
    queryFn: () =>
      request<OrganisationMember[]>(`/api/v1/agencies/${agencyId}/members`),
    enabled: Boolean(agencyId),
  });
}

/**
 * Attach somebody to a site.
 *
 * @returns The mutation.
 *
 * @remarks
 * Invalidates the sites as well as the roster, because the grid shows a member
 * count on every row.
 */
export function useAddAgencyMember() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ agencyId, body }: { agencyId: string; body: OrganisationMember }) =>
      request<OrganisationMember>(`/api/v1/agencies/${agencyId}/members`, {
        method: 'POST',
        json: body,
      }),
    onSuccess: (_result, { agencyId }) => {
      void client.invalidateQueries({ queryKey: keys.agencyMembers(agencyId) });
      void client.invalidateQueries({ queryKey: keys.agencies });
    },
  });
}

/**
 * Detach somebody from a site.
 *
 * @returns The mutation.
 *
 * @remarks
 * The kind is a path segment rather than a query parameter because it is half
 * of the identity: an account and an assistant record can share an identifier.
 */
export function useRemoveAgencyMember() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      agencyId,
      member,
    }: {
      agencyId: string;
      member: OrganisationMember;
    }) =>
      request<void>(
        `/api/v1/agencies/${agencyId}/members/${member.member_kind}/${member.member_id}`,
        { method: 'DELETE' },
      ),
    onSuccess: (_result, { agencyId }) => {
      void client.invalidateQueries({ queryKey: keys.agencyMembers(agencyId) });
      void client.invalidateQueries({ queryKey: keys.agencies });
    },
  });
}

/**
 * The teams the caller may read.
 *
 * @returns The query.
 *
 * @remarks
 * An administrator gets the whole company, a manager gets the teams they run,
 * and an assistant gets the one they are on. The narrowing is the server's and
 * happens in the statement; nothing here filters.
 */
export function useTeams() {
  return useQuery({
    queryKey: keys.teams,
    queryFn: () => request<Team[]>('/api/v1/teams?size=500'),
  });
}

/**
 * The team the caller is themselves on.
 *
 * @returns The query.
 *
 * @remarks
 * Membership, not management: a manager who runs two teams is a *member* of
 * one, and it is that one whose roster and shared space are theirs.
 */
export function useMyTeam() {
  return useQuery({
    queryKey: keys.myTeam,
    queryFn: () => request<Team>('/api/v1/me/team'),
    retry: false,
  });
}

/**
 * Form a team at one of the company's sites.
 *
 * @returns The mutation.
 *
 * @remarks
 * Invalidates the plannings too: which team exists changes what a run may be
 * asked for, and the run screen offers one picker per team.
 */
export function useCreateTeam() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: TeamBody) =>
      request<Team>('/api/v1/teams', { method: 'POST', json: body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.teams });
      void client.invalidateQueries({ queryKey: keys.agencies });
      void client.invalidateQueries({ queryKey: ['planning'] });
    },
  });
}

/**
 * Change a team's name, site or manager.
 *
 * @returns The mutation.
 */
export function useUpdateTeam() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: TeamBody }) =>
      request<Team>(`/api/v1/teams/${id}`, { method: 'PUT', json: body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.teams });
      void client.invalidateQueries({ queryKey: ['planning'] });
    },
  });
}

/**
 * Disband a team that holds no work.
 *
 * @returns The mutation.
 */
export function useDeleteTeam() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => request<void>(`/api/v1/teams/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.teams });
      void client.invalidateQueries({ queryKey: keys.agencies });
      void client.invalidateQueries({ queryKey: ['planning'] });
    },
  });
}

/**
 * Everybody on one team.
 *
 * @param teamId - The team to read, or `''` while a dialog is closed.
 * @returns The query.
 */
export function useTeamMembers(teamId: string) {
  return useQuery({
    queryKey: keys.teamMembers(teamId),
    queryFn: () => request<OrganisationMember[]>(`/api/v1/teams/${teamId}/members`),
    enabled: Boolean(teamId),
  });
}

/**
 * Put somebody on a team.
 *
 * @returns The mutation.
 *
 * @remarks
 * One person at a time, which is the one place this surface departs from the
 * "submit the whole list" rule the working-days editor follows. A person is on
 * exactly one team, so a whole-list submission would silently take people off
 * other teams — and each of those removals changes whose week the next planning
 * run rewrites.
 */
export function useAddTeamMember() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ teamId, body }: { teamId: string; body: OrganisationMember }) =>
      request<OrganisationMember>(`/api/v1/teams/${teamId}/members`, {
        method: 'POST',
        json: body,
      }),
    onSuccess: (_result, { teamId }) => {
      void client.invalidateQueries({ queryKey: keys.teamMembers(teamId) });
      void client.invalidateQueries({ queryKey: keys.teams });
      void client.invalidateQueries({ queryKey: ['planning'] });
    },
  });
}

/**
 * Take somebody off a team.
 *
 * @returns The mutation.
 */
export function useRemoveTeamMember() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ teamId, member }: { teamId: string; member: OrganisationMember }) =>
      request<void>(
        `/api/v1/teams/${teamId}/members/${member.member_kind}/${member.member_id}`,
        { method: 'DELETE' },
      ),
    onSuccess: (_result, { teamId }) => {
      void client.invalidateQueries({ queryKey: keys.teamMembers(teamId) });
      void client.invalidateQueries({ queryKey: keys.teams });
      void client.invalidateQueries({ queryKey: ['planning'] });
    },
  });
}

/**
 * The files a team shares.
 *
 * @param teamId - The team whose space is being read.
 * @returns The query.
 */
export function useTeamDocuments(teamId: string) {
  return useQuery({
    queryKey: keys.teamDocuments(teamId),
    queryFn: () => request<TeamDocument[]>(`/api/v1/teams/${teamId}/documents`),
    enabled: Boolean(teamId),
  });
}

/**
 * What a team's shared space accepts.
 *
 * @returns The query.
 *
 * @remarks
 * Read so the picker can refuse an oversized or unshareable file before
 * uploading it rather than after. A rejection that arrives once the whole file
 * has crossed the network is a rejection somebody waited for.
 */
export function useTeamDocumentConstraints() {
  return useQuery({
    queryKey: keys.teamDocumentConstraints,
    queryFn: () =>
      request<TeamDocumentConstraints>('/api/v1/teams/document-constraints'),
  });
}
