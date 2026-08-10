import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QuotePlanningFeedback } from '../QuotePlanningFeedback';
import type { SuggestedSlot, UnplacedQuote } from '@/api/types';

// Interpolating, not key-echoing: the reason is translated and then
// substituted into a sentence, and a `t` that dropped its values would let a
// test pass while the reason never reached the screen.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, values?: Record<string, unknown>) =>
      values
        ? `${key}(${Object.entries(values)
            .map(([name, value]) => `${name}=${String(value)}`)
            .join(',')})`
        : key,
  }),
}));

const mutate = vi.fn();

vi.mock('@/api/queries', () => ({
  useRescheduleQuoteLine: () => ({ mutate, isPending: false }),
}));

const MONDAY: SuggestedSlot = {
  day: '2026-08-17',
  start_minute: 14 * 60 + 30,
  end_minute: 16 * 60 + 30,
  hca_id: 'hca-2',
  hca_name: 'Amina Benali',
};

const TUESDAY: SuggestedSlot = {
  day: '2026-08-18',
  start_minute: 9 * 60,
  end_minute: 11 * 60,
  hca_id: 'hca-3',
  hca_name: 'Fatou Diallo',
};

const FEEDBACK: UnplacedQuote = {
  quote_reference: 'D-2648',
  customer_id: 'customer-1',
  customer_name: 'Jeanne Vincent',
  visits: [
    {
      requirement_id: 'req-1',
      name: 'Entretien du logement',
      customer_id: 'customer-1',
      customer_name: 'Jeanne Vincent',
      quote_reference: 'D-2648',
      day: '2026-08-18',
      reason: 'no-feasible-slot',
      detail: null,
      quote_line_id: 'line-1',
      alternatives: [MONDAY, TUESDAY],
    },
  ],
  alternatives: [MONDAY, TUESDAY],
};

beforeEach(() => vi.clearAllMocks());

/**
 * What a quote says when the planner sent it back, and what a click does.
 *
 * A quote reappearing in the validation queue with no visible reason reads as
 * the system having lost it. These pin the three halves of the answer: which
 * visit failed and why, when somebody qualified is free instead, and what
 * happens when an operator accepts one of those times.
 */
describe('QuotePlanningFeedback', () => {
  it('renders nothing for a quote that plans cleanly', () => {
    // The ordinary case. No note means no problem, and a panel saying so on
    // every quote would bury the ones that need attention.
    render(<QuotePlanningFeedback feedback={null} quoteId="q-1" />);

    expect(screen.queryByTestId('quote-planning-feedback')).toBeNull();
  });

  it('says which visit failed and why', () => {
    render(<QuotePlanningFeedback feedback={FEEDBACK} quoteId="q-1" />);

    const panel = screen.getByTestId('quote-planning-feedback');
    expect(panel).toHaveTextContent('Entretien du logement');
    expect(panel).toHaveTextContent('planning.reason.no-feasible-slot');
  });

  it('offers a time with somebody named to do it', () => {
    // "Monday at 14:30" is only useful if somebody can be asked whether that
    // works, so the assistant is part of the offer.
    render(<QuotePlanningFeedback feedback={FEEDBACK} quoteId="q-1" />);

    const slot = screen.getByTestId('slot-2026-08-17-870');
    expect(slot).toHaveTextContent('Amina Benali');
    expect(slot).toHaveTextContent('14:30');
  });

  it('moves the visit onto the slot that was clicked', async () => {
    // **The whole point.** The offer names a day, a window and a person; what
    // is sent is the line to move and the time to move it to.
    const user = userEvent.setup();
    render(<QuotePlanningFeedback feedback={FEEDBACK} quoteId="q-1" />);

    await user.click(screen.getByTestId('slot-2026-08-17-870'));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0]![0]).toEqual({
      quote_line_id: 'line-1',
      day: '2026-08-17',
      start_minute: 870,
      end_minute: 990,
    });
  });

  it('sends the slot that was clicked, not the first one offered', async () => {
    // Two chips, and clicking the second must not quietly book the first.
    const user = userEvent.setup();
    render(<QuotePlanningFeedback feedback={FEEDBACK} quoteId="q-1" />);

    await user.click(screen.getByTestId('slot-2026-08-18-540'));

    expect(mutate.mock.calls[0]![0]).toMatchObject({
      day: '2026-08-18',
      start_minute: 540,
    });
  });

  it('never sends an assistant', async () => {
    // The offer names one and the quote has nowhere to keep it. Storing a
    // preference the planner need not honour would be a promise nothing keeps.
    const user = userEvent.setup();
    render(<QuotePlanningFeedback feedback={FEEDBACK} quoteId="q-1" />);

    await user.click(screen.getByTestId('slot-2026-08-17-870'));

    expect(mutate.mock.calls[0]![0]).not.toHaveProperty('hca_id');
  });

  it('groups the offers under the visit they answer', () => {
    // A quote with two unplaced visits has two sets of free times. One flat
    // list would leave an operator guessing which slot answers which problem.
    const second = {
      ...FEEDBACK.visits[0]!,
      requirement_id: 'req-2',
      quote_line_id: 'line-2',
      alternatives: [TUESDAY],
    };
    render(
      <QuotePlanningFeedback
        feedback={{ ...FEEDBACK, visits: [FEEDBACK.visits[0]!, second] }}
        quoteId="q-1"
      />,
    );

    expect(screen.getByTestId('alternatives-for-req-1')).toBeInTheDocument();
    expect(screen.getByTestId('alternatives-for-req-2')).toBeInTheDocument();
  });

  it('says so explicitly when nothing at all was free', () => {
    // "We looked and there is nothing" is a different answer from "we did not
    // look", and only the first tells a manager the week is genuinely full.
    render(
      <QuotePlanningFeedback
        feedback={{
          ...FEEDBACK,
          visits: [{ ...FEEDBACK.visits[0]!, alternatives: [] }],
        }}
        quoteId="q-1"
      />,
    );

    expect(screen.getByTestId('no-alternative-slot-req-1')).toHaveTextContent(
      'quote.planningNoAlternative',
    );
  });

  it('shows the slots without offering them when there is no quote to move', async () => {
    // The planning-run summary lists unplaced work across every quote and has
    // no single one to act on. A chip that does nothing when clicked is worse
    // than one that plainly is not a button.
    const user = userEvent.setup();
    render(<QuotePlanningFeedback feedback={FEEDBACK} />);

    const slot = screen.getByTestId('slot-2026-08-17-870');
    expect(slot).toHaveTextContent('Amina Benali');
    await user.click(slot);

    expect(mutate).not.toHaveBeenCalled();
  });

  it('does not offer a slot for a note written before lines were named', async () => {
    // An older stored note has no `quote_line_id`, so there is nothing to
    // move. It is still worth reading.
    const user = userEvent.setup();
    render(
      <QuotePlanningFeedback
        feedback={{
          ...FEEDBACK,
          visits: [{ ...FEEDBACK.visits[0]!, quote_line_id: null }],
        }}
        quoteId="q-1"
      />,
    );

    await user.click(screen.getByTestId('slot-2026-08-17-870'));

    expect(mutate).not.toHaveBeenCalled();
  });

  it('presents the whole thing as a warning, not an error', () => {
    // The rest of the week was planned and saved. Something needs a decision,
    // which is not the same as something having gone wrong.
    render(<QuotePlanningFeedback feedback={FEEDBACK} quoteId="q-1" />);

    expect(screen.getByTestId('quote-planning-feedback').className).toContain(
      'MuiAlert-colorWarning',
    );
  });
});
