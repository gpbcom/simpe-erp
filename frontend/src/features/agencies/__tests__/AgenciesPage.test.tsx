import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AgenciesPage } from '../AgenciesPage';
import type { Agency } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

const query = {
  data: undefined as Agency[] | undefined,
  isLoading: false,
  isError: false,
};

vi.mock('@/api/queries', () => ({
  useAgencies: () => query,
  useCreateAgency: () => ({ mutateAsync: vi.fn() }),
  useUpdateAgency: () => ({ mutateAsync: vi.fn() }),
  useDeleteAgency: () => ({ mutateAsync: vi.fn() }),
  useAgencyMembers: () => ({ data: [], isLoading: false }),
  useAddAgencyMember: () => ({ mutateAsync: vi.fn() }),
  useRemoveAgencyMember: () => ({ mutateAsync: vi.fn() }),
  useUsers: () => ({ data: [] }),
  useHcas: () => ({ data: [] }),
}));

const HEAD_OFFICE: Agency = {
  id: 'agency-1',
  company_id: 'company-1',
  name: 'Siege Paris',
  agency_type: 'hq',
  address: {
    street: '10 rue de la Roquette',
    postal_code: '75011',
    city: 'Paris',
    country: 'France',
    latitude: 48.8551,
    longitude: 2.372,
    geocoding_error: null,
  },
  is_headquarters: true,
  member_count: 27,
  team_count: 1,
  created_at: null,
  updated_at: null,
};

const BRANCH: Agency = {
  ...HEAD_OFFICE,
  id: 'agency-2',
  name: 'Antenne Lyon',
  agency_type: 'office',
  address: null,
  is_headquarters: false,
  member_count: 0,
  team_count: 0,
};

describe('AgenciesPage', () => {
  beforeEach(() => {
    query.data = undefined;
    query.isLoading = false;
    query.isError = false;
  });

  it('reports a failed read rather than an empty company', () => {
    query.isError = true;

    render(<AgenciesPage />);

    expect(screen.getByTestId('agencies-error')).toBeInTheDocument();
    expect(screen.queryByTestId('agencies-empty')).not.toBeInTheDocument();
  });

  it('says a company with no site can have one, rather than showing nothing', () => {
    query.data = [];

    render(<AgenciesPage />);

    expect(screen.getByTestId('agencies-empty')).toBeInTheDocument();
  });

  it('lists every site with what it is', () => {
    query.data = [HEAD_OFFICE, BRANCH];

    render(<AgenciesPage />);

    expect(screen.getByTestId('agency-type-agency-1')).toHaveTextContent(
      'agencyType.hq',
    );
    expect(screen.getByTestId('agency-type-agency-2')).toHaveTextContent(
      'agencyType.office',
    );
  });

  it('shows both counts, because the delete refusal is built on them', () => {
    query.data = [HEAD_OFFICE];

    render(<AgenciesPage />);

    expect(screen.getByTestId('agency-members-agency-1')).toHaveTextContent('27');
    expect(screen.getByTestId('agency-teams-agency-1')).toHaveTextContent('1');
  });

  it('offers a site with no address as a dash rather than as blank', () => {
    query.data = [BRANCH];

    render(<AgenciesPage />);

    expect(screen.getByTestId('agencies-grid')).toHaveTextContent('—');
  });

  it('offers the roster and the editor on every row', () => {
    query.data = [HEAD_OFFICE];

    render(<AgenciesPage />);

    expect(screen.getByTestId('edit-agency-agency-1')).toBeInTheDocument();
    expect(screen.getByTestId('agency-people-agency-1')).toBeInTheDocument();
  });
});
