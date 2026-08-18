import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useSetWorkingDays } from '@/api/queries';
import { WEEKDAYS, type Hca, type Weekday } from '@/api/types';

interface WorkingDaysDialogProps {
  hca: Hca | null;
  onClose: () => void;
}

/**
 * Set which days of the week an assistant works, from the workforce screen.
 *
 * @param props - The assistant and the close handler.
 * @returns The rendered dialog.
 *
 * @remarks
 * **The manager's half of a control the assistant already had.** The endpoint
 * takes any signed-in account and performs a row-level ownership check, so an
 * assistant sets their own week on `/me` and a manager sets anybody's — but
 * until now only the first had a screen. The workforce grid printed the week as
 * read-only chips, which is exactly the shape that reads as "this is fixed".
 *
 * **All seven days are offered, weekends included.** Nothing has ever refused
 * Saturday or Sunday: `Weekday` carries all seven and the request model accepts
 * any of them. What made weekends look unavailable is that
 * `Hca.DEFAULT_WORKING_WEEKDAYS` is Monday-to-Friday, so every seeded record
 * shows the two of them greyed — a default that reads as a rule.
 *
 * The rules are the assistant's own screen's, deliberately: the whole week is
 * submitted rather than the day that was clicked, so two tabs cannot race into
 * a week nobody chose. And a week with no day is refused here rather than sent
 * and rejected, because clearing every chip is a statement whose two readings
 * are opposites.
 */
export function WorkingDaysDialog({ hca, onClose }: WorkingDaysDialogProps) {
  const { t } = useTranslation();
  const save = useSetWorkingDays(hca?.id ?? null);
  const [selected, setSelected] = useState<Weekday[]>([]);

  useEffect(() => {
    setSelected(hca?.working_weekdays ?? []);
  }, [hca]);

  const toggle = (day: Weekday) => {
    setSelected((current) =>
      current.includes(day)
        ? current.filter((entry) => entry !== day)
        : [...current, day],
    );
  };

  const ordered = WEEKDAYS.filter((day) => selected.includes(day));
  const stored = hca?.working_weekdays ?? [];
  const unchanged =
    ordered.length === stored.length &&
    ordered.every((day, index) => stored[index] === day);

  return (
    <Dialog
      open={hca !== null}
      onClose={onClose}
      maxWidth="xs"
      fullWidth
      data-testid="working-days-dialog"
    >
      <DialogTitle>
        {t('hcas.editWorkingDays')}
        {hca ? ` · ${hca.first_name} ${hca.last_name}` : ''}
      </DialogTitle>

      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            {t('hcas.workingDaysManagerHint')}
          </Typography>

          <Box
            sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}
            data-testid="rota-day-list"
          >
            {WEEKDAYS.map((day) => {
              const active = selected.includes(day);
              return (
                <Chip
                  key={day}
                  label={t(`common.weekday_${day}`)}
                  color={active ? 'primary' : 'default'}
                  variant={active ? 'filled' : 'outlined'}
                  onClick={() => toggle(day)}
                  data-testid={`rota-day-${day}`}
                  data-selected={active ? 'true' : 'false'}
                />
              );
            })}
          </Box>

          {ordered.length === 0 ? (
            <Alert severity="warning" data-testid="rota-empty">
              {t('hca.workingDaysEmpty')}
            </Alert>
          ) : null}

          {save.isError ? (
            <Alert severity="error" data-testid="rota-error">
              {t('common.saveFailed')}
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose} data-testid="cancel-rota">
          {t('common.cancel')}
        </Button>
        <Button
          variant="contained"
          onClick={() => save.mutate(ordered, { onSuccess: onClose })}
          disabled={ordered.length === 0 || unchanged || save.isPending}
          data-testid="save-rota"
        >
          {t('common.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
