import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import FullCalendar from '@fullcalendar/react';
import timeGridPlugin from '@fullcalendar/timegrid';
import dayGridPlugin from '@fullcalendar/daygrid';
import interactionPlugin from '@fullcalendar/interaction';
import frLocale from '@fullcalendar/core/locales/fr';
import GroupsIcon from '@mui/icons-material/Groups';
import Alert from '@mui/material/Alert';
import Avatar from '@mui/material/Avatar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import List from '@mui/material/List';
import ListItemAvatar from '@mui/material/ListItemAvatar';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { ApiError } from '@/api/client';
import {
  useAllPlannings,
  useChangeInterventionType,
  useCustomerPlannings,
  useCustomers,
  useDeleteIntervention,
  useInterventionTypes,
  usePlanningRuns,
  useStartPlanningRun,
} from '@/api/queries';
import { INTERVENTION_STATUS_COLOUR, PLANNING_HCA_COLOURS } from '@/theme/palette';
import { hasAtLeast, useSession } from '@/store/session';
import { formatTime, initialsOf } from '@/utils/format';
import { customerPlanningWindow, planningWindow } from '@/utils/planningWindow';
import { PlanningRunStatus } from './PlanningRunStatus';
import type { CustomerPlanning, HcaPlanning, Intervention } from '@/api/types';

/**
 * The rail entry that shows the whole workforce at once.
 *
 * @remarks
 * A sentinel rather than a separate piece of state: "which planning am I
 * looking at" is one question, and answering it with a string plus a boolean
 * makes the two disagree the first time somebody forgets to clear one.
 */
const EVERYBODY = 'all';

/**
 * Which side of a visit the calendar is grouped by.
 *
 * @remarks
 * An intervention names an assistant *and* a household, so the same visits
 * group two ways: `assistants` answers "is Thursday covered", `customers`
 * answers "what is happening at Madame Vincent's this week". Neither is a
 * filter over the other's answer, which is why this is a lens rather than a
 * search box.
 */
type Audience = 'assistants' | 'customers';

/**
 * Every assistant's planning, as a calendar.
 *
 * @returns The rendered page.
 *
 * @remarks
 * A calendar rather than a list of cards. The question a manager asks is "who
 * is where at three o'clock on Thursday?", and a list sorted by date answers it
 * only after they have counted rows. This is the same `FullCalendar` the
 * assistant's own planning uses, so the two screens read alike and a fix to one
 * is a fix to both.
 *
 * **Everybody, or one assistant, chosen on the left.** The screen opens on the
 * whole workforce — that is the view a manager comes here for, and an empty
 * grid beside a full rail reads as "nobody is planned" rather than as "pick
 * someone". Choosing a name narrows the grid to that assistant alone, which is
 * how a week gets read in detail once the overview has raised a question.
 *
 * The rail carries each assistant's visit count, so whose week is full is
 * legible before opening it, and their colour swatch, so the shared grid has a
 * legend.
 */
export function TeamPlanningPage() {
  const { t, i18n } = useTranslation();
  const client = useQueryClient();
  const isAdmin = useSession((state) => state.user?.role === 'admin');
  const isManager = useSession((state) => hasAtLeast(state.user?.role, 'manager'));

  // An assistant has no assistants lens to switch to, so they do not get a
  // switch: a control whose other side answers 403 is a control that lies.
  const [audience, setAudience] = useState<Audience>(
    isManager ? 'assistants' : 'customers',
  );
  const readsCustomers = audience === 'customers';

  // Both computed once and held: recomputing on every render would produce a
  // new query key the moment the clock crossed midnight mid-session, and the
  // whole screen would refetch under the manager.
  //
  // **Two windows, deliberately.** The households' span is the one their own
  // portal reads, so the agency and the family are looking at the same weeks;
  // the assistants' span is the scheduler's fortnight. Sharing one number would
  // make one of the two answer a question nobody asked.
  const [{ from, to }] = useState(planningWindow);
  const [customerRange] = useState(customerPlanningWindow);

  const { data: plannings, isLoading: loadingAssistants } = useAllPlannings(
    from,
    to,
    isManager && !readsCustomers,
  );
  const { data: households, isLoading: loadingCustomers } = useCustomerPlannings(
    customerRange.from,
    customerRange.to,
    readsCustomers,
  );
  // Only the assistants lens needs the book: the households lens carries each
  // name on the planning itself, which is why that envelope exists at all.
  const { data: customers } = useCustomers(undefined, isManager && !readsCustomers);
  const startRun = useStartPlanningRun();
  const latest = usePlanningRuns(isAdmin, isAdmin).data?.[0];
  const running = latest?.status === 'pending' || latest?.status === 'running';
  const isLoading = readsCustomers ? loadingCustomers : loadingAssistants;

  const [selectedHcaId, setSelectedHcaId] = useState<string>(EVERYBODY);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>(EVERYBODY);
  const [openVisit, setOpenVisit] = useState<Intervention | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const { data: types } = useInterventionTypes();
  const deleting = useDeleteIntervention();
  const retyping = useChangeInterventionType();

  const retype = async (typeId: string) => {
    if (!openVisit?.id || typeId === openVisit.intervention_type_id) return;
    setEditError(null);
    try {
      await retyping.mutateAsync({ id: openVisit.id, typeId });
      // Closed rather than left showing the visit it has just re-labelled. The
      // row it was rendered from is stale the moment the request lands, and a
      // drawer that keeps insisting on the old service is worse than none.
      setOpenVisit(null);
    } catch (cause) {
      setEditError(cause instanceof ApiError ? cause.message : t('common.error'));
    }
  };

  const remove = async () => {
    if (!openVisit?.id) return;
    setEditError(null);
    try {
      await deleting.mutateAsync({ id: openVisit.id, from, to });
      setConfirmingDelete(false);
      setOpenVisit(null);
    } catch (cause) {
      setConfirmingDelete(false);
      setEditError(cause instanceof ApiError ? cause.message : t('common.error'));
    }
  };

  // The visits are written by a worker, behind the screen's back, so nothing
  // invalidates them when a run finishes. Without this the manager is told
  // "75 visits planned" above an empty calendar and has to reload.
  const finished = latest?.status === 'succeeded' ? latest.finished_at : null;
  useEffect(() => {
    if (!finished) return;
    void client.invalidateQueries({ queryKey: ['planning', 'all'] });
  }, [client, finished]);

  const roster: HcaPlanning[] = useMemo(
    () =>
      [...(plannings ?? [])].sort((left, right) =>
        left.hca_full_name.localeCompare(right.hca_full_name),
      ),
    [plannings],
  );

  const book: CustomerPlanning[] = useMemo(
    () =>
      [...(households ?? [])].sort((left, right) =>
        left.customer_full_name.localeCompare(right.customer_full_name),
      ),
    [households],
  );

  // An assistant who was being read and has since left the roster — it is
  // rebuilt by every planning run — would leave the grid pointing at nobody.
  // Falling back to the overview says "here is the workforce" instead of
  // showing an empty week that reads as a failed solve.
  useEffect(() => {
    if (selectedHcaId === EVERYBODY || roster.length === 0) return;
    if (roster.some((entry) => entry.hca_id === selectedHcaId)) return;
    setSelectedHcaId(EVERYBODY);
  }, [roster, selectedHcaId]);

  // The same fallback on the other axis: a household whose arrangement ended
  // drops out of the book, and a grid pointing at nobody reads as an empty week
  // rather than as a household who is no longer served.
  useEffect(() => {
    if (selectedCustomerId === EVERYBODY || book.length === 0) return;
    if (book.some((entry) => entry.customer_id === selectedCustomerId)) return;
    setSelectedCustomerId(EVERYBODY);
  }, [book, selectedCustomerId]);

  const selectedId = readsCustomers ? selectedCustomerId : selectedHcaId;
  const showsEverybody = selectedId === EVERYBODY;
  const selected = roster.find((entry) => entry.hca_id === selectedHcaId) ?? null;
  const selectedHousehold =
    book.find((entry) => entry.customer_id === selectedCustomerId) ?? null;
  const shown = readsCustomers
    ? showsEverybody
      ? book
      : selectedHousehold
        ? [selectedHousehold]
        : []
    : showsEverybody
      ? roster
      : selected
        ? [selected]
        : [];
  const entries = readsCustomers ? book : roster;
  const totalVisits = entries.reduce(
    (count, entry) => count + entry.interventions.length,
    0,
  );

  // Position in the rail, not a hash of the identifier: a hash gives two
  // adjacent assistants the same hue often enough to be noticed, and the rail
  // is what the manager reads the legend off.
  const colourOf = (hcaId: string): string => {
    const index = roster.findIndex((entry) => entry.hca_id === hcaId);
    const colour =
      PLANNING_HCA_COLOURS[(index < 0 ? 0 : index) % PLANNING_HCA_COLOURS.length];
    return colour ?? PLANNING_HCA_COLOURS[0];
  };

  const householdColourOf = (customerId: string): string => {
    const index = book.findIndex((entry) => entry.customer_id === customerId);
    const colour =
      PLANNING_HCA_COLOURS[(index < 0 ? 0 : index) % PLANNING_HCA_COLOURS.length];
    return colour ?? PLANNING_HCA_COLOURS[0];
  };

  const customerName = (customerId: string): string => {
    const found = (customers ?? []).find((entry) => entry.id === customerId);
    return found ? `${found.first_name} ${found.last_name}` : customerId;
  };

  const events = useMemo(
    () =>
      shown.flatMap((entry) => {
        const household = readsCustomers
          ? (entry as CustomerPlanning).customer_full_name
          : null;
        return entry.interventions.map((visit) => {
          // Whoever is not already answered by the rail goes first in the
          // title: on the shared grid that is the assistant, on one person's
          // week it is the customer.
          //
          // **On the households lens, narrowed to one household, the colours
          // are the status colours the family sees in their own space.** That
          // is the whole point of this view; a per-household hue there would be
          // the agency reading a different picture from the customer. On the
          // whole-agency grid there is no portal counterpart — a household
          // never sees forty households — so the hue answers "whose visit is
          // that", exactly as it does for assistants.
          const colour = !showsEverybody
            ? INTERVENTION_STATUS_COLOUR[visit.status]
            : readsCustomers
              ? householdColourOf((entry as CustomerPlanning).customer_id)
              : colourOf((entry as HcaPlanning).hca_id);
          const title = readsCustomers
            ? showsEverybody
              ? `${household} · ${visit.name}`
              : `${visit.name} · ${visit.hca_full_name}`
            : showsEverybody
              ? `${visit.hca_full_name} · ${visit.name}`
              : `${visit.name} · ${customerName(visit.customer_id)}`;
          return {
            id: visit.id ?? '',
            title,
            start: `${visit.day}T${visit.start_time}`,
            end: `${visit.day}T${visit.end_time}`,
            backgroundColor: colour,
            borderColor: colour,
            extendedProps: { visit },
          };
        });
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      roster,
      book,
      selected,
      selectedHousehold,
      showsEverybody,
      readsCustomers,
      customers,
    ],
  );

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" spacing={2}>
        <Typography variant="h1" sx={{ flexGrow: 1 }}>
          {t('nav.plannings')}
        </Typography>
        {/* Rendered only for somebody who may read both. An assistant sees the
            households lens alone, and offering them a segment that answers 403
            would be a control that lies about what it does. */}
        {isManager ? (
          <ToggleButtonGroup
            size="small"
            exclusive
            value={audience}
            onChange={(_event, next: Audience | null) => next && setAudience(next)}
            data-testid="planning-audience"
          >
            <ToggleButton value="assistants" data-testid="planning-audience-assistants">
              {t('planning.byAssistant')}
            </ToggleButton>
            <ToggleButton value="customers" data-testid="planning-audience-customers">
              {t('planning.byCustomer')}
            </ToggleButton>
          </ToggleButtonGroup>
        ) : null}
        {isAdmin ? (
          <Button
            variant="contained"
            onClick={() => startRun.mutate({ from, to })}
            disabled={running || startRun.isPending}
            data-testid="compute-planning"
          >
            {running ? t('planning.computing') : t('planning.compute')}
          </Button>
        ) : null}
      </Stack>

      <PlanningRunStatus run={latest ?? null} />

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="stretch">
        <Card sx={{ width: { xs: '100%', md: 280 }, flexShrink: 0 }}>
          <Typography variant="h3" sx={{ p: 2, pb: 1 }}>
            {readsCustomers ? t('nav.customers') : t('nav.hcas')}
          </Typography>
          <Divider />
          {isLoading ? (
            <Typography sx={{ p: 2 }}>{t('common.loading')}</Typography>
          ) : entries.length === 0 ? (
            // A sentence rather than a blank rail: an empty roster and a failed
            // request look identical without one.
            <Box sx={{ p: 3, textAlign: 'center' }} data-testid="planning-roster-empty">
              <Typography variant="body2" color="text.secondary">
                {readsCustomers
                  ? t('planning.noHouseholdPlanned')
                  : t('planning.nobodyPlanned')}
              </Typography>
            </Box>
          ) : (
            <List
              dense
              // Named "roster" and not "hca-list": a container whose test id
              // begins with the same prefix as the entries it holds is counted
              // as one of them by any `^=` selector.
              data-testid="planning-roster"
            >
              {/* The whole workforce, first and always present: the overview is
                  what the screen is for, and burying it under twelve names
                  would make it the one entry a manager has to hunt for. */}
              <ListItemButton
                selected={showsEverybody}
                onClick={() =>
                  readsCustomers
                    ? setSelectedCustomerId(EVERYBODY)
                    : setSelectedHcaId(EVERYBODY)
                }
                data-testid="planning-all"
              >
                <ListItemAvatar>
                  <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main' }}>
                    <GroupsIcon fontSize="small" />
                  </Avatar>
                </ListItemAvatar>
                <ListItemText
                  primary={
                    readsCustomers
                      ? t('planning.everyHousehold')
                      : t('planning.everybody')
                  }
                  secondary={t('planning.visitCount', { count: totalVisits })}
                />
              </ListItemButton>
              <Divider component="li" />
              {readsCustomers
                ? book.map((entry) => (
                    <ListItemButton
                      key={entry.customer_id}
                      selected={entry.customer_id === selectedCustomerId}
                      onClick={() => setSelectedCustomerId(entry.customer_id)}
                      data-testid={`planning-customer-${entry.customer_id}`}
                    >
                      <ListItemAvatar>
                        <Avatar
                          sx={{
                            width: 32,
                            height: 32,
                            bgcolor: householdColourOf(entry.customer_id),
                            color: '#fff',
                            fontSize: 13,
                          }}
                        >
                          {initialsOf(entry.customer_full_name)}
                        </Avatar>
                      </ListItemAvatar>
                      <ListItemText
                        primary={entry.customer_full_name}
                        secondary={t('planning.visitCount', {
                          count: entry.interventions.length,
                        })}
                      />
                    </ListItemButton>
                  ))
                : roster.map((entry) => (
                    <ListItemButton
                      key={entry.hca_id}
                      selected={entry.hca_id === selectedHcaId}
                      onClick={() => setSelectedHcaId(entry.hca_id)}
                      data-testid={`planning-hca-${entry.hca_id}`}
                    >
                      <ListItemAvatar>
                        {/* Also the legend for the shared grid, which is why
                            the swatch is worn even when one assistant is being
                            read. */}
                        <Avatar
                          sx={{
                            width: 32,
                            height: 32,
                            bgcolor: colourOf(entry.hca_id),
                            color: '#fff',
                            fontSize: 13,
                          }}
                        >
                          {initialsOf(entry.hca_full_name)}
                        </Avatar>
                      </ListItemAvatar>
                      <ListItemText
                        primary={entry.hca_full_name}
                        secondary={t('planning.visitCount', {
                          count: entry.interventions.length,
                        })}
                      />
                    </ListItemButton>
                  ))}
            </List>
          )}
        </Card>

        <Card
          sx={{ p: 2, flexGrow: 1, minWidth: 0 }}
          data-testid="team-planning-calendar"
        >
          {entries.length > 0 ? (
            <FullCalendar
              // Keyed on the lens *and* the selection so switching rebuilds the
              // grid rather than animating one person's week into another's,
              // which reads as visits moving.
              key={`${audience}-${selectedId}`}
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
              // **Weekends are shown on the households lens**, because they are
              // shown in the household's own space and care does not stop on a
              // Sunday. The assistants lens hides them: a scheduler reads a
              // working week, and five columns are wider than seven.
              weekends={readsCustomers}
              allDaySlot={false}
              height="auto"
              nowIndicator
              events={events}
              eventClick={(info) => {
                setOpenVisit(info.event.extendedProps.visit as Intervention);
              }}
            />
          ) : (
            <Box sx={{ p: 6, textAlign: 'center' }} data-testid="team-planning-empty">
              <Typography color="text.secondary">
                {readsCustomers
                  ? t('planning.noHouseholdPlanned')
                  : t('planning.nobodyPlanned')}
              </Typography>
            </Box>
          )}
        </Card>
      </Stack>

      <Drawer
        anchor="right"
        open={Boolean(openVisit)}
        onClose={() => setOpenVisit(null)}
        slotProps={{ paper: { sx: { width: 380, p: 3 } } }}
      >
        {openVisit ? (
          <Stack spacing={2} data-testid="team-intervention-detail">
            <Typography variant="h2">{openVisit.name}</Typography>
            <Chip
              label={t(`planning.status_${openVisit.status}`)}
              sx={{
                alignSelf: 'flex-start',
                bgcolor: INTERVENTION_STATUS_COLOUR[openVisit.status],
                color: '#fff',
              }}
            />
            <Divider />
            <Box>
              {/* Named in full, and first. On the shared grid the block was
                  read by its colour, and a colour is not something a manager
                  can act on — "call Karim Haddad" needs the name. */}
              <Typography variant="caption" color="text.secondary">
                {t('planning.assistant')}
              </Typography>
              <Stack direction="row" alignItems="center" spacing={1}>
                <Avatar
                  sx={{
                    width: 28,
                    height: 28,
                    bgcolor: colourOf(openVisit.hca_id),
                    color: '#fff',
                    fontSize: 12,
                  }}
                >
                  {initialsOf(openVisit.hca_full_name)}
                </Avatar>
                <Typography data-testid="team-intervention-hca">
                  {openVisit.hca_full_name}
                </Typography>
              </Stack>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('quote.customer')}
              </Typography>
              <Typography>{customerName(openVisit.customer_id)}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('planning.day')}
              </Typography>
              <Typography>
                {openVisit.day} · {formatTime(openVisit.start_time)} –{' '}
                {formatTime(openVisit.end_time)}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('hca.address')}
              </Typography>
              <Typography>
                {openVisit.address.street}
                <br />
                {openVisit.address.postal_code} {openVisit.address.city}
              </Typography>
            </Box>

            {/* **Read-only on the households lens.** Changing what a visit is,
                or removing it, rewrites the household's quote and their bill —
                a decision that belongs to the assistants view, where the
                manager arrived to schedule rather than to answer a family's
                question. Rendering the controls and ignoring them would look
                entirely right until somebody pressed one. */}
            {readsCustomers ? null : (
              <>
                <Divider />

                {/* A native select, like the quote dialogs use. MUI's default
                renders a hidden input beside a div that neither a keyboard nor
                a test can operate as a dropdown. */}
                <TextField
                  select
                  size="small"
                  label={t('quote.service')}
                  value={openVisit.intervention_type_id}
                  onChange={(event) => retype(event.target.value)}
                  disabled={retyping.isPending}
                  helperText={t('planning.retypeReprices')}
                  slotProps={{ select: { native: true } }}
                  data-testid="intervention-type-select"
                >
                  {(types ?? []).map((entry) => (
                    <option key={entry.id ?? entry.code} value={entry.id ?? ''}>
                      {entry.name}
                    </option>
                  ))}
                </TextField>

                <Button
                  color="error"
                  variant="outlined"
                  onClick={() => setConfirmingDelete(true)}
                  disabled={deleting.isPending}
                  data-testid="delete-intervention"
                >
                  {t('planning.deleteVisit')}
                </Button>

                {editError ? (
                  <Alert severity="error" data-testid="intervention-edit-error">
                    {editError}
                  </Alert>
                ) : null}
              </>
            )}
          </Stack>
        ) : null}
      </Drawer>

      {/* Asked for, never assumed. Cancelling takes the visit off the quote as
          well as off the calendar, and a customer's bill is not something to
          change on a mis-click. */}
      <Dialog open={confirmingDelete} onClose={() => setConfirmingDelete(false)}>
        <DialogTitle>{t('planning.deleteVisitTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText data-testid="delete-intervention-explain">
            {t('planning.deleteVisitExplain', {
              name: openVisit?.name ?? '',
              day: openVisit?.day ?? '',
            })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmingDelete(false)}>
            {t('common.cancel')}
          </Button>
          <Button
            color="error"
            variant="contained"
            onClick={remove}
            disabled={deleting.isPending}
            data-testid="confirm-delete-intervention"
          >
            {t('planning.deleteVisit')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
