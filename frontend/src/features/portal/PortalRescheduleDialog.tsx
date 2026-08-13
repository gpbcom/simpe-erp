import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useRescheduleVisit } from '@/api/queries';
import { minutesToTime, timeToMinutes } from '@/utils/format';
import type { Intervention } from '@/api/types';

interface PortalRescheduleDialogProps {
  visit: Intervention | null;
  onClose: () => void;
  onDone: () => void;
}

/**
 * Ask a household when a visit would suit them better.
 *
 * @param props - The visit, and the two handlers.
 * @returns The rendered dialog.
 *
 * @remarks
 * - **A window, not a time**, and the wording says so. The household gives the
 *   span they are available in and the solver picks the moment inside it,
 *   against the assistant's round and their travel. Asking for an exact time
 *   would be collecting a preference the planner cannot honour, and the visit
 *   would come back unplaced with nothing explaining why.
 * - The window is **pre-filled from the current visit**, widened by an hour
 *   either side, because most reschedules are "same sort of time, different
 *   day" and an empty pair of time boxes is a form nobody finishes.
 * - It reprices: a Sunday or a holiday costs more. So the change goes back to
 *   the agency, which the dialog states rather than leaving the household to
 *   discover on their next invoice.
 */
export function PortalRescheduleDialog({
  visit,
  onClose,
  onDone,
}: PortalRescheduleDialogProps) {
  const { t } = useTranslation();
  const move = useRescheduleVisit();
  const [day, setDay] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!visit) return;
    const from = timeToMinutes(visit.start_time) ?? 9 * 60;
    const until = timeToMinutes(visit.end_time) ?? 10 * 60;
    setDay(visit.day);
    setStart(minutesToTime(Math.max(0, from - 60)));
    setEnd(minutesToTime(Math.min(24 * 60, until + 60)));
    setError(null);
  }, [visit]);

  const confirm = () => {
    if (!visit?.id) return;
    const startMinute = timeToMinutes(start);
    const endMinute = timeToMinutes(end);
    if (startMinute === null || endMinute === null || endMinute <= startMinute) {
      setError(t('portal.windowInvalid'));
      return;
    }
    setError(null);
    move.mutate(
      {
        interventionId: visit.id,
        day,
        start_minute: startMinute,
        end_minute: endMinute,
      },
      {
        onSuccess: onDone,
        onError: (cause) =>
          setError(cause instanceof Error ? cause.message : t('common.error')),
      },
    );
  };

  return (
    <Dialog
      open={Boolean(visit)}
      onClose={onClose}
      fullWidth
      data-testid="portal-reschedule-dialog"
    >
      <DialogTitle>{t('portal.rescheduleTitle')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {t('portal.windowExplained')}
          </Typography>
          <Grid container spacing={2}>
            <Grid size={12}>
              <TextField
                fullWidth
                type="date"
                label={t('portal.newDay')}
                value={day}
                onChange={(event) => setDay(event.target.value)}
                slotProps={{
                  inputLabel: { shrink: true },
                  htmlInput: { 'data-testid': 'portal-new-day' },
                }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth
                type="time"
                label={t('portal.notBefore')}
                value={start}
                onChange={(event) => setStart(event.target.value)}
                slotProps={{
                  inputLabel: { shrink: true },
                  htmlInput: { 'data-testid': 'portal-not-before' },
                }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth
                type="time"
                label={t('portal.notAfter')}
                value={end}
                onChange={(event) => setEnd(event.target.value)}
                slotProps={{
                  inputLabel: { shrink: true },
                  htmlInput: { 'data-testid': 'portal-not-after' },
                }}
              />
            </Grid>
          </Grid>
          <Alert severity="info">{t('portal.rescheduleWarning')}</Alert>
          {error ? (
            <Alert severity="error" data-testid="portal-reschedule-error">
              {error}
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} data-testid="portal-reschedule-dismiss">
          {t('common.cancel')}
        </Button>
        <Button
          variant="contained"
          onClick={confirm}
          disabled={move.isPending}
          data-testid="portal-reschedule-confirm"
        >
          {t('portal.rescheduleConfirm')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
