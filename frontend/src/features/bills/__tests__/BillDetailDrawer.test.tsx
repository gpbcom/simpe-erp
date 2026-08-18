import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BillDetailDrawer } from '../BillDetailDrawer';
import type { Bill, BillStatus } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, values?: Record<string, unknown>) =>
      values
        ? `${key}(${Object.entries(values)
            .map(([name, value]) => `${name}=${String(value)}`)
            .join(',')})`
        : key,
  }),
}));

const setStatus = vi.fn();
const download = vi.fn();

vi.mock('@/api/queries', () => ({
  useBill: () => ({ data: undefined }),
  useSetBillStatus: () => ({
    mutate: setStatus,
    isPending: false,
    isError: false,
  }),
  useDownloadBill: () => ({
    mutate: download,
    isPending: false,
    isError: false,
  }),
}));

function aBill(overrides: Partial<Bill> = {}): Bill {
  return {
    id: 'bill-1',
    company_id: 'company-1',
    customer_id: 'customer-1',
    billing_run_id: 'run-1',
    number: 'FA-2026-000001',
    sequence: 1,
    sequence_year: 2026,
    periodicity: 'monthly',
    period_start: '2026-03-01',
    period_end: '2026-03-31',
    issued_on: '2026-04-01',
    due_on: '2026-05-01',
    status: 'to-be-validated',
    customer_full_name: 'Jeanne Vincent',
    customer_address: {
      street: '1 rue des Lilas',
      postal_code: '75011',
      city: 'Paris',
      country: 'France',
      latitude: null,
      longitude: null,
      geocoding_error: null,
    },
    recipient: {
      kind: 'individual',
      name: 'Jeanne Vincent',
      address: {
        street: '1 rue des Lilas',
        postal_code: '75011',
        city: 'Paris',
        country: 'France',
        latitude: null,
        longitude: null,
        geocoding_error: null,
      },
      siren: null,
      vat_number: null,
      service_code: null,
      share_ttc: null,
    },
    operation_nature: 'services',
    lines: [
      {
        id: 'line-1',
        quote_line_id: 'quote-line-1',
        intervention_id: 'visit-1',
        name: 'Aide à la toilette',
        service_category: 'necessity',
        service_date: '2026-03-09',
        day: '2026-03-09',
        start_time: '09:00:00',
        end_time: '11:00:00',
        hca_full_name: 'Amina Benali',
        duration_minutes: 120,
        hourly_rate_ht: '31.91',
        total_ht: '63.82',
        vat_rate: '0.0550',
        vat_amount: '3.51',
        total_ttc: '67.33',
      },
    ],
    total_ht: '63.82',
    total_vat: '3.51',
    total_ttc: '67.33',
    document_key: 'invoices/company-1/abc.pdf',
    generated_by: 'user-1',
    validated_by: null,
    validated_at: null,
    sent_at: null,
    paid_on: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

beforeEach(() => vi.clearAllMocks());

/**
 * One invoice, and what a manager may do to it.
 *
 * The two things worth pinning hardest are requirement 9 — the rows are visits
 * and no quote is named — and the lifecycle, where the wrong button offered is
 * a manager sending an invoice they meant to correct.
 */
describe('BillDetailDrawer', () => {
  it('renders nothing when no invoice is selected', () => {
    render(<BillDetailDrawer selected={null} onClose={vi.fn()} />);

    expect(screen.queryByTestId('bill-detail-drawer')).toBeNull();
  });

  it('lists the visits it charges for', () => {
    render(<BillDetailDrawer selected={aBill()} onClose={vi.fn()} />);

    const lines = screen.getByTestId('bill-lines');
    expect(lines).toHaveTextContent('Aide à la toilette');
    expect(lines).toHaveTextContent('Amina Benali');
    expect(lines).toHaveTextContent('2026-03-09');
  });

  it('names no quote anywhere on the screen', () => {
    // **Requirement 9, made testable.** `quote_line_id` is stored on every
    // charge so a disputed line can be traced in a support conversation. A
    // manager reading it off the screen and quoting it to a customer would be
    // reading from a document the customer does not hold.
    render(<BillDetailDrawer selected={aBill()} onClose={vi.fn()} />);

    const drawer = screen.getByTestId('bill-detail-drawer');
    expect(drawer.textContent).not.toContain('quote-line-1');
    expect(drawer.textContent?.toLowerCase()).not.toContain('quote');
  });

  it('shows a dash for a service the planner never placed', () => {
    // Still billed: the visit was sold and delivered whether or not a planning
    // run ever saw it, and dropping it would forgive money the agency earned.
    const unplanned = aBill({
      lines: [
        {
          ...aBill().lines[0]!,
          day: null,
          start_time: null,
          end_time: null,
          hca_full_name: null,
        },
      ],
    });
    render(<BillDetailDrawer selected={unplanned} onClose={vi.fn()} />);

    expect(screen.getByTestId('bill-lines')).toHaveTextContent('bill.notPlanned');
  });

  it('says whether the customer has actually been sent it', () => {
    // "Awaiting payment" and "actually sent" are different questions, and a
    // bill a manager pushed forward by hand while the mail server was down is
    // awaited but never went.
    render(<BillDetailDrawer selected={aBill()} onClose={vi.fn()} />);

    expect(screen.getByTestId('bill-sent-state')).toHaveTextContent('bill.notSent');
  });

  it('offers validating an invoice that is waiting for it', () => {
    render(<BillDetailDrawer selected={aBill()} onClose={vi.fn()} />);

    expect(screen.getByTestId('bill-advance-accepted')).toBeInTheDocument();
  });

  it('sends the invoice when it is validated', async () => {
    // **The act that reaches a customer.** Moving to accepted is what the
    // server announces, and what the webhook then emails.
    const user = userEvent.setup();
    render(<BillDetailDrawer selected={aBill()} onClose={vi.fn()} />);

    await user.click(screen.getByTestId('bill-advance-accepted'));

    expect(setStatus).toHaveBeenCalledWith({ status: 'accepted' });
  });

  it('offers only the neighbouring statuses, never a skip', () => {
    // The lifecycle moves one step at a time and the server refuses anything
    // else with a 409. A button that offered "paid" from here would be one
    // that is always refused.
    render(<BillDetailDrawer selected={aBill()} onClose={vi.fn()} />);

    expect(screen.queryByTestId('bill-advance-paid')).toBeNull();
    expect(screen.queryByTestId('bill-step-back-accepted')).toBeNull();
  });

  it('offers a way back from every status past the first', () => {
    // A manager who marked the wrong row needs it. An irreversible status
    // would leave them editing the database.
    render(
      <BillDetailDrawer selected={aBill({ status: 'accepted' })} onClose={vi.fn()} />,
    );

    expect(screen.getByTestId('bill-step-back-to-be-validated')).toBeInTheDocument();
  });

  it('offers nothing forward once an invoice is settled', () => {
    render(<BillDetailDrawer selected={aBill({ status: 'paid' })} onClose={vi.fn()} />);

    expect(screen.queryByTestId('bill-advance-paid')).toBeNull();
    expect(screen.getByTestId('bill-step-back-waiting-payment')).toBeInTheDocument();
  });

  it('downloads the document by number, not by route', async () => {
    const user = userEvent.setup();
    render(<BillDetailDrawer selected={aBill()} onClose={vi.fn()} />);

    await user.click(screen.getByTestId('bill-download'));

    expect(download).toHaveBeenCalledWith({
      id: 'bill-1',
      number: 'FA-2026-000001',
    });
  });

  it('cannot download an invoice whose document was never stored', () => {
    // A button that answers 503 is worse than one that is plainly unavailable.
    // Asserted as disabled rather than by clicking it: a disabled control has
    // no pointer events, so a click test would be asserting on the test
    // library's own refusal rather than on the screen.
    render(
      <BillDetailDrawer selected={aBill({ document_key: null })} onClose={vi.fn()} />,
    );

    expect(screen.getByTestId('bill-download')).toBeDisabled();
  });

  it('shows the total the customer is asked to pay', () => {
    render(<BillDetailDrawer selected={aBill()} onClose={vi.fn()} />);

    expect(screen.getByTestId('bill-total-ttc')).toHaveTextContent('67.33');
  });

  it('says so when an invoice charges nothing', () => {
    const empty = aBill({
      lines: [],
      total_ht: '0.00',
      total_vat: '0.00',
      total_ttc: '0.00',
    });
    render(<BillDetailDrawer selected={empty} onClose={vi.fn()} />);

    expect(screen.getByTestId('bill-no-line')).toHaveTextContent('bills.noLine');
  });
});

/** The statuses, so the neighbour rule is asserted from each of them. */
const EVERY_STATUS: BillStatus[] = [
  'to-be-validated',
  'accepted',
  'waiting-payment',
  'paid',
];

describe('BillDetailDrawer lifecycle', () => {
  it.each(EVERY_STATUS)('offers at most one move each way from %s', (status) => {
    render(<BillDetailDrawer selected={aBill({ status })} onClose={vi.fn()} />);

    const drawer = screen.getByTestId('bill-detail-drawer');
    const advances = drawer.querySelectorAll('[data-testid^="bill-advance-"]');
    const backs = drawer.querySelectorAll('[data-testid^="bill-step-back-"]');

    expect(advances.length).toBeLessThanOrEqual(1);
    expect(backs.length).toBeLessThanOrEqual(1);
  });
});

describe('BillDetailDrawer — who is billed', () => {
  it('says nothing when the household pays its own invoice', () => {
    // The overwhelmingly common case. A line repeating the customer's name
    // under their own name is noise on every invoice the agency issues.
    render(<BillDetailDrawer selected={aBill()} onClose={vi.fn()} />);

    expect(screen.queryByTestId('bill-recipient')).not.toBeInTheDocument();
  });

  it('names the payer when somebody else is being asked for the money', () => {
    // The single most important fact on the screen when it is true: the person
    // cared for is not the person being invoiced.
    const funded: Bill = aBill({
      recipient: {
        ...aBill().recipient,
        kind: 'public',
        name: 'Conseil départemental de Paris',
        siren: '130025265',
      },
    });

    render(<BillDetailDrawer selected={funded} onClose={vi.fn()} />);

    const line = screen.getByTestId('bill-recipient');
    expect(line).toHaveTextContent('Conseil départemental de Paris');
    expect(line).toHaveTextContent('130025265');
  });
});
