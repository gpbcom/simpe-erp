import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TeamsPage } from '../TeamsPage';
import type { Agency, Team, User } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options?.name ? `${key}:${String(options.name)}` : key,
    i18n: { language: 'en' },
  }),
}));

const query = {
  data: undefined as Team[] | undefined,
  isLoading: false,
  isError: false,
};
const agencies: { data: Agency[] } = { data: [] };
const accounts: { data: User[] } = { data: [] };

vi.mock('@/api/queries', () => ({
  useTeams: () => query,
  useAgencies: () => agencies,
  useUsers: () => accounts,
  useCreateTeam: () => ({ mutateAsync: vi.fn() }),
  useUpdateTeam: () => ({ mutateAsync: vi.fn() }),
  useDeleteTeam: () => ({ mutateAsync: vi.fn() }),
  useTeamMembers: () => ({ data: [], isLoading: false }),
  useAddTeamMember: () => ({ mutateAsync: vi.fn() }),
  useRemoveTeamMember: () => ({ mutateAsync: vi.fn() }),
  useTeamDocuments: () => ({ data: [], isLoading: false }),
  useTeamDocumentConstraints: () => ({ data: undefined }),
  useHcas: () => ({ data: [] }),
  keys: { teamDocuments: (id: string) => ['teams', 'detail', id, 'documents'] },
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

const TEAM: Team = {
  id: 'team-1',
  company_id: 'company-1',
  agency_id: 'agency-1',
  name: 'Equipe principale',
  manager_user_id: 'user-1',
  member_count: 27,
  created_at: null,
  updated_at: null,
};

describe('TeamsPage', () => {
  beforeEach(() => {
    query.data = undefined;
    query.isLoading = false;
    query.isError = false;
    agencies.data = [];
    accounts.data = [];
  });

  it('reports a failed read rather than an empty company', () => {
    query.isError = true;

    render(<TeamsPage />);

    expect(screen.getByTestId('teams-error')).toBeInTheDocument();
  });

  it('says a company with no team must form one before quoting', () => {
    query.data = [];

    render(<TeamsPage />);

    expect(screen.getByTestId('teams-empty')).toBeInTheDocument();
  });

  it('resolves the site and the manager from lists it already holds', () => {
    query.data = [TEAM];
    agencies.data = [
      {
        id: 'agency-1',
        company_id: 'company-1',
        name: 'Siege Paris',
        agency_type: 'hq',
        address: null,
        is_headquarters: true,
        member_count: 27,
        team_count: 1,
        created_at: null,
        updated_at: null,
      },
    ];
    accounts.data = [
      {
        id: 'user-1',
        email: 'manager@simple-erp.fr',
        full_name: 'Nathalie Blanchard',
        role: 'manager',
        is_active: true,
        hca_id: null,
        company_id: 'company-1',
        language: 'fr',
        photo_url: null,
        must_change_password: false,
        created_at: null,
        updated_at: null,
      } as User,
    ];

    render(<TeamsPage />);

    expect(screen.getByTestId('team-agency-team-1')).toHaveTextContent('Siege Paris');
    expect(screen.getByTestId('team-manager-team-1')).toHaveTextContent(
      'Nathalie Blanchard',
    );
  });

  it('falls back to the identifier when a name cannot be resolved', () => {
    query.data = [TEAM];

    render(<TeamsPage />);

    expect(screen.getByTestId('team-agency-team-1')).toHaveTextContent('agency-1');
  });

  it('offers the roster and the shared space on every row', () => {
    query.data = [TEAM];

    render(<TeamsPage />);

    expect(screen.getByTestId('team-people-team-1')).toBeInTheDocument();
    expect(screen.getByTestId('team-documents-team-1')).toBeInTheDocument();
  });
});
