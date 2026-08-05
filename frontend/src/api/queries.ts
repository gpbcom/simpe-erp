import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request } from './client';
import type {
  Customer,
  Hca,
  HcaPlanning,
  InterventionType,
  Notification,
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
  myProfile: ['me', 'hca'] as const,
  myCustomers: (search?: string) => ['me', 'customers', search ?? ''] as const,
  myQuotes: ['me', 'quotes'] as const,
  myPlanning: (hcaId: string, from: string, to: string) =>
    ['planning', hcaId, from, to] as const,
  allPlannings: (from: string, to: string) => ['planning', 'all', from, to] as const,
  quotes: (status?: QuoteStatus, search?: string) =>
    ['quotes', status ?? 'all', search ?? ''] as const,
  quote: (id: string) => ['quotes', id] as const,
  hcas: (search?: string) => ['hcas', search ?? ''] as const,
  hca: (id: string) => ['hcas', id] as const,
  customers: (search?: string) => ['customers', search ?? ''] as const,
  interventionTypes: ['intervention-types'] as const,
  notifications: ['notifications'] as const,
  unreadCount: ['notifications', 'unread'] as const,
};

/** The caller's own assistant record. */
export function useMyProfile() {
  return useQuery({
    queryKey: keys.myProfile,
    queryFn: () => request<Hca>('/api/v1/me/hca'),
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
export function useInterventionTypes() {
  return useQuery({
    queryKey: keys.interventionTypes,
    queryFn: () => request<InterventionType[]>('/api/v1/intervention-types?size=200'),
  });
}

/** The caller's notifications. */
export function useNotifications() {
  return useQuery({
    queryKey: keys.notifications,
    queryFn: () => request<Notification[]>('/api/v1/notifications?size=100'),
  });
}

/** How many notifications the caller has not read. */
export function useUnreadCount() {
  return useQuery({
    queryKey: keys.unreadCount,
    queryFn: () => request<{ unread: number }>('/api/v1/notifications/unread-count'),
    // A safety net behind the event stream, not the primary path. If a frame is
    // dropped the badge is briefly stale rather than wrong for ever — the row
    // is already in the database either way.
    refetchInterval: 60_000,
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
