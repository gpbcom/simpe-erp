import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useRescheduleQuoteLine } from '@/api/queries';
import type { SuggestedSlot, UnplacedQuote, UnplacedVisit } from '@/api/types';
import { minutesToTime } from '@/utils/format';

interface QuotePlanningFeedbackProps {
  feedback: UnplacedQuote | null;
  /**
   * The quote the note belongs to.
   *
   * @remarks
   * Absent on the screens that only report — the planning-run summary lists
   * unplaced work across every quote and has no single one to move a line on.
   * Without it the slots are shown but not offered as clickable.
   */
  quoteId?: string;
}

/**
 * Why a quote came back to be validated, and when its work could go instead.
 *
 * @param props - The note left by the last planning run, and the quote it is on.
 * @returns The rendered panel, or nothing when the quote plans cleanly.
 *
 * @remarks
 * A quote reappearing in the validation queue a week after somebody validated
 * it reads as the system having lost it. This is the explanation that stops
 * that: which visits would not fit, why each one failed, and the times a
 * qualified assistant is free instead.
 *
 * **The offered slots are clickable, and that is the point.** Being told a
 * visit did not fit leaves an operator to telephone the customer with nothing
 * to propose; "Monday at 14:30 with Amina Benali" turns the call into a
 * decision, and accepting it here writes the new day and window onto the line
 * without anybody retyping a date.
 *
 * **Accepting a slot does not validate the quote.** It answers *when* the work
 * happens, never *whether* the agency has agreed to it — so the quote stays in
 * the validation queue and a manager still has to validate it.
 *
 * The assistant is named in the offer and is deliberately not stored. A quote
 * records what is sold and when; who does it is the planner's to decide on its
 * next run, and a preference kept here would be a promise nothing keeps.
 *
 * Slots are grouped under the visit they answer. A quote with two unplaced
 * visits has two sets of free times, and one flat list would leave an operator
 * guessing which slot belongs to which problem — and a click no way to know
 * which line to move.
 */
export function QuotePlanningFeedback({
  feedback,
  quoteId,
}: QuotePlanningFeedbackProps) {
  const { t, i18n } = useTranslation();
  const reschedule = useRescheduleQuoteLine(quoteId ?? '');
  const [failure, setFailure] = useState<string | null>(null);
  // Which slot is in flight, so only the clicked chip shows it is working.
  const [pending, setPending] = useState<string | null>(null);
  if (!feedback) return null;

  /** Identify one slot, for the test id and the in-flight marker. */
  const slotKey = (slot: SuggestedSlot): string =>
    `${slot.day}-${slot.start_minute}-${slot.hca_id}`;

  const accept = (visit: UnplacedVisit, slot: SuggestedSlot) => {
    if (!quoteId || !visit.quote_line_id) return;
    setFailure(null);
    setPending(slotKey(slot));
    reschedule.mutate(
      {
        quote_line_id: visit.quote_line_id,
        day: slot.day,
        start_minute: slot.start_minute,
        end_minute: slot.end_minute,
      },
      {
        onError: (cause) => {
          setPending(null);
          setFailure(cause instanceof Error ? cause.message : t('common.error'));
        },
        onSuccess: () => setPending(null),
      },
    );
  };

  const offers = (visit: UnplacedVisit) => {
    const slots = visit.alternatives;
    const actionable = Boolean(quoteId && visit.quote_line_id);
    if (slots.length === 0) {
      return (
        <Typography
          variant="body2"
          color="text.secondary"
          data-testid={`no-alternative-slot-${visit.requirement_id}`}
        >
          {t('quote.planningNoAlternative')}
        </Typography>
      );
    }
    return (
      <Stack direction="row" spacing={1} sx={{ mt: 0.5, flexWrap: 'wrap', gap: 1 }}>
        {slots.map((slot) => (
          <Chip
            key={slotKey(slot)}
            size="small"
            variant="outlined"
            color={actionable ? 'primary' : 'default'}
            clickable={actionable}
            disabled={actionable && pending !== null}
            onClick={actionable ? () => accept(visit, slot) : undefined}
            data-testid={`slot-${slot.day}-${slot.start_minute}`}
            label={t('quote.planningSlot', {
              day: new Date(slot.day).toLocaleDateString(i18n.language, {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
              }),
              time: minutesToTime(slot.start_minute),
              assistant: slot.hca_name,
            })}
          />
        ))}
      </Stack>
    );
  };

  return (
    <Alert severity="warning" data-testid="quote-planning-feedback">
      <AlertTitle>{t('quote.planningReturnedTitle')}</AlertTitle>
      <Typography variant="body2" sx={{ mb: 1 }}>
        {t('quote.planningReturnedLead')}
      </Typography>

      {failure ? (
        <Typography variant="body2" color="error" data-testid="reschedule-error">
          {failure}
        </Typography>
      ) : null}

      <Stack spacing={1.5} sx={{ mt: 1 }}>
        {feedback.visits.map((visit) => (
          <Box key={visit.requirement_id}>
            <Typography variant="body2">
              {t('planning.runPartialVisit', {
                service: visit.name,
                day: visit.day,
                reason: t(`planning.reason.${visit.reason}`),
              })}
            </Typography>
            <Typography
              variant="body2"
              sx={{ mt: 0.5, fontWeight: 600 }}
              data-testid={`alternatives-for-${visit.requirement_id}`}
            >
              {quoteId && visit.quote_line_id
                ? t('quote.planningAlternativesActionable')
                : t('quote.planningAlternatives')}
            </Typography>
            {offers(visit)}
          </Box>
        ))}
      </Stack>
    </Alert>
  );
}
