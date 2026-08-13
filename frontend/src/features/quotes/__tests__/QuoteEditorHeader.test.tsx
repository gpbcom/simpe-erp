import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QuoteEditorDialog } from '../QuoteEditorDialog';
import type { Quote } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

const updateHeader = vi.fn();
const replaceLines = vi.fn();

vi.mock('@/api/queries', () => ({
  useInterventionTypes: () => ({ data: [] }),
  usePricingRules: () => ({ data: { vat_rates: { necessity: '0.055' } } }),
  useCertificationTypes: () => ({ data: [] }),
  useSkillTypes: () => ({ data: [] }),
  useCustomers: () => ({
    data: [
      { id: 'customer-1', first_name: 'Jeanne', last_name: 'Vincent' },
      { id: 'customer-2', first_name: 'Marie', last_name: 'Durand' },
    ],
  }),
  useUpdateQuoteHeader: () => ({ mutate: updateHeader, isPending: false }),
  useReplaceQuoteLines: () => ({ mutate: replaceLines, isPending: false }),
}));

const QUOTE: Quote = {
  id: 'quote-1',
  company_id: 'company-1',
  team_id: 'team-1',
  reference: 'D-2648',
  customer_id: 'customer-1',
  status: 'pending-validation',
  lines: [],
  aggregates: [],
  issued_on: '2026-08-01',
  valid_until: '2026-09-01',
  authored_by: null,
  submitted_at: null,
  validated_by: null,
  validated_at: null,
  planning_feedback: null,
  interrupted_on: null,
  auto_renew: false,
  renewed_from_id: null,
};

/**
 * Editing a quote's header from the quotes menu.
 *
 * The planner now sends quotes back to be validated when their work will not
 * fit, and those are past draft by definition. A returned quote nobody can
 * change is a dead end, so these pin that the header is present, populated and
 * saveable on exactly such a quote.
 */
describe('QuoteEditorDialog header', () => {
  it('offers every header field on a quote past draft', () => {
    render(<QuoteEditorDialog quote={QUOTE} scope="manager" onClose={vi.fn()} />);

    expect(screen.getByTestId('quote-header-fields')).toBeVisible();
    expect(screen.getByTestId('quote-reference')).toHaveValue('D-2648');
    expect(screen.getByTestId('quote-issued-on')).toHaveValue('2026-08-01');
    expect(screen.getByTestId('quote-valid-until')).toHaveValue('2026-09-01');
    expect(screen.getByTestId('quote-customer')).toHaveValue('customer-1');
  });

  it('leaves Save disabled until something actually changes', () => {
    // A lit Save button on an untouched quote invites a pointless reprice,
    // and an edit reprices against today's catalogue.
    render(<QuoteEditorDialog quote={QUOTE} scope="manager" onClose={vi.fn()} />);

    expect(screen.getByTestId('save-quote-lines')).toBeDisabled();
  });

  it('saves a header change through the header route', async () => {
    const user = userEvent.setup();
    render(<QuoteEditorDialog quote={QUOTE} scope="manager" onClose={vi.fn()} />);

    await user.selectOptions(screen.getByTestId('quote-customer'), 'customer-2');
    await user.click(screen.getByTestId('save-quote-lines'));

    expect(updateHeader).toHaveBeenCalledWith(
      expect.objectContaining({
        quoteId: 'quote-1',
        header: expect.objectContaining({ customer_id: 'customer-2' }),
      }),
      expect.anything(),
    );
  });

  it('clears a date to null rather than to an empty string', async () => {
    // The server reads `null` as "not issued yet". An empty string would be
    // an invalid date rather than an absent one.
    const user = userEvent.setup();
    render(<QuoteEditorDialog quote={QUOTE} scope="manager" onClose={vi.fn()} />);

    await user.clear(screen.getByTestId('quote-valid-until'));
    await user.click(screen.getByTestId('save-quote-lines'));

    expect(updateHeader).toHaveBeenCalledWith(
      expect.objectContaining({
        header: expect.objectContaining({ valid_until: null }),
      }),
      expect.anything(),
    );
  });
});
