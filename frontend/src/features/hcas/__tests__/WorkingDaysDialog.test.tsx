import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorkingDaysDialog } from '../WorkingDaysDialog';
import type { Hca } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const mutate = vi.fn();
vi.mock('@/api/queries', () => ({
  useSetWorkingDays: () => ({
    mutate,
    isPending: false,
    isError: false,
    isSuccess: false,
  }),
}));

function hca(days: Hca['working_weekdays']): Hca {
  return {
    id: 'hca-1',
    first_name: 'Amina',
    last_name: 'Benali',
    phone_number: '+33600000001',
    email: 'amina@example.com',
    address: {
      street: '1 rue A',
      postal_code: '75001',
      city: 'Paris',
      country: 'France',
      latitude: 48.85,
      longitude: 2.35,
      geocoding_error: null,
    },
    contract_type: 'cdi',
    certifications: [],
    skills: [],
    driving_license: null,
    photo_url: null,
    availability: [],
    working_weekdays: days,
    field_employee: true,
    created_at: null,
    updated_at: null,
  };
}

describe('WorkingDaysDialog', () => {
  beforeEach(() => mutate.mockClear());

  it('offers all seven days, weekends included', () => {
    // The requirement in one assertion. Nothing ever refused Saturday or
    // Sunday — the Monday-to-Friday *default* is what made them look barred.
    render(<WorkingDaysDialog hca={hca(['monday'])} onClose={vi.fn()} />);

    expect(screen.getByTestId('rota-day-list').querySelectorAll('[data-testid^="rota-day-"]'))
      .toHaveLength(7);
    expect(screen.getByTestId('rota-day-saturday')).toBeInTheDocument();
    expect(screen.getByTestId('rota-day-sunday')).toBeInTheDocument();
  });

  it('shows the stored week as selected and the rest as not', () => {
    render(<WorkingDaysDialog hca={hca(['monday', 'saturday'])} onClose={vi.fn()} />);

    expect(screen.getByTestId('rota-day-monday')).toHaveAttribute('data-selected', 'true');
    expect(screen.getByTestId('rota-day-saturday')).toHaveAttribute('data-selected', 'true');
    expect(screen.getByTestId('rota-day-tuesday')).toHaveAttribute('data-selected', 'false');
  });

  it('can add a weekend day to a Monday-to-Friday week', async () => {
    render(
      <WorkingDaysDialog
        hca={hca(['monday', 'tuesday', 'wednesday', 'thursday', 'friday'])}
        onClose={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByTestId('rota-day-sunday'));
    await userEvent.click(screen.getByTestId('save-rota'));

    // Sent in ISO order regardless of the order clicked: the whole week is
    // submitted, and two weeks that mean the same thing must compare equal.
    expect(mutate).toHaveBeenCalledWith(
      ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'sunday'],
      expect.anything(),
    );
  });

  it('sends the whole week, never the day that was clicked', async () => {
    render(<WorkingDaysDialog hca={hca(['monday'])} onClose={vi.fn()} />);

    await userEvent.click(screen.getByTestId('rota-day-saturday'));
    await userEvent.click(screen.getByTestId('save-rota'));

    // Not `['saturday']`. A delta would let two tabs race into a week nobody
    // chose; last-write-wins on a whole week is at least somebody's week.
    expect(mutate).toHaveBeenCalledWith(['monday', 'saturday'], expect.anything());
  });

  it('refuses a week with no day rather than sending it', async () => {
    render(<WorkingDaysDialog hca={hca(['monday'])} onClose={vi.fn()} />);

    await userEvent.click(screen.getByTestId('rota-day-monday'));

    expect(screen.getByTestId('rota-empty')).toBeInTheDocument();
    expect(screen.getByTestId('save-rota')).toBeDisabled();
    expect(mutate).not.toHaveBeenCalled();
  });

  it('cannot save a week nobody changed', () => {
    render(<WorkingDaysDialog hca={hca(['monday', 'friday'])} onClose={vi.fn()} />);

    expect(screen.getByTestId('save-rota')).toBeDisabled();
  });

  it('is closed when it has nobody to edit', () => {
    render(<WorkingDaysDialog hca={null} onClose={vi.fn()} />);

    expect(screen.queryByTestId('rota-day-list')).toBeNull();
  });

  it('keeps its test ids clear of the read-only grid chips', () => {
    // Suite 29 counts `[data-testid^="working-day-"]`, and the workforce grid
    // prints its own chips under that prefix. Sharing it would make the dialog
    // inflate a count that is asserted elsewhere.
    render(<WorkingDaysDialog hca={hca(['monday'])} onClose={vi.fn()} />);

    expect(document.querySelectorAll('[data-testid^="working-day-"]')).toHaveLength(0);
  });
});
