import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import FullCalendar from '@fullcalendar/react';
import timeGridPlugin from '@fullcalendar/timegrid';
import dayGridPlugin from '@fullcalendar/daygrid';
import interactionPlugin from '@fullcalendar/interaction';
import frLocale from '@fullcalendar/core/locales/fr';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { usePortalPlanning } from '@/api/queries';
import { INTERVENTION_STATUS_COLOUR } from '@/theme/palette';
import { formatTime } from '@/utils/format';
import { customerPlanningWindow } from '@/utils/planningWindow';
import { PortalRescheduleDialog } from './PortalRescheduleDialog';
import { PortalCancelDialog } from './PortalCancelDialog';
import type { Intervention } from '@/api/types';

/**
 * The household's own calendar, and the two things they may do to a visit.
 *
 * @returns The rendered page.
 *
 * @remarks
 * - **The same calendar an assistant reads**, deliberately: FullCalendar with
 *   the same plugins, the same hours and the same week start, so the agency and
 *   the household are looking at one thing described one way.
 * - **Weekends are shown here**, unlike the assistant's diary. That screen hides
 *   them because the solved work is weekday work and two empty columns waste
 *   width; a household asking "is anybody coming on Saturday?" is asking a
 *   question the empty column answers.
 * - Clicking a visit opens it, with **cancel** and **move**. Both send the quote
 *   back to the agency for approval and neither takes effect until a manager
 *   agrees — which the dialogs say, because a calendar that silently empties is
 *   indistinguishable from one that is broken.
 */
export function PortalPlanningPage() {
  const { t, i18n } = useTranslation();
  const [{ from, to }] = useState(customerPlanningWindow);
  const { data: planning, isLoading } = usePortalPlanning(from, to);
  const [selected, setSelected] = useState<Intervention | null>(null);
  const [cancelling, setCancelling] = useState<Intervention | null>(null);
  const [moving, setMoving] = useState<Intervention | null>(null);

  const events = useMemo(
    () =>
      (planning ?? []).map((visit) => ({
        id: visit.id ?? '',
        title: visit.name,
        start: `${visit.day}T${visit.start_time}`,
        end: `${visit.day}T${visit.end_time}`,
        backgroundColor: INTERVENTION_STATUS_COLOUR[visit.status],
        borderColor: INTERVENTION_STATUS_COLOUR[visit.status],
        extendedProps: { intervention: visit },
      })),
    [planning],
  );

  return (
    <Stack spacing={2}>
      <Typography variant="h1">{t('portal.myPlanning')}</Typography>

      {!isLoading && (planning ?? []).length === 0 ? (
        <Alert severity="info" data-testid="portal-no-visit">
          {t('portal.noVisit')}
        </Alert>
      ) : null}

      <Card sx={{ p: 2 }} data-testid="portal-calendar">
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
          <Stack spacing={2} data-testid="portal-visit-detail">
            <Typography variant="h2">{selected.name}</Typography>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('planning.when')}
              </Typography>
              <Typography data-testid="portal-visit-when">
                {selected.day} · {formatTime(selected.start_time)} –{' '}
                {formatTime(selected.end_time)}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('portal.assistant')}
              </Typography>
              <Typography data-testid="portal-visit-hca">
                {selected.hca_full_name}
              </Typography>
            </Box>

            <Divider />

            <Alert severity="info">{t('portal.changeNeedsApproval')}</Alert>

            <Button
              variant="outlined"
              onClick={() => setMoving(selected)}
              data-testid="portal-reschedule-visit"
            >
              {t('portal.reschedule')}
            </Button>
            <Button
              variant="outlined"
              color="error"
              onClick={() => setCancelling(selected)}
              data-testid="portal-cancel-visit"
            >
              {t('portal.cancel')}
            </Button>
          </Stack>
        ) : null}
      </Drawer>

      <PortalCancelDialog
        visit={cancelling}
        onClose={() => setCancelling(null)}
        onDone={() => {
          setCancelling(null);
          setSelected(null);
        }}
      />
      <PortalRescheduleDialog
        visit={moving}
        onClose={() => setMoving(null)}
        onDone={() => {
          setMoving(null);
          setSelected(null);
        }}
      />
    </Stack>
  );
}
