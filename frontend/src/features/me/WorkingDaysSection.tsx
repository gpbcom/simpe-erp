import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useSetWorkingDays } from '@/api/queries';
import { WEEKDAYS, type Hca, type Weekday } from '@/api/types';

interface WorkingDaysSectionProps {
  /** The record whose working week this is. */
  profile: Hca;
}

/**
 * The days of the week the assistant works at all.
 *
 * @param props - The record whose working week to show.
 * @returns The rendered section.
 *
 * @remarks
 * **This is not the same thing as an absence, and the two are deliberately
 * separate screens.** A day off in the week is a standing arrangement — "I
 * never work Wednesdays" — while an absence is dated. Both stop the planner
 * scheduling somebody, but only one of them ends when they come back from
 * leave, and a manager reading "nobody could take this visit" needs to know
 * which they are looking at.
 *
 * Editable by the assistant themselves, like their absences: the API takes any
 * signed-in account and performs a row-level ownership check, so an assistant
 * sets their own week and a manager sets anybody's.
 *
 * The whole week is submitted, never the day that was clicked. Two tabs open on
 * this screen would otherwise race, and last-write-wins on a delta produces a
 * working week nobody chose.
 *
 * A week with no days is refused here rather than sent and rejected. The server
 * answers 422 for it — clearing every box is a statement whose two readings are
 * opposites — but a disabled button says so before the click rather than after.
 */
export function WorkingDaysSection({ profile }: WorkingDaysSectionProps) {
  const { t } = useTranslation();
  const save = useSetWorkingDays(profile.id);
  const [selected, setSelected] = useState<Weekday[]>(profile.working_weekdays);
  useEffect(() => {
    setSelected(profile.working_weekdays);
  }, [profile.working_weekdays]);

  const toggle = (day: Weekday) => {
    setSelected((current) =>
      current.includes(day)
        ? current.filter((entry) => entry !== day)
        : [...current, day],
    );
  };

  const ordered = WEEKDAYS.filter((day) => selected.includes(day));
  const unchanged =
    ordered.length === profile.working_weekdays.length &&
    ordered.every((day, index) => profile.working_weekdays[index] === day);

  return (
    <Card data-testid="working-days-section">
      <CardContent>
        <Stack spacing={2}>
          <Box>
            <Typography variant="h3">{t('hca.workingDays')}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t('hca.workingDaysHint')}
            </Typography>
          </Box>

          <Box
            sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}
            data-testid="working-day-list"
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
                  data-testid={`working-day-${day}`}
                  data-selected={active ? 'true' : 'false'}
                />
              );
            })}
          </Box>

          {ordered.length === 0 ? (
            <Alert severity="warning" data-testid="working-days-empty">
              {t('hca.workingDaysEmpty')}
            </Alert>
          ) : null}

          {save.isError ? (
            <Alert severity="error" data-testid="working-days-error">
              {t('common.saveFailed')}
            </Alert>
          ) : null}

          {save.isSuccess && unchanged ? (
            <Alert severity="success" data-testid="working-days-saved">
              {t('common.saved')}
            </Alert>
          ) : null}

          <Box>
            <Button
              variant="contained"
              onClick={() => save.mutate(ordered)}
              disabled={ordered.length === 0 || unchanged || save.isPending}
              data-testid="save-working-days"
            >
              {t('common.save')}
            </Button>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}
