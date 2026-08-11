import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CustomerBillingCard } from '../CustomerBillingCard';
import type { BillingSettings, Customer } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, options?: Record<string, string>) =>
      options?.periodicity ? `${key}:${options.periodicity}` : key,
  }),
}));

const save = { mutate: vi.fn(), isPending: false, isError: false, isSuccess: false };
const settings = { data: undefined as BillingSettings | undefined };

vi.mock('@/api/queries', () => ({
  useBillingSettings: () => settings,
  useSetCustomerBillingPeriodicity: () => save,
}));

const AGENCY_RULES: BillingSettings = {
  id: 'billing-settings',
  periodicity: 'monthly',
  payment_terms_days: 30,
  late_penalty_multiplier: 3,
  recovery_indemnity_eur: '40.00',
  escompte_offered: false,
  updated_by: null,
  updated_at: null,
};

const CUSTOMER: Customer = {
  id: 'customer-1',
  first_name: 'Marie',
  last_name: 'Durand',
  phone_number: '+33612345678',
  email: 'marie.durand@example.fr',
  address: {
    street: '12 rue de Rivoli',
    postal_code: '75004',
    city: 'Paris',
    country: 'France',
    latitude: 48.85,
    longitude: 2.35,
    geocoding_error: null,
  },
  registration_status: 'active',
  billing_periodicity: null,
  created_at: null,
  updated_at: null,
};

describe('CustomerBillingCard', () => {
  beforeEach(() => {
    save.mutate.mockClear();
    save.isPending = false;
    save.isError = false;
    save.isSuccess = false;
    settings.data = AGENCY_RULES;
  });

  it('shows a customer with no override as following the agency', () => {
    render(<CustomerBillingCard customer={CUSTOMER} />);

    expect(screen.getByTestId('customer-billing-periodicity')).toHaveValue('');
  });

  it('names the agency rule in the option, so the two can be told apart', () => {
    render(<CustomerBillingCard customer={CUSTOMER} />);

    expect(
      screen.getByText('customer.billingFollowsAgency:billingSettings.monthly'),
    ).toBeInTheDocument();
  });

  it('shows a customer with an override on their own rule', () => {
    render(
      <CustomerBillingCard
        customer={{ ...CUSTOMER, billing_periodicity: 'weekly' }}
      />,
    );

    expect(screen.getByTestId('customer-billing-periodicity')).toHaveValue('weekly');
  });

  it('sends the chosen granularity for this customer', async () => {
    render(<CustomerBillingCard customer={CUSTOMER} />);

    await userEvent.selectOptions(
      screen.getByTestId('customer-billing-periodicity'),
      'yearly',
    );

    expect(save.mutate).toHaveBeenCalledWith({
      customerId: 'customer-1',
      periodicity: 'yearly',
    });
  });

  it('sends null when the customer goes back to the agency rule', async () => {
    // Taking an override off has to be as reachable as putting one on. Sent as
    // the agency's *current* periodicity instead, the customer would look
    // unchanged today and stop following the setting tomorrow.
    render(
      <CustomerBillingCard
        customer={{ ...CUSTOMER, billing_periodicity: 'weekly' }}
      />,
    );

    await userEvent.selectOptions(
      screen.getByTestId('customer-billing-periodicity'),
      '',
    );

    expect(save.mutate).toHaveBeenCalledWith({
      customerId: 'customer-1',
      periodicity: null,
    });
  });

  it('still offers the agency option before the rules have loaded', () => {
    settings.data = undefined;

    render(<CustomerBillingCard customer={CUSTOMER} />);

    expect(
      screen.getByText('customer.billingFollowsAgencyUnknown'),
    ).toBeInTheDocument();
  });

  it('reports a refused change rather than looking saved', () => {
    save.isError = true;

    render(<CustomerBillingCard customer={CUSTOMER} />);

    expect(screen.getByTestId('customer-billing-error')).toBeInTheDocument();
  });
});
