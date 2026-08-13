import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { CustomerPlanning, HcaPlanning, UserRole } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, options?: Record<string, unknown>) =>
      options && 'count' in options ? `${key}:${options.count}` : key,
  }),
}));

/**
 * FullCalendar is stubbed.
 *
 * It is the one component in this codebase that fights jsdom — it measures the
 * viewport on mount — and none of the questions here are about it. What is
 * under test is which dataset the page asks for, which rail it draws and which
 * controls it offers; the grid is somebody else's problem.
 */
vi.mock('@fullcalendar/react', () => ({
  default: ({
    weekends,
    events,
    eventClick,
  }: {
    weekends?: boolean;
    events?: { id: string; extendedProps: unknown }[];
    eventClick?: (info: { event: { extendedProps: unknown } }) => void;
  }) => (
    <div data-testid="calendar" data-weekends={String(weekends)}>
      {/* One button per block, so a test can open the drawer. Without it the
          read-only assertions below would pass against a drawer that was never
          rendered — which is to say, against nothing. */}
      {(events ?? []).map((event) => (
        <button
          key={event.id}
          type="button"
          data-testid={`calendar-event-${event.id}`}
          onClick={() =>
            eventClick?.({ event: { extendedProps: event.extendedProps } })
          }
        >
          {event.id}
        </button>
      ))}
    </div>
  ),
}));
vi.mock('@fullcalendar/timegrid', () => ({ default: {} }));
vi.mock('@fullcalendar/daygrid', () => ({ default: {} }));
vi.mock('@fullcalendar/interaction', () => ({ default: {} }));
vi.mock('@fullcalendar/core/locales/fr', () => ({ default: {} }));

const VISIT = {
  id: 'visit-1',
  planning_run_id: 'run-1',
  team_id: 'team-1',
  name: 'Toilette matin',
  intervention_type_id: 'type-1',
  quote_line_id: 'line-1',
  hca_id: 'hca-1',
  hca_full_name: 'Luc Martin',
  customer_id: 'customer-1',
  day: '2026-08-03',
  start_time: '09:00:00',
  end_time: '10:00:00',
  address: {
    street: '12 rue de Rivoli',
    postal_code: '75004',
    city: 'Paris',
    country: 'France',
    latitude: null,
    longitude: null,
    geocoding_error: null,
  },
  status: 'planned' as const,
};

const ASSISTANTS: HcaPlanning[] = [
  {
    hca_id: 'hca-1',
    hca_full_name: 'Luc Martin',
    period_start: '2026-08-03',
    period_end: '2026-09-13',
    interventions: [VISIT],
  },
];

const HOUSEHOLDS: CustomerPlanning[] = [
  {
    customer_id: 'customer-1',
    customer_full_name: 'Marie Durand',
    period_start: '2026-06-04',
    period_end: '2026-12-01',
    interventions: [VISIT],
  },
];

const allPlannings = vi.fn();
const customerPlannings = vi.fn();
const startRun = vi.fn();
let role: UserRole = 'manager';
let teams: { id: string; name: string; agency_id: string }[] = [];
let agencies: { id: string; name: string }[] = [];

vi.mock('@/store/session', () => ({
  useSession: (selector: (state: { user: { role: UserRole } }) => unknown) =>
    selector({ user: { role } }),
  hasAtLeast: (given: UserRole | undefined, minimum: UserRole) =>
    ['hca', 'manager', 'admin'].indexOf(given ?? 'hca') >=
    ['hca', 'manager', 'admin'].indexOf(minimum),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock('@/api/queries', () => ({
  useAllPlannings: (from: string, to: string, enabled: boolean) => {
    allPlannings(from, to, enabled);
    return { data: enabled ? ASSISTANTS : undefined, isLoading: false };
  },
  useCustomerPlannings: (from: string, to: string, enabled: boolean) => {
    customerPlannings(from, to, enabled);
    return { data: enabled ? HOUSEHOLDS : undefined, isLoading: false };
  },
  useCustomers: () => ({ data: [] }),
  useInterventionTypes: () => ({ data: [] }),
  usePlanningRuns: () => ({ data: [] }),
  useStartPlanningRun: () => ({ mutate: startRun, isPending: false, isError: false }),
  // The re-compute control now picks a scope — a team, a site, or the whole
  // company — so the page reads both lists to build it.
  useTeams: () => ({ data: teams }),
  useAgencies: () => ({ data: agencies }),
  useDeleteIntervention: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useChangeInterventionType: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

const { TeamPlanningPage } = await import('../TeamPlanningPage');

describe('TeamPlanningPage — choosing an audience', () => {
  beforeEach(() => {
    role = 'manager';
    allPlannings.mockClear();
    customerPlannings.mockClear();
  });

  it('opens on the assistants for a manager', () => {
    render(<TeamPlanningPage />);

    expect(screen.getByTestId('planning-audience')).toBeInTheDocument();
    expect(screen.getByTestId('planning-hca-hca-1')).toBeInTheDocument();
    expect(
      screen.queryByTestId('planning-customer-customer-1'),
    ).not.toBeInTheDocument();
  });

  it('swaps the rail when the customers lens is chosen', async () => {
    render(<TeamPlanningPage />);

    await userEvent.click(screen.getByTestId('planning-audience-customers'));

    expect(screen.getByTestId('planning-customer-customer-1')).toBeInTheDocument();
    expect(screen.queryByTestId('planning-hca-hca-1')).not.toBeInTheDocument();
  });

  it('asks for one dataset at a time', async () => {
    // **Not merely cosmetic.** A manager on the households lens still holding
    // an open query for every assistant's diary is a request nobody reads, and
    // an assistant would get a 403 from it.
    render(<TeamPlanningPage />);

    await userEvent.click(screen.getByTestId('planning-audience-customers'));

    expect(customerPlannings).toHaveBeenLastCalledWith(
      expect.any(String),
      expect.any(String),
      true,
    );
    expect(allPlannings).toHaveBeenLastCalledWith(
      expect.any(String),
      expect.any(String),
      false,
    );
  });

  it('reads the households over a wider window than the assistants', async () => {
    // The households' span is the one their own portal reads. Sharing the
    // scheduler's fortnight would show the agency a different set of weeks from
    // the family on the telephone.
    render(<TeamPlanningPage />);
    await userEvent.click(screen.getByTestId('planning-audience-customers'));

    const [staffFrom] = allPlannings.mock.calls[0] as [string, string, boolean];
    const [householdFrom] = customerPlannings.mock.calls[0] as [
      string,
      string,
      boolean,
    ];

    expect(householdFrom < staffFrom).toBe(true);
  });

  it('shows weekends on the households lens and hides them on the assistants', async () => {
    // Care does not stop on a Sunday, and the household's own space shows the
    // weekend. A scheduler reads a working week.
    render(<TeamPlanningPage />);

    expect(screen.getByTestId('calendar')).toHaveAttribute('data-weekends', 'false');

    await userEvent.click(screen.getByTestId('planning-audience-customers'));

    expect(screen.getByTestId('calendar')).toHaveAttribute('data-weekends', 'true');
  });
});

describe('TeamPlanningPage — what an assistant gets', () => {
  beforeEach(() => {
    role = 'hca';
    allPlannings.mockClear();
    customerPlannings.mockClear();
  });

  it('renders no switch', () => {
    // **A control whose other side answers 403 is a control that lies.** The
    // assistants lens is not theirs to read, so it is not offered.
    render(<TeamPlanningPage />);

    expect(screen.queryByTestId('planning-audience')).not.toBeInTheDocument();
  });

  it('lands on the households and never asks for the workforce', () => {
    render(<TeamPlanningPage />);

    expect(screen.getByTestId('planning-customer-customer-1')).toBeInTheDocument();
    expect(allPlannings).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      false,
    );
  });
});

describe('TeamPlanningPage — the households lens is read-only', () => {
  beforeEach(() => {
    role = 'manager';
  });

  it('offers retype and delete on an assistant visit', async () => {
    // The control case. Without it the assertion below would pass against a
    // drawer that never rendered the controls in either lens.
    render(<TeamPlanningPage />);

    await userEvent.click(screen.getByTestId('calendar-event-visit-1'));

    expect(screen.getByTestId('team-intervention-detail')).toBeInTheDocument();
    expect(screen.getByTestId('intervention-type-select')).toBeInTheDocument();
    expect(screen.getByTestId('delete-intervention')).toBeInTheDocument();
  });

  it('offers neither on a household visit', async () => {
    // Changing what a visit is, or removing it, rewrites the household's quote
    // and their bill. Rendering the controls and ignoring them would look
    // entirely right until somebody pressed one.
    render(<TeamPlanningPage />);
    await userEvent.click(screen.getByTestId('planning-audience-customers'));

    await userEvent.click(screen.getByTestId('calendar-event-visit-1'));

    expect(screen.getByTestId('team-intervention-detail')).toBeInTheDocument();
    expect(screen.queryByTestId('intervention-type-select')).not.toBeInTheDocument();
    expect(screen.queryByTestId('delete-intervention')).not.toBeInTheDocument();
  });
});

describe('TeamPlanningPage — choosing what to recompute', () => {
  beforeEach(() => {
    role = 'manager';
    startRun.mockClear();
    teams = [{ id: 'team-1', name: 'Équipe Paris', agency_id: 'agency-1' }];
    agencies = [
      { id: 'agency-1', name: 'Siege Paris' },
      { id: 'agency-2', name: 'Antenne Lyon' },
    ];
  });

  it('offers the whole company to an administrator only', async () => {
    // Company-wide rewrites the calendar of every assistant employed, and the
    // server refuses it for anybody else. Offering it to a manager would make
    // the button's own default a 403.
    role = 'admin';
    render(<TeamPlanningPage />);

    await userEvent.click(screen.getByRole('combobox'));

    expect(screen.getByTestId('team-picker-all')).toBeInTheDocument();
  });

  it('withholds the whole company from a manager', async () => {
    render(<TeamPlanningPage />);

    await userEvent.click(screen.getByRole('combobox'));

    expect(screen.queryByTestId('team-picker-all')).not.toBeInTheDocument();
  });

  it('offers only the sites the caller runs a team at', async () => {
    // Derived from the teams they can see, so a manager is offered the branches
    // they actually work from rather than every address the company holds.
    render(<TeamPlanningPage />);

    await userEvent.click(screen.getByRole('combobox'));

    expect(screen.getByTestId('team-picker-agency-agency-1')).toBeInTheDocument();
    expect(
      screen.queryByTestId('team-picker-agency-agency-2'),
    ).not.toBeInTheDocument();
  });

  it('defaults a manager to their site, which is the widest they may ask for', async () => {
    render(<TeamPlanningPage />);

    await userEvent.click(screen.getByTestId('compute-planning'));

    expect(startRun).toHaveBeenCalledWith(
      expect.objectContaining({ agencyId: 'agency-1' }),
    );
  });

  it('sends the team alone once one is picked', async () => {
    render(<TeamPlanningPage />);
    await userEvent.click(screen.getByRole('combobox'));
    await userEvent.click(screen.getByTestId('team-picker-team-1'));

    await userEvent.click(screen.getByTestId('compute-planning'));

    expect(startRun).toHaveBeenCalledWith(
      expect.objectContaining({ teamId: 'team-1' }),
    );
  });

  it('sends neither field for an administrator, which means the company', async () => {
    role = 'admin';
    render(<TeamPlanningPage />);

    await userEvent.click(screen.getByTestId('compute-planning'));

    expect(startRun).toHaveBeenCalledWith(
      expect.not.objectContaining({ teamId: expect.anything() }),
    );
    expect(startRun).toHaveBeenCalledWith(
      expect.not.objectContaining({ agencyId: expect.anything() }),
    );
  });

  it('disables the button for a manager who runs no team anywhere', () => {
    // There is nothing they may ask for, and a button that answers 403 is
    // worse than one that is plainly unavailable.
    teams = [];
    render(<TeamPlanningPage />);

    expect(screen.getByTestId('compute-planning')).toBeDisabled();
  });
});
