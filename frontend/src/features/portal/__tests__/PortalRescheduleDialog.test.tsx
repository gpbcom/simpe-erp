import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PortalRescheduleDialog } from '../PortalRescheduleDialog';
import type { Intervention } from '@/api/types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const mutate = vi.fn();

vi.mock('@/api/queries', () => ({
  useRescheduleVisit: () => ({ mutate, isPending: false }),
}));

const VISIT: Intervention = {
  id: 'intervention-1',
  planning_run_id: 'run-1',
  name: 'Toilette',
  intervention_type_id: 'type-1',
  quote_line_id: 'line-1',
  hca_id: 'hca-1',
  hca_full_name: 'Luc Martin',
  customer_id: 'customer-1',
  address: {
    street: '12 rue de Rivoli',
    postal_code: '75004',
    city: 'Paris',
    country: 'France',
    latitude: 48.8558,
    longitude: 2.3588,
    geocoding_error: null,
  },
  day: '2026-09-14',
  start_time: '09:00',
  end_time: '10:00',
  status: 'planned',
};

describe('PortalRescheduleDialog', () => {
  it('pre-fills a window wider than the visit', () => {
    // A window exactly as long as the work leaves the solver nowhere to put it,
    // so the visit comes back unplaced — which reads to the household as their
    // change having been ignored rather than refused.
    render(<PortalRescheduleDialog visit={VISIT} onClose={vi.fn()} onDone={vi.fn()} />);

    expect(screen.getByTestId('portal-not-before')).toHaveValue('08:00');
    expect(screen.getByTestId('portal-not-after')).toHaveValue('11:00');
    expect(screen.getByTestId('portal-new-day')).toHaveValue('2026-09-14');
  });

  it('refuses a window that ends before it starts', async () => {
    const user = userEvent.setup();
    render(<PortalRescheduleDialog visit={VISIT} onClose={vi.fn()} onDone={vi.fn()} />);

    await user.clear(screen.getByTestId('portal-not-after'));
    await user.type(screen.getByTestId('portal-not-after'), '07:00');
    await user.click(screen.getByTestId('portal-reschedule-confirm'));

    expect(screen.getByTestId('portal-reschedule-error')).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
  });

  it('sends minutes from midnight, not clock times', async () => {
    // The unit the solver works in, and what every other time on the wire uses.
    const user = userEvent.setup();
    mutate.mockClear();
    render(<PortalRescheduleDialog visit={VISIT} onClose={vi.fn()} onDone={vi.fn()} />);

    await user.click(screen.getByTestId('portal-reschedule-confirm'));

    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        interventionId: 'intervention-1',
        day: '2026-09-14',
        start_minute: 480,
        end_minute: 660,
      }),
      expect.anything(),
    );
  });

  it('warns that the agency has to agree', () => {
    // The change is not applied when the household presses the button — it is
    // requested. A dialog that does not say so leaves them expecting a calendar
    // that updates.
    render(<PortalRescheduleDialog visit={VISIT} onClose={vi.fn()} onDone={vi.fn()} />);

    expect(screen.getByText('portal.rescheduleWarning')).toBeInTheDocument();
  });

  it('is closed when there is no visit', () => {
    render(<PortalRescheduleDialog visit={null} onClose={vi.fn()} onDone={vi.fn()} />);

    expect(screen.queryByTestId('portal-reschedule-dialog')).not.toBeInTheDocument();
  });
});
