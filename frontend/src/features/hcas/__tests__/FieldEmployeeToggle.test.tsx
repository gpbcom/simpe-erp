import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FieldEmployeeToggle } from '../FieldEmployeeToggle';
import type { Hca } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const mutate = vi.fn();

vi.mock('@/api/queries', () => ({
  useUpdateEmployment: () => ({ mutate, isPending: false }),
}));

const HCA: Hca = {
  id: 'hca-1',
  first_name: 'Marc',
  last_name: 'Dubois',
  phone_number: '+33612345678',
  email: 'marc.dubois@simple-erp.fr',
  address: {
    street: '22 rue de Belleville',
    postal_code: '75020',
    city: 'Paris',
    country: 'France',
    latitude: 48.8722,
    longitude: 2.3795,
    geocoding_error: null,
  },
  contract_type: 'cdd',
  certifications: [{ name: 'DEAES', code: 'DEAES', issuer: null, obtained_on: null, expires_on: null }],
  skills: [],
  driving_license: null,
  photo_url: null,
  availability: [],
  working_weekdays: ['monday'],
  field_employee: true,
  created_at: null,
  updated_at: null,
};

/**
 * Taking somebody off the rounds from the grid they are read in.
 *
 * The column used to be a chip, changeable only from inside a dialog labelled
 * "edit the qualifications" — which is not where anybody looks for it. These
 * cases pin the two things that make the cell safe to click: it sends the
 * whole employment payload, and it keeps its label.
 */
describe('FieldEmployeeToggle', () => {
  it('sends the rest of the employment record back unchanged', async () => {
    const user = userEvent.setup();
    render(<FieldEmployeeToggle hca={HCA} />);

    await user.click(
      within(screen.getByTestId('field-employee-hca-1')).getByRole('checkbox'),
    );

    // The route replaces all three fields, so a toggle that sent only the
    // flag would clear the contract and the qualifications beside it.
    expect(mutate).toHaveBeenCalledWith({
      contract_type: 'cdd',
      certifications: HCA.certifications,
      field_employee: false,
    });
  });

  it('still reads as a word, not only as a switch', () => {
    render(<FieldEmployeeToggle hca={{ ...HCA, field_employee: false }} />);

    // The column is scanned down twelve rows far more often than it is
    // clicked. A bare switch says whether it can be changed, not what it is.
    expect(screen.getByTestId('field-employee-hca-1')).toHaveTextContent(
      'hcas.notFieldEmployee',
    );
  });
});
