import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import FullCalendar from '@fullcalendar/react';
import timeGridPlugin from '@fullcalendar/timegrid';
import dayGridPlugin from '@fullcalendar/daygrid';
import interactionPlugin from '@fullcalendar/interaction';
import frLocale from '@fullcalendar/core/locales/fr';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Chip from '@mui/material/Chip';
import Drawer from '@mui/material/Drawer';
import Divider from '@mui/material/Divider';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { addDays, startOfWeek } from 'date-fns';
import { usePlanning } from '@/api/queries';
import { INTERVENTION_STATUS_COLOUR } from '@/theme/palette';
import { formatTime, toIsoDate } from '@/utils/format';
import { useSession } from '@/store/session';
import type { Intervention } from '@/api/types';

/**
 * An assistant's own diary, as a week calendar.
 *
 * @returns The rendered page.
 *
 * @remarks
 * A calendar rather than a table, because the question an assistant asks is
 * "where am I at three o'clock on Thursday?" — which a list of rows sorted by
 * date answers only after they have counted. The day starts at 07:00 and ends
 * at 21:00 to match the configured working day, so an empty morning is visibly
 * empty rather than scrolled off the top.
 */
export function MyPlanningPage() {
  const { t, i18n } = useTranslation();
  const user = useSession((state) => state.user);
  const [anchorDate] = useState(() => startOfWeek(new Date(), { weekStartsOn: 1 }));
  const [selected, setSelected] = useState<Intervention | null>(null);

  const from = toIsoDate(anchorDate);
  const to = toIsoDate(addDays(anchorDate, 41));
  const { data: planning } = usePlanning(user?.hca_id ?? null, from, to);

  const events = useMemo(
    () =>
      (planning?.interventions ?? []).map((intervention) => ({
        id: intervention.id ?? '',
        title: intervention.name,
        start: `${intervention.day}T${intervention.start_time}`,
        end: `${intervention.day}T${intervention.end_time}`,
        backgroundColor: INTERVENTION_STATUS_COLOUR[intervention.status],
        borderColor: INTERVENTION_STATUS_COLOUR[intervention.status],
        extendedProps: { intervention },
      })),
    [planning],
  );

  return (
    <Stack spacing={2}>
      <Typography variant="h1">{t('nav.myPlanning')}</Typography>

      <Card sx={{ p: 2 }} data-testid="planning-calendar">
        <FullCalendar
          plugins={[timeGridPlugin, dayGridPlugin, interactionPlugin]}
          initialView="timeGridWeek"
          locale={i18n.language.startsWith('fr') ? frLocale : undefined}
          headerToolbar={{
            left: 'prev,next today',
            center: 'title',
            right: 'timeGridDay,timeGridWeek,dayGridMonth',
          }}
          slotMinTime="07:00:00"
          slotMaxTime="21:00:00"
          firstDay={1}
          weekends={false}
          allDaySlot={false}
          height="auto"
          nowIndicator
          events={events}
          eventClick={(info) => {
            setSelected(info.event.extendedProps.intervention as Intervention);
          }}
        />
      </Card>

      <Drawer
        anchor="right"
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        slotProps={{ paper: { sx: { width: 380, p: 3 } } }}
      >
        {selected ? (
          <Stack spacing={2} data-testid="intervention-detail">
            <Typography variant="h2">{selected.name}</Typography>
            <Chip
              label={t(`planning.status_${selected.status}`)}
              sx={{
                alignSelf: 'flex-start',
                bgcolor: INTERVENTION_STATUS_COLOUR[selected.status],
                color: '#fff',
              }}
            />
            <Divider />
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('planning.day')}
              </Typography>
              <Typography>
                {selected.day} · {formatTime(selected.start_time)} –{' '}
                {formatTime(selected.end_time)}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('hca.address')}
              </Typography>
              <Typography>
                {selected.address.street}
                <br />
                {selected.address.postal_code} {selected.address.city}
              </Typography>
            </Box>
          </Stack>
        ) : null}
      </Drawer>
    </Stack>
  );
}
