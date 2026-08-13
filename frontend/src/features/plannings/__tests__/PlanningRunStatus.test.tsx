import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PlanningRunStatus } from '../PlanningRunStatus';
import type { PlanningRun, UnplacedQuote } from '@/api/types';

// The stand-in interpolates rather than returning the bare key. The partial
// report nests one lookup inside another — the reason is translated and then
// substituted into the sentence — and a `t` that dropped its values would let
// a test pass while the reason never reached the screen at all.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values
        ? `${key}(${Object.entries(values)
            .map(([name, value]) => `${name}=${String(value)}`)
            .join(',')})`
        : key,
  }),
}));

const RUN: PlanningRun = {
  id: 'run-1',
  status: 'succeeded',
  team_id: 'team-1',
  requested_by: 'admin@simple-erp.fr',
  period_start: '2026-08-10',
  period_end: '2026-08-16',
  started_at: '2026-08-10T08:00:00Z',
  finished_at: '2026-08-10T08:01:00Z',
  total_travel_minutes: 1240,
  scheduled_count: 95,
  is_optimised: true,
  unplaced_quotes: [],
  unassigned_requirement_ids: [],
  error_message: null,
};

/**
 * What the last run says about itself.
 *
 * The case worth pinning is the middle one. A run that placed every visit but
 * never proved its rounds shortest is a success with a caveat, and if the
 * screen renders it identically to a fully optimised run then the caveat may
 * as well not be recorded — a slow creep in travel would have no symptom.
 */
describe('PlanningRunStatus', () => {
  it('reports an optimised run as a plain success', () => {
    render(<PlanningRunStatus run={RUN} />);

    const alert = screen.getByTestId('planning-run-status');
    expect(alert).toHaveTextContent('planning.runSucceeded');
    expect(alert.className).toContain('MuiAlert-colorSuccess');
  });

  it('says so when the rounds were not proved shortest', () => {
    render(<PlanningRunStatus run={{ ...RUN, is_optimised: false }} />);

    const alert = screen.getByTestId('planning-run-status');
    expect(alert).toHaveTextContent('planning.runSucceededUnoptimised');
    // Info, not error: every visit is scheduled and the week is usable.
    expect(alert.className).toContain('MuiAlert-colorInfo');
  });

  it('treats an older run with no answer as an ordinary success', () => {
    // `null` is a run from before the two-pass solve, which never asked the
    // question. Rendering it as unoptimised would invent a finding about it.
    render(<PlanningRunStatus run={{ ...RUN, is_optimised: null }} />);

    const alert = screen.getByTestId('planning-run-status');
    expect(alert).toHaveTextContent('planning.runSucceeded');
    expect(alert.className).toContain('MuiAlert-colorSuccess');
  });

  it('shows the server message verbatim when a run failed', () => {
    // It names every visit that could not be placed and why, which is the
    // whole value of a failed run.
    render(
      <PlanningRunStatus
        run={{ ...RUN, status: 'failed', error_message: '3 of 95 visit(s)…' }}
      />,
    );

    expect(screen.getByTestId('planning-run-status')).toHaveTextContent(
      '3 of 95 visit(s)…',
    );
  });

  it('renders nothing before any run has been started', () => {
    render(<PlanningRunStatus run={null} />);

    expect(screen.queryByTestId('planning-run-status')).toBeNull();
  });

  it('names the quote, the customer and the reason on a partial run', () => {
    // The whole point of the change: an operator must be able to see which
    // quote is affected and why, without reading a solver status.
    const quote: UnplacedQuote = {
      quote_reference: 'DEV-2026-0042',
      customer_id: 'customer-1',
      customer_name: 'Marie Durand',
      visits: [
        {
          requirement_id: 'req-1',
          name: 'Aide a la toilette',
          customer_id: 'customer-1',
          customer_name: 'Marie Durand',
          quote_reference: 'DEV-2026-0042',
          day: '2026-08-17',
          reason: 'missing-certification',
          detail: null,
          quote_line_id: 'line-1',
          alternatives: [],
        },
      ],
      alternatives: [],
    };
    render(
      <PlanningRunStatus
        run={{
          ...RUN,
          status: 'partial',
          scheduled_count: 89,
          unplaced_quotes: [quote],
        }}
      />,
    );

    const alert = screen.getByTestId('planning-run-status');
    // Warning, not error: the week was planned and saved.
    expect(alert.className).toContain('MuiAlert-colorWarning');
    expect(screen.getByTestId('unplaced-quote-DEV-2026-0042')).toHaveTextContent(
      'planning.runPartialQuote',
    );
    expect(alert).toHaveTextContent('planning.reason.missing-certification');
  });

  it('counts the unplaced visits rather than trusting a total', () => {
    // The heading arithmetic is the one thing a reader checks against the
    // calendar, so it is derived from the report itself.
    const visit = (id: string) => ({
      requirement_id: id,
      name: 'Aide a la toilette',
      customer_id: 'customer-1',
      customer_name: 'Marie Durand',
      quote_reference: 'DEV-2026-0042',
      day: '2026-08-17',
      reason: 'out-of-radius' as const,
      detail: null,
      quote_line_id: 'line-1',
      alternatives: [],
    });
    render(
      <PlanningRunStatus
        run={{
          ...RUN,
          status: 'partial',
          scheduled_count: 88,
          unplaced_quotes: [
            {
              quote_reference: 'DEV-2026-0042',
              customer_id: 'customer-1',
              customer_name: 'Marie Durand',
              visits: [visit('req-1'), visit('req-2')],
              alternatives: [],
            },
          ],
        }}
      />,
    );

    expect(screen.getByTestId('planning-run-status')).toHaveTextContent(
      'planning.runPartialTitle',
    );
  });
});
