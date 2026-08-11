import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BillingSettingsPage } from '../BillingSettingsPage';
import type { BillingSettings } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

const save = vi.fn();
const query = {
  data: undefined as BillingSettings | undefined,
  isLoading: false,
};
const mutation = { mutate: save, isPending: false, isError: false, isSuccess: false };

vi.mock('@/api/queries', () => ({
  useBillingSettings: () => query,
  useUpdateBillingSettings: () => mutation,
  // The rules tab renders the e-invoicing warning, which asks whether a
  // platform is connected. Stubbed as "one is" so these tests stay about
  // the invoicing rules; the warning has its own tests.
  useIntegrations: () => ({ data: [{ enabled: true }], isLoading: false }),
}));

const RULES: BillingSettings = {
  id: 'billing-settings',
  periodicity: 'monthly',
  payment_terms_days: 30,
  late_penalty_multiplier: 3,
  recovery_indemnity_eur: '40.00',
  escompte_offered: false,
  updated_by: null,
  updated_at: null,
};

beforeEach(() => {
  query.data = RULES;
  query.isLoading = false;
  mutation.isError = false;
  mutation.isSuccess = false;
  vi.clearAllMocks();
});

/**
 * The invoicing rules a manager owns.
 *
 * Every field here is printed on a document that goes to customers, so what
 * these pin is that a save sends the whole rule set and that the screen is
 * honest about a change re-issuing nothing.
 */
describe('BillingSettingsPage', () => {
  it('waits rather than rendering an empty form', () => {
    query.isLoading = true;
    query.data = undefined;
    render(<BillingSettingsPage />);

    expect(screen.queryByTestId('billing-settings-page')).toBeNull();
  });

  it('fills the form from the stored rules', () => {
    render(<BillingSettingsPage />);

    expect(screen.getByTestId('billing-payment-terms')).toHaveValue(30);
  });

  it('says a change re-issues nothing', () => {
    // **The sentence that stops a manager expecting corrected invoices.** An
    // invoice already issued keeps the terms it was printed with, because
    // those terms are part of what the customer was told.
    render(<BillingSettingsPage />);

    expect(screen.getByTestId('billing-settings-notice')).toHaveTextContent(
      'billingSettings.notice',
    );
  });

  it('sends the whole rule set, not the field that changed', async () => {
    // **Never a partial body.** The server's payload defaults every field, so
    // omitting one would silently reset a value printed on every invoice.
    const user = userEvent.setup();
    render(<BillingSettingsPage />);

    await user.clear(screen.getByTestId('billing-payment-terms'));
    await user.type(screen.getByTestId('billing-payment-terms'), '45');
    await user.click(screen.getByTestId('billing-settings-save'));

    expect(save).toHaveBeenCalledWith({
      periodicity: 'monthly',
      payment_terms_days: 45,
      late_penalty_multiplier: 3,
      recovery_indemnity_eur: '40.00',
      escompte_offered: false,
    });
  });

  it('refuses terms beyond the statutory ceiling before asking the server', async () => {
    // The ceiling is statutory, not a preference. Caught here it names the
    // limit before the request; caught by the server it is a 422 saying the
    // same thing, and the server's is the one that guards the database.
    const user = userEvent.setup();
    render(<BillingSettingsPage />);

    await user.clear(screen.getByTestId('billing-payment-terms'));
    await user.type(screen.getByTestId('billing-payment-terms'), '90');

    expect(screen.getByTestId('billing-settings-problem')).toHaveTextContent(
      'billingSettings.termsTooLong',
    );
    expect(screen.getByTestId('billing-settings-save')).toBeDisabled();
  });

  it('refuses a zero-day payment term', async () => {
    const user = userEvent.setup();
    render(<BillingSettingsPage />);

    await user.clear(screen.getByTestId('billing-payment-terms'));
    await user.type(screen.getByTestId('billing-payment-terms'), '0');

    expect(screen.getByTestId('billing-settings-problem')).toHaveTextContent(
      'billingSettings.termsTooShort',
    );
  });

  it('reports a refused save', () => {
    mutation.isError = true;
    render(<BillingSettingsPage />);

    expect(screen.getByTestId('billing-settings-error')).toBeInTheDocument();
  });

  it('confirms a save that worked', () => {
    mutation.isSuccess = true;
    render(<BillingSettingsPage />);

    expect(screen.getByTestId('billing-settings-saved')).toBeInTheDocument();
  });
});
