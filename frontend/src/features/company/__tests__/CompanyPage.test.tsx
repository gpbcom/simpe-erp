import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CompanyPage } from '../CompanyPage';
import type { Company } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

const uploadLogo = vi.fn();
const removeLogo = vi.fn();
const updateCompany = vi.fn();
const query = { data: undefined as Company | undefined, isLoading: false, isError: false };
let role: string | undefined = 'admin';

vi.mock('@/api/queries', () => ({
  useMyCompany: () => query,
  useUpdateMyCompany: () => ({ mutate: updateCompany, isPending: false }),
  useUploadCompanyLogo: () => ({ mutate: uploadLogo, isPending: false }),
  useRemoveCompanyLogo: () => ({ mutate: removeLogo, isPending: false }),
}));

vi.mock('@/store/session', () => ({
  useSession: (selector: (state: { user: { role?: string } }) => unknown) =>
    selector({ user: { role } }),
}));

const AGENCY: Company = {
  id: 'company-1',
  name: 'Aide Domicile Paris',
  registration_number: '12345678900011',
  legal_form: 'SARL',
  share_capital: '10000.00',
  rcs_number: 'RCS Paris B 123 456 789',
  vat_number: 'FR12345678901',
  phone_number: '01 23 45 67 89',
  contact_email: 'contact@simple-erp.fr',
  address: null,
  iban: 'FR7630006000011234567890189',
  bic: 'BNPAFRPP',
  logo_url: null,
  is_accepting_applications: true,
  created_at: null,
  updated_at: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  role = 'admin';
  query.data = AGENCY;
  query.isLoading = false;
  query.isError = false;
});

/**
 * The agency's own screen: its identity, its bank account and its letterhead.
 *
 * The permissions are enforced on the server — every route here is
 * administrator-gated and the profile payload cannot carry a logo URL — so
 * these cases are about the *screen* keeping its half of the promise.
 */
describe('CompanyPage', () => {
  it('shows nothing but a refusal to a manager', () => {
    role = 'manager';

    render(<CompanyPage />);

    expect(screen.getByTestId('company-forbidden')).toBeInTheDocument();
    expect(screen.queryByTestId('company-iban')).not.toBeInTheDocument();
  });

  it('reports a failed read rather than an empty form', () => {
    query.data = undefined;
    query.isError = true;

    render(<CompanyPage />);

    expect(screen.queryByTestId('company-section')).not.toBeInTheDocument();
  });

  it('prefills the account the administrator is entitled to read whole', () => {
    render(<CompanyPage />);

    expect(screen.getByTestId('company-iban')).toHaveValue(
      'FR7630006000011234567890189',
    );
    expect(screen.getByTestId('company-bic')).toHaveValue('BNPAFRPP');
  });

  it('sends the bank details on save', async () => {
    const user = userEvent.setup();
    render(<CompanyPage />);

    await user.click(screen.getByTestId('save-company'));

    expect(updateCompany).toHaveBeenCalledTimes(1);
    expect(updateCompany.mock.calls[0]![0]).toMatchObject({
      iban: 'FR7630006000011234567890189',
      bic: 'BNPAFRPP',
    });
  });

  it('sends an emptied account as null, not as an empty string', async () => {
    const user = userEvent.setup();
    render(<CompanyPage />);

    await user.clear(screen.getByTestId('company-iban'));
    await user.click(screen.getByTestId('save-company'));

    expect(updateCompany.mock.calls[0]![0].iban).toBeNull();
  });

  it('never sends a logo url with the profile', async () => {
    const user = userEvent.setup();
    query.data = { ...AGENCY, logo_url: 'https://s3/simple-erp/company-logos/c/a.png' };
    render(<CompanyPage />);

    await user.click(screen.getByTestId('save-company'));

    expect(updateCompany.mock.calls[0]![0]).not.toHaveProperty('logo_url');
  });

  it('offers no Remove button when the agency has no logo', () => {
    render(<CompanyPage />);

    expect(screen.getByTestId('upload-logo')).toBeInTheDocument();
    expect(screen.queryByTestId('remove-logo')).not.toBeInTheDocument();
  });

  it('offers Remove once a logo is stored', () => {
    query.data = { ...AGENCY, logo_url: 'https://s3/simple-erp/company-logos/c/a.png' };

    render(<CompanyPage />);

    expect(screen.getByTestId('remove-logo')).toBeInTheDocument();
  });

  it('uploads a chosen file straight away', async () => {
    const user = userEvent.setup();
    render(<CompanyPage />);
    const file = new File(['x'], 'mark.png', { type: 'image/png' });

    await user.upload(screen.getByTestId('logo-input'), file);

    expect(uploadLogo).toHaveBeenCalledWith(file);
    // The Save button is for the form; the logo is already stored by now.
    expect(updateCompany).not.toHaveBeenCalled();
  });

  it('clears the picker so the same file can be retried', async () => {
    const user = userEvent.setup();
    render(<CompanyPage />);
    const input = screen.getByTestId('logo-input') as HTMLInputElement;

    await user.upload(input, new File(['x'], 'mark.png', { type: 'image/png' }));

    expect(input.value).toBe('');
  });

  it('removes the stored logo on demand', async () => {
    const user = userEvent.setup();
    query.data = { ...AGENCY, logo_url: 'https://s3/simple-erp/company-logos/c/a.png' };
    render(<CompanyPage />);

    await user.click(screen.getByTestId('remove-logo'));

    expect(removeLogo).toHaveBeenCalledTimes(1);
  });
});
