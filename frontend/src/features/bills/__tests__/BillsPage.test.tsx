import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BillsPage } from '../BillsPage';
import type { Bill } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string) => key,
  }),
}));

const filterState = {
  filter: {} as Record<string, string | boolean | undefined>,
  draft: {} as Record<string, string | boolean | undefined>,
  setText: vi.fn(),
  setChoice: vi.fn(),
  setFlag: vi.fn(),
  reset: vi.fn(),
  isFiltered: false,
};

vi.mock('@/components/filters/entityFilter', () => ({
  useEntityFilter: () => filterState,
  filterQuery: () => '',
}));

vi.mock('@/components/filters/EntityFilterBar', () => ({
  EntityFilterBar: () => <div data-testid="bill-filter-bar" />,
}));

const query = { data: undefined as Bill[] | undefined, isLoading: false };

vi.mock('@/api/queries', () => ({
  // The rules tab renders the e-invoicing warning, which asks whether a
  // platform is connected. Stubbed as "one is" so these tests stay about
  // the invoicing rules; the warning has its own tests.
  useIntegrations: () => ({ data: [{ enabled: true }], isLoading: false }),
  useBills: () => query,
  useBill: () => ({ data: undefined }),
  useBillingRun: () => ({ data: undefined }),
  useBillingSettings: () => ({ data: undefined }),
  useStartBillingRun: () => ({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    isError: false,
  }),
  useSetBillStatus: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useDownloadBill: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}));

const MARCH: Bill = {
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
  lines: [],
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
};

beforeEach(() => {
  query.data = undefined;
  query.isLoading = false;
  vi.clearAllMocks();
});

/**
 * The billing screen: the list, and the way into generating a period.
 *
 * A month nobody notices is a month nobody invoices, so what these pin is that
 * the invoices are visible, that their state is legible at a glance, and that
 * the button which creates them is reachable without a filter being set first.
 */
describe('BillsPage', () => {
  it('renders the grid while the invoices are still loading', () => {
    // An empty page with no spinner reads as "you have never billed anybody",
    // which is a different and much more alarming statement.
    query.isLoading = true;
    render(<BillsPage />);

    expect(screen.getByTestId('bills-grid')).toBeInTheDocument();
  });

  it('shows an agency with no invoices its empty list', () => {
    query.data = [];
    render(<BillsPage />);

    expect(screen.getByTestId('bills-page')).toBeInTheDocument();
    expect(screen.getByTestId('bills-grid')).toBeInTheDocument();
  });

  it('lists an invoice by its number and its customer', () => {
    query.data = [MARCH];
    render(<BillsPage />);

    const grid = screen.getByTestId('bills-grid');
    expect(grid).toHaveTextContent('FA-2026-000001');
    expect(grid).toHaveTextContent('Jeanne Vincent');
  });

  it('shows what state each invoice is in without opening it', () => {
    // **The reason the queue is not a separate screen.** Filtering this list to
    // `to-be-validated` is the queue, so the status has to be legible in the
    // row rather than one click away.
    query.data = [MARCH];
    render(<BillsPage />);

    expect(screen.getByTestId('bill-status-to-be-validated')).toBeInTheDocument();
  });

  it('offers generating a period without needing a filter first', () => {
    // The button is the entry point to the whole feature. Hidden behind a
    // filter or an empty state, an agency that has never billed would have no
    // way to start.
    query.data = [];
    render(<BillsPage />);

    expect(screen.getByTestId('generate-bills')).toBeInTheDocument();
  });

  it('opens the generation dialog when the button is pressed', async () => {
    const user = userEvent.setup();
    query.data = [];
    render(<BillsPage />);

    await user.click(screen.getByTestId('generate-bills'));

    expect(screen.getByTestId('generate-bills-dialog')).toBeInTheDocument();
  });

  it('says plainly that generating sends nothing', async () => {
    // **The one sentence that stops a manager hunting for emails.** Generating
    // writes invoices that wait for validation; a manager who assumed the
    // customers had been mailed would spend the afternoon looking.
    const user = userEvent.setup();
    query.data = [];
    render(<BillsPage />);

    await user.click(screen.getByTestId('generate-bills'));

    expect(screen.getByTestId('generate-bills-dialog')).toHaveTextContent(
      'bills.generateHelp',
    );
  });
});
