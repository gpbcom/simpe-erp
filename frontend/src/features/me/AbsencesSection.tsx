import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import DeleteIcon from '@mui/icons-material/Delete';
import { useAddAbsence, useRemoveAbsence } from '@/api/queries';
import { formatDate } from '@/utils/format';
import type { Hca } from '@/api/types';

/** Why somebody is unavailable. Mirrors `AvailabilityKind` on the server. */
const KINDS = ['holiday', 'day-off', 'sick-leave', 'training', 'unavailable'];

interface AbsencesSectionProps {
  /** The record whose absences these are. */
  profile: Hca;
}

/**
 * The periods the assistant cannot work.
 *
 * @param props - The record whose absences to show.
 * @returns The rendered section.
 *
 * @remarks
 * Editable by the assistant themselves — the availability API takes any signed-in
 * account and performs a row-level ownership check, so an assistant files their
 * own absences and a manager files anybody's.
 *
 * This is personal data with direct operational weight: an absence is what
 * removes somebody from the next planning run. Leaving it read-only here would
 * mean an assistant had to telephone somebody to say they were on holiday.
 */
export function AbsencesSection({ profile }: AbsencesSectionProps) {
  const { t, i18n } = useTranslation();
  const add = useAddAbsence(profile.id);
  const remove = useRemoveAbsence(profile.id);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [kind, setKind] = useState(KINDS[0] ?? 'holiday');

  const submit = () => {
    if (!start || !end || !profile.id) return;
    add.mutate(
      {
        hca_id: profile.id,
        start_date: start,
        end_date: end,
        kind,
        start_time: null,
        end_time: null,
        note: null,
      },
      {
        onSuccess: () => {
          setStart('');
          setEnd('');
        },
      },
    );
  };

  return (
    <Card data-testid="absences-section">
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h3">{t('hca.availability')}</Typography>

          <Stack spacing={1} data-testid="absence-list">
            {profile.availability.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {t('hca.noAbsence')}
              </Typography>
            ) : (
              profile.availability.map((slot) => (
                <Box
                  key={slot.id}
                  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
                >
                  <Chip label={t(`hca.absence_${slot.kind}`, slot.kind)} />
                  <Typography variant="body2" sx={{ flexGrow: 1 }}>
                    {formatDate(slot.start_date, i18n.language)} —{' '}
                    {formatDate(slot.end_date, i18n.language)}
                  </Typography>
                  <IconButton
                    size="small"
                    onClick={() => slot.id && remove.mutate(slot.id)}
                    data-testid={`remove-absence-${slot.id}`}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Box>
              ))
            )}
          </Stack>

          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <TextField
              type="date"
              label={t('planning.from')}
              value={start}
              onChange={(event) => setStart(event.target.value)}
              InputLabelProps={{ shrink: true }}
              sx={{ maxWidth: 180 }}
              inputProps={{ 'data-testid': 'absence-start' }}
            />
            <TextField
              type="date"
              label={t('planning.to')}
              value={end}
              onChange={(event) => setEnd(event.target.value)}
              InputLabelProps={{ shrink: true }}
              sx={{ maxWidth: 180 }}
              inputProps={{ 'data-testid': 'absence-end' }}
            />
            <TextField
              select
              label={t('hca.absenceKind')}
              value={kind}
              onChange={(event) => setKind(event.target.value)}
              sx={{ maxWidth: 200 }}
              inputProps={{ 'data-testid': 'absence-kind' }}
            >
              {KINDS.map((option) => (
                <MenuItem key={option} value={option}>
                  {t(`hca.absence_${option}`, option)}
                </MenuItem>
              ))}
            </TextField>
            <Button
              variant="outlined"
              onClick={submit}
              disabled={!start || !end || add.isPending}
              data-testid="add-absence"
            >
              {t('hca.declareAbsence')}
            </Button>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}
