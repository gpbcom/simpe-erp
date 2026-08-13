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
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { ApiError } from '@/api/client';
import {
  useAgencies,
  useAllPlannings,
  useChangeInterventionType,
  useCustomerPlannings,
  useCustomers,
  useDeleteIntervention,
  useInterventionTypes,
  usePlanningRuns,
  useStartPlanningRun,
  useTeams,
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
 * The scope value meaning "every team of the company".
 *
 * @remarks
 * The empty string, because it is the one scope that sends neither `team_id`
 * nor `agency_id` — the request *is* the absence of a scope. It is offered to
 * administrators only: a company-wide computation rewrites the calendar of
 * every assistant employed, and the server refuses it for anybody else.
 */
const COMPANY_SCOPE = '';

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
  const [audience, setAudience] = useState<Audience>(
    isManager ? 'assistants' : 'customers',
  );
  const readsCustomers = audience === 'customers';
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
  const { data: customers } = useCustomers(undefined, isManager && !readsCustomers);
  const startRun = useStartPlanningRun();
  const { data: teams } = useTeams();
  const { data: agencies } = useAgencies();
  const [scope, setScope] = useState('');
  const latest = usePlanningRuns(isManager, isManager).data?.[0];
  const running = latest?.status === 'pending' || latest?.status === 'running';
  const isLoading = readsCustomers ? loadingCustomers : loadingAssistants;

  /**
   * The sites the caller may compute a planning for, in the picker's order.
   *
   * @remarks
   * Derived from the teams they can already see rather than from the full site
   * list, so a manager is offered the branches they actually run a team at. An
   * administrator sees every team, so this comes out as every site anyway.
   */
  const scopeSites = useMemo(() => {
    const wanted = new Set((teams ?? []).map((team) => team.agency_id));
    return (agencies ?? []).filter((agency) => agency.id && wanted.has(agency.id));
  }, [teams, agencies]);

  const hasNoScope = !isAdmin && scopeSites.length === 0 && (teams ?? []).length === 0;
  /**
   * The scope actually in force, once the picker's default is applied.
   *
   * @remarks
   * A manager has no company-wide option, so the empty default would leave the
   * select on a value it does not offer. Their first site is used instead —
   * the widest thing they are allowed to ask for — and their first team when
   * they run teams at no site the list carries.
   */
  const widestOwned = scopeSites.length
    ? `agency:${scopeSites[0]?.id}`
    : (teams ?? []).length
      ? `team:${(teams ?? [])[0]?.id}`
      : COMPANY_SCOPE;
  const effectiveScope = scope || (isAdmin ? COMPANY_SCOPE : widestOwned);
  const requestedScope = effectiveScope.startsWith('team:')
    ? { teamId: effectiveScope.slice(5) }
    : effectiveScope.startsWith('agency:')
      ? { agencyId: effectiveScope.slice(7) }
      : {};

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

  useEffect(() => {
    if (selectedHcaId === EVERYBODY || roster.length === 0) return;
    if (roster.some((entry) => entry.hca_id === selectedHcaId)) return;
    setSelectedHcaId(EVERYBODY);
  }, [roster, selectedHcaId]);

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
        {}
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
        {isManager ? (
          <>
            {}
            <TextField
              select
              size="small"
              label={t('teams.picker')}
              value={effectiveScope}
              onChange={(event) => setScope(event.target.value)}
              slotProps={{ htmlInput: { 'data-testid': 'team-picker' } }}
              sx={{ minWidth: 200 }}
            >
              {isAdmin ? (
                <MenuItem value={COMPANY_SCOPE} data-testid="team-picker-all">
                  {t('teams.wholeCompany')}
                </MenuItem>
              ) : null}
              {scopeSites.map((agency) => (
                <MenuItem
                  key={agency.id}
                  value={`agency:${agency.id}`}
                  data-testid={`team-picker-agency-${agency.id}`}
                >
                  {t('teams.wholeSite', { name: agency.name })}
                </MenuItem>
              ))}
              {(teams ?? []).map((team) => (
                <MenuItem
                  key={team.id}
                  value={`team:${team.id}`}
                  data-testid={`team-picker-${team.id}`}
                >
                  {team.name}
                </MenuItem>
              ))}
              {hasNoScope ? (
                <MenuItem value={COMPANY_SCOPE} disabled>
                  {t('teams.noScope')}
                </MenuItem>
              ) : null}
            </TextField>
            <Button
              variant="contained"
              onClick={() => startRun.mutate({ from, to, ...requestedScope })}
              disabled={running || startRun.isPending || hasNoScope}
              data-testid="compute-planning"
            >
              {running ? t('planning.computing') : t('planning.compute')}
            </Button>
          </>
        ) : null}
      </Stack>

      {}
      {startRun.isError ? (
        <Alert severity="error" data-testid="compute-planning-error">
          {startRun.error instanceof ApiError
            ? startRun.error.message
            : t('common.error')}
        </Alert>
      ) : null}

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
              data-testid="planning-roster"
            >
              {}
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
                        {}
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
              {}
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

            {}
            {readsCustomers ? null : (
              <>
                <Divider />

                {}
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

      {}
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
