import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import type { PlanningRun } from '@/api/types';

interface PlanningRunStatusProps {
  /** The most recent run, or `null` when none has been started. */
  run: PlanningRun | null;
}

/**
 * What the last planning run did, in language an operator can act on.
 *
 * @param props - The run to describe.
 * @returns The rendered alert, or nothing when there is no run.
 *
 * @remarks
 * Its own component because the decision it makes is not obvious and is worth
 * testing on its own: the page around it mounts FullCalendar, and a test that
 * had to render all of that to assert one sentence would break for reasons
 * that have nothing to do with the sentence.
 *
 * **Four outcomes.** A failed run shows the server's message — there is no
 * plan, and the message says why. A successful run reports the count and the
 * travel. A run whose rounds were never proved shortest says so, in `info`
 * rather than `success`. And a **partial** run — a week that was planned with
 * gaps in it — gets the breakdown below.
 *
 * The partial case is why this component exists in its current shape. A run
 * used to fail outright the moment one visit could not be placed, and reported
 * it as a single sentence quoting a solver status and a configuration key.
 * That told an operator nothing they could do. What they need is *which quote*
 * is affected, *whose* it is, and *why* — so the report arrives structured and
 * the sentences are assembled here, in the reader's own language. A message
 * composed on the server would reach an English operator in French.
 *
 * `is_optimised` is checked against `false` rather than for falsiness. `null`
 * means a run from before the two-pass solve, which never asked the question;
 * treating it as unoptimised would invent a finding about a historic plan.
 *
 * The unoptimised wording says the rounds were not *proved* shortest, and
 * deliberately does not suggest raising the optimisation budget. Measured on
 * the seeded agency, tripling that budget left the travel identical at 256
 * minutes and still unproved — the plan was already optimal and the solver
 * simply could not show it. Advice that sends an operator to change a setting
 * which does not help is worse than no advice.
 */
export function PlanningRunStatus({ run }: PlanningRunStatusProps) {
  const { t } = useTranslation();
  if (!run) return null;

  if (run.status === 'partial') {
    const unplaced = run.unplaced_quotes.reduce(
      (total, quote) => total + quote.visits.length,
      0,
    );
    const planned = run.scheduled_count ?? 0;
    return (
      // Warning, not error: the week was planned and saved. Something still
      // needs a decision, which is not the same as nothing having happened.
      <Alert severity="warning" data-testid="planning-run-status">
        <AlertTitle>
          {t('planning.runPartialTitle', {
            planned,
            total: planned + unplaced,
            unplaced,
          })}
        </AlertTitle>
        <Typography variant="body2" sx={{ mb: 1 }}>
          {t('planning.runPartialLead')}
        </Typography>
        {run.unplaced_quotes.map((quote) => (
          <Box
            key={quote.quote_reference}
            sx={{ mt: 1 }}
            data-testid={`unplaced-quote-${quote.quote_reference}`}
          >
            <Typography variant="body2" fontWeight={600}>
              {t('planning.runPartialQuote', {
                reference: quote.quote_reference,
                customer: quote.customer_name,
              })}
            </Typography>
            <Box component="ul" sx={{ m: 0, pl: 3 }}>
              {quote.visits.map((visit) => (
                <Typography component="li" variant="body2" key={visit.requirement_id}>
                  {t('planning.runPartialVisit', {
                    service: visit.name,
                    day: visit.day,
                    reason: t(`planning.reason.${visit.reason}`),
                  })}
                </Typography>
              ))}
            </Box>
          </Box>
        ))}
      </Alert>
    );
  }

  const unoptimised = run.status === 'succeeded' && run.is_optimised === false;
  const severity =
    run.status === 'failed'
      ? 'error'
      : run.status === 'succeeded'
        ? unoptimised
          ? 'info'
          : 'success'
        : 'info';

  return (
    <Alert severity={severity} data-testid="planning-run-status">
      {run.status === 'failed'
        ? (run.error_message ?? t('planning.runFailed'))
        : run.status === 'succeeded'
          ? t(
              unoptimised
                ? 'planning.runSucceededUnoptimised'
                : 'planning.runSucceeded',
              {
                count: run.scheduled_count ?? 0,
                travel: run.total_travel_minutes ?? 0,
              },
            )
          : t('planning.runPending')}
    </Alert>
  );
}
