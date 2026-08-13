import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CircularProgress from '@mui/material/CircularProgress';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { usePlanningSettings, useUpdatePlanningSettings } from '@/api/queries';
import { minutesToTime, timeToMinutes } from '@/utils/format';

interface FormState {
  radiusKm: string;
  dayStart: string;
  dayEnd: string;
  lunchMinutes: string;
  lunchStart: string;
  lunchEnd: string;
}

/** The floor the server enforces on the midday break, in minutes. */
const MIN_LUNCH_BREAK_MINUTES = 60;

/**
 * The planning rules a manager or administrator owns.
 *
 * @returns The rendered page.
 *
 * @remarks
 * **These used to live in `app.yaml`.** Moving the day to 08:00 meant a
 * deployment, which is not what "configurable by a manager" means. They are now
 * one stored row, and this is the screen that writes it.
 *
 * The four times are held as minutes from midnight by the API, because that is
 * the unit the constraint solver works in. The conversion to and from `HH:MM`
 * happens here so a manager types a clock time rather than `1170`.
 *
 * **Nothing is re-planned when this is saved.** The rules apply to the next
 * planning run. Silently recomputing this week because somebody widened a
 * radius would move assistants who have already been told where to go, so the
 * page says so rather than leaving a manager to discover it.
 *
 * The coherence rules — a day that ends after it starts, a lunch window inside
 * that day and wide enough to hold the break — are checked here *and* by the
 * server. This copy is for the message: caught here it names the conflicting
 * pair before the request, and caught by the server it is a 422 that says the
 * same thing. Neither is a replacement for the other, and the server's is the
 * one that actually guards the database.
 */
export function PlanningSettingsPage() {
  const { t } = useTranslation();
  const { data: settings, isLoading } = usePlanningSettings();
  const save = useUpdatePlanningSettings();
  const [form, setForm] = useState<FormState | null>(null);

  useEffect(() => {
    if (!settings) return;
    setForm({
      radiusKm: String(settings.max_intervention_radius_km),
      dayStart: minutesToTime(settings.day_start_minute),
      dayEnd: minutesToTime(settings.day_end_minute),
      lunchMinutes: String(settings.lunch_break_minutes),
      lunchStart: minutesToTime(settings.lunch_window_start_minute),
      lunchEnd: minutesToTime(settings.lunch_window_end_minute),
    });
  }, [settings]);

  if (isLoading || !form) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}>
        <CircularProgress data-testid="planning-settings-loading" />
      </Box>
    );
  }

  const set = (field: keyof FormState) => (value: string) =>
    setForm((current) => (current ? { ...current, [field]: value } : current));

  const radius = Number(form.radiusKm);
  const dayStart = timeToMinutes(form.dayStart);
  const dayEnd = timeToMinutes(form.dayEnd);
  const lunchMinutes = Number(form.lunchMinutes);
  const lunchStart = timeToMinutes(form.lunchStart);
  const lunchEnd = timeToMinutes(form.lunchEnd);

  const parsed =
    dayStart !== null && dayEnd !== null && lunchStart !== null && lunchEnd !== null;

  let problem: string | null = null;
  if (!parsed || Number.isNaN(radius) || Number.isNaN(lunchMinutes)) {
    problem = 'planning.settingsIncomplete';
  } else if (radius <= 0) {
    problem = 'planning.settingsRadiusInvalid';
  } else if (lunchMinutes < MIN_LUNCH_BREAK_MINUTES) {
    problem = 'planning.settingsLunchTooShort';
  } else if (dayEnd <= dayStart) {
    problem = 'planning.settingsDayInverted';
  } else if (lunchEnd <= lunchStart) {
    problem = 'planning.settingsLunchInverted';
  } else if (lunchStart < dayStart || lunchEnd > dayEnd) {
    problem = 'planning.settingsLunchOutsideDay';
  } else if (lunchEnd - lunchStart < lunchMinutes) {
    problem = 'planning.settingsLunchWindowTooNarrow';
  }

  const submit = () => {
    if (problem || !parsed) return;
    save.mutate({
      max_intervention_radius_km: radius,
      day_start_minute: dayStart,
      day_end_minute: dayEnd,
      lunch_break_minutes: lunchMinutes,
      lunch_window_start_minute: lunchStart,
      lunch_window_end_minute: lunchEnd,
    });
  };

  return (
    <Stack spacing={3} data-testid="planning-settings-page">
      <Box>
        <Typography variant="h1">{t('planning.settingsTitle')}</Typography>
        <Typography variant="body2" color="text.secondary">
          {t('planning.settingsSubtitle')}
        </Typography>
      </Box>

      <Alert severity="info" data-testid="planning-settings-notice">
        {t('planning.settingsAppliesNextRun')}
      </Alert>

      <Card>
        <CardContent>
          <Stack spacing={3}>
            <Box>
              <Typography variant="h3">{t('planning.workingDayTitle')}</Typography>
              <Typography variant="body2" color="text.secondary">
                {t('planning.workingDayHint')}
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <TextField
                type="time"
                label={t('planning.dayStart')}
                value={form.dayStart}
                onChange={(event) => set('dayStart')(event.target.value)}
                InputLabelProps={{ shrink: true }}
                sx={{ maxWidth: 180 }}
                inputProps={{ 'data-testid': 'day-start' }}
              />
              <TextField
                type="time"
                label={t('planning.dayEnd')}
                value={form.dayEnd}
                onChange={(event) => set('dayEnd')(event.target.value)}
                InputLabelProps={{ shrink: true }}
                sx={{ maxWidth: 180 }}
                inputProps={{ 'data-testid': 'day-end' }}
              />
            </Box>

            <Box>
              <Typography variant="h3">{t('planning.lunchTitle')}</Typography>
              <Typography variant="body2" color="text.secondary">
                {t('planning.lunchHint')}
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <TextField
                type="number"
                label={t('planning.lunchMinutes')}
                value={form.lunchMinutes}
                onChange={(event) => set('lunchMinutes')(event.target.value)}
                sx={{ maxWidth: 180 }}
                inputProps={{ 'data-testid': 'lunch-minutes', min: 60 }}
              />
              <TextField
                type="time"
                label={t('planning.lunchWindowStart')}
                value={form.lunchStart}
                onChange={(event) => set('lunchStart')(event.target.value)}
                InputLabelProps={{ shrink: true }}
                sx={{ maxWidth: 180 }}
                inputProps={{ 'data-testid': 'lunch-start' }}
              />
              <TextField
                type="time"
                label={t('planning.lunchWindowEnd')}
                value={form.lunchEnd}
                onChange={(event) => set('lunchEnd')(event.target.value)}
                InputLabelProps={{ shrink: true }}
                sx={{ maxWidth: 180 }}
                inputProps={{ 'data-testid': 'lunch-end' }}
              />
            </Box>

            <Box>
              <Typography variant="h3">{t('planning.radiusTitle')}</Typography>
              <Typography variant="body2" color="text.secondary">
                {t('planning.radiusHint')}
              </Typography>
            </Box>
            <TextField
              type="number"
              label={t('planning.radiusKm')}
              value={form.radiusKm}
              onChange={(event) => set('radiusKm')(event.target.value)}
              sx={{ maxWidth: 220 }}
              inputProps={{ 'data-testid': 'radius-km', min: 0.1, step: 0.5 }}
            />

            {problem ? (
              <Alert severity="warning" data-testid="planning-settings-problem">
                {t(problem)}
              </Alert>
            ) : null}

            {save.isError ? (
              <Alert severity="error" data-testid="planning-settings-error">
                {t('common.saveFailed')}
              </Alert>
            ) : null}

            {save.isSuccess ? (
              <Alert severity="success" data-testid="planning-settings-saved">
                {t('common.saved')}
              </Alert>
            ) : null}

            <Box>
              <Button
                variant="contained"
                onClick={submit}
                disabled={problem !== null || save.isPending}
                data-testid="planning-settings-save"
              >
                {t('common.save')}
              </Button>
            </Box>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
