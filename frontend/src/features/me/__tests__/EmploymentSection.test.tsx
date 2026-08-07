import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EmploymentSection } from '../EmploymentSection';
import type { Hca } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const mutate = vi.fn();

vi.mock('@/api/queries', () => ({
  useUpdateEmployment: () => ({ mutate, isPending: false }),
  useCertificationTypes: () => ({ data: [] }),
}));

const PROFILE: Hca = {
  id: 'hca-1',
  first_name: 'Amina',
  last_name: 'Benali',
  phone_number: '+33612345678',
  email: 'amina.benali@simple-erp.fr',
  address: {
    street: '18 rue de Charonne',
    postal_code: '75011',
    city: 'Paris',
    country: 'France',
    latitude: 48.8534,
    longitude: 2.3776,
    geocoding_error: null,
  },
  contract_type: 'cdi',
  certifications: [],
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
 * Who may take somebody off the rounds, asserted on the control itself.
 *
 * The rule is enforced on the server — the route is manager-gated and the
 * self-service payload has no such field — so these cases are about the
 * *screen* keeping its half of the promise: the flag is always shown, and it
 * is editable for exactly one of the two roles.
 *
 * Both cases query the same `field-employee` test id on purpose — it names
 * the control, not the variant. They are told apart by looking inside it: a
 * `Switch` wraps a real checkbox, a locked `Chip` wraps nothing. A second
 * identifier would be a second thing to keep in step with the first.
 */
describe('EmploymentSection', () => {
  it('lets a manager or an administrator take somebody off the rounds', async () => {
    const user = userEvent.setup();
    render(<EmploymentSection profile={PROFILE} editable />);

    const control = within(screen.getByTestId('field-employee')).getByRole(
      'checkbox',
    );
    expect(control).toBeChecked();

    // Saving is disabled until something changes, so the flag flipping is
    // what enables the button — proving the switch is wired to the payload
    // and not merely rendered beside it.
    expect(screen.getByTestId('save-employment')).toBeDisabled();
    await user.click(control);
    await user.click(screen.getByTestId('save-employment'));

    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ field_employee: false }),
    );
  });

  it('shows an assistant the flag locked rather than hiding it', () => {
    render(<EmploymentSection profile={PROFILE} editable={false} />);

    // Shown: a page that omits what it will not let you change answers "what
    // does this system say about me?" with silence.
    const control = screen.getByTestId('field-employee');
    expect(control).toBeVisible();

    // Locked: a chip naming who owns the field, not a disabled input. There
    // is nothing to toggle in it and nothing to save.
    expect(within(control).queryByRole('checkbox')).toBeNull();
    expect(screen.queryByTestId('save-employment')).toBeNull();
  });
});
