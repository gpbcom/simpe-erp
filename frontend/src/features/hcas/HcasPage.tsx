import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import Avatar from '@mui/material/Avatar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Alert from '@mui/material/Alert';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import DeleteIcon from '@mui/icons-material/Delete';
import {
  useCertificationTypes,
  useDeleteHca,
  useHcas,
  usePromoteUser,
  useUpdateEmployment,
  useUsers,
} from '@/api/queries';
import { useSession } from '@/store/session';
import { EntityFilterBar } from '@/components/filters/EntityFilterBar';
import type { FilterDetail, FilterTab } from '@/components/filters/EntityFilterBar';
import { useEntityFilter } from '@/components/filters/entityFilter';
import type { EntityFilterSpec } from '@/components/filters/entityFilter';
import { AppIcon } from '@/components/icons/AppIcon';
import { FieldEmployeeToggle } from './FieldEmployeeToggle';
import { initialsOf } from '@/utils/format';
import { WEEKDAYS } from '@/api/types';
import { WorkingDaysDialog } from './WorkingDaysDialog';
import type { Certification, Hca, User } from '@/api/types';

/** Which of the assistant filter's fields are text, flags and closed lists. */
const HCA_FILTER_SPEC: EntityFilterSpec = {
  textFields: ['search', 'city', 'postal_code', 'email', 'phone'],
  flagFields: ['field_employee', 'is_geocoded', 'has_photo'],
  enumFields: { contract_type: ['cdi', 'cdd', 'interim'] },
};

/** The contract tabs, in the order a payroll office thinks of them. */
const HCA_TABS: FilterTab[] = [
  { key: 'all', label: 'hca.filter_all' },
  { key: 'cdi', value: 'cdi', label: 'hca.filter_cdi' },
  { key: 'cdd', value: 'cdd', label: 'hca.filter_cdd' },
  { key: 'interim', value: 'interim', label: 'hca.filter_interim' },
];

/** What is folded away behind "more filters". */
const HCA_DETAILS: FilterDetail[] = [
  { field: 'city', label: 'hca.filterCity', kind: 'text' },
  { field: 'postal_code', label: 'hca.filterPostalCode', kind: 'text' },
  { field: 'email', label: 'hca.filterEmail', kind: 'text' },
  { field: 'phone', label: 'hca.filterPhone', kind: 'text' },
  {
    field: 'field_employee',
    label: 'hca.filterFieldEmployee',
    kind: 'flag',
    options: [
      { value: 'true', label: 'hca.filterFieldEmployeeYes' },
      { value: 'false', label: 'hca.filterFieldEmployeeNo' },
    ],
  },
  {
    field: 'is_geocoded',
    label: 'hca.filterGeocoded',
    kind: 'flag',
    options: [
      { value: 'true', label: 'hca.filterGeocodedYes' },
      { value: 'false', label: 'hca.filterGeocodedNo' },
    ],
  },
  {
    field: 'has_photo',
    label: 'hca.filterPhoto',
    kind: 'flag',
    options: [
      { value: 'true', label: 'hca.filterPhotoYes' },
      { value: 'false', label: 'hca.filterPhotoNo' },
    ],
  },
];

/**
 * The workforce, and the one thing a manager may change about them.
 *
 * @returns The rendered page.
 *
 * @remarks
 * Certifications are edited **here and only here**. An assistant's own account
 * page renders them as locked chips, because somebody who could grant
 * themselves a qualification could be routed to work they are not trained for.
 * This dialog is the other half of that rule.
 *
 * Promotion sits here too, on the same row as the person it concerns, rather
 * than on an accounts screen of its own. What a manager wants is "make Luc a
 * manager", and the workforce grid is where they are already looking at Luc —
 * an accounts list would ask them to find the same person twice, by email.
 */
export function HcasPage() {
  const { t } = useTranslation();
  // Promotion and the accounts list are both administrator-only. A manager
  // sees the workforce without the role column rather than a column that
  // says 'no account' about every one of them.
  const isAdmin = useSession((state) => state.user?.role === 'admin');
  const { data: accounts } = useUsers(isAdmin);
  const promote = usePromoteUser();
  const [promoting, setPromoting] = useState<Hca | null>(null);

  const accountOf = (hcaId: string | null): User | undefined =>
    // A record that has never been stored has no identifier and therefore
    // no account; matching on null would match every account without one.
    hcaId ? (accounts ?? []).find((entry) => entry.hca_id === hcaId) : undefined;

  const confirmPromotion = async () => {
    const account = promoting ? accountOf(promoting.id) : undefined;
    if (!account?.id) return;
    await promote.mutateAsync({ userId: account.id, role: 'manager' });
    setPromoting(null);
  };
  const hcaFilter = useEntityFilter(HCA_FILTER_SPEC);
  const { data, isLoading } = useHcas(undefined, hcaFilter.filter);
  const [editing, setEditing] = useState<Hca | null>(null);
  const [draft, setDraft] = useState<Certification[]>([]);
  const [added, setAdded] = useState('');
  const [onRounds, setOnRounds] = useState(true);
  const [removing, setRemoving] = useState<Hca | null>(null);
  const [removalError, setRemovalError] = useState<string | null>(null);
  const { data: catalogue } = useCertificationTypes();
  const remove = useDeleteHca();

  // Only what is not already held, so the picker cannot add a duplicate the
  // server would store twice and the planner would read once.
  const available = (catalogue ?? []).filter(
    (entry) => !draft.some((held) => held.code === entry.code),
  );

  const [editingDays, setEditingDays] = useState<Hca | null>(null);

  const openEditor = (hca: Hca) => {
    setEditing(hca);
    setDraft([...hca.certifications]);
    setAdded('');
    setOnRounds(hca.field_employee);
  };

  // Through the shared mutation rather than a hand-rolled request. It knows
  // to invalidate `['planning']` as well as the workforce, which this screen
  // did not: taking somebody off the rounds changes who the next run may
  // schedule, so the calendars stop agreeing with the grid until they are
  // refetched — and nothing on either screen would have said so.
  const updateEmployment = useUpdateEmployment(editing?.id ?? null);

  const save = () => {
    if (!editing?.id) return;
    updateEmployment.mutate(
      {
        contract_type: editing.contract_type,
        certifications: draft,
        field_employee: onRounds,
      },
      { onSuccess: () => setEditing(null) },
    );
  };

  const confirmRemoval = () => {
    if (!removing?.id) return;
    setRemovalError(null);
    remove.mutate(removing.id, {
      onSuccess: () => setRemoving(null),
      onError: (cause) =>
        setRemovalError(cause instanceof Error ? cause.message : t('common.error')),
    });
  };

  const columns: GridColDef<Hca>[] = [
    {
      field: 'photo_url',
      headerName: '',
      width: 60,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        <Avatar
          src={params.row.photo_url ?? undefined}
          sx={{ width: 32, height: 32, fontSize: 13 }}
        >
          {initialsOf(`${params.row.first_name} ${params.row.last_name}`)}
        </Avatar>
      ),
    },
    { field: 'last_name', headerName: t('hca.lastName'), width: 140 },
    { field: 'first_name', headerName: t('hca.firstName'), width: 140 },
    {
      field: 'contract_type',
      headerName: t('hca.contractType'),
      width: 120,
      renderCell: (params) => (
        <Chip label={t(`hca.contract_${params.row.contract_type}`)} />
      ),
    },
    {
      field: 'field_employee',
      headerName: t('hcas.fieldEmployee'),
      width: 150,
      sortable: false,
      // Changed in the cell rather than only inside the qualifications
      // dialog. Taking somebody off the rounds has nothing to do with their
      // diplomas, and burying it behind a button labelled "edit the
      // qualifications" made the one field a manager changes weekly the
      // hardest one on the screen to find. Everybody who reaches this page
      // already holds the role the route asks for.
      renderCell: (params) => <FieldEmployeeToggle hca={params.row} />,
    },
    {
      field: 'working_weekdays',
      headerName: t('hca.workingDays'),
      width: 190,
      sortable: false,
      // The initials of the days worked, in ISO order, so a manager can read a
      // rota down the column. Spelling them out would need a column nobody has
      // room for; a count would say "4 days" without saying which four, which
      // is the only part that decides who can take a Wednesday visit.
      // The cell is the control. A separate button would be a fourth one on a
      // row that already carries three, and the chips are what a manager is
      // looking at when they decide the rota is wrong.
      renderCell: (params) => (
        <Tooltip title={t('hcas.editWorkingDays')}>
          <Stack
            direction="row"
            spacing={0.5}
            sx={{ flexWrap: 'wrap', cursor: 'pointer' }}
            onClick={() => setEditingDays(params.row)}
            data-testid={`edit-working-days-${params.row.id}`}
          >
            {WEEKDAYS.map((day) => {
              const worked = params.row.working_weekdays.includes(day);
              return (
                <Chip
                  key={day}
                  size="small"
                  variant={worked ? 'filled' : 'outlined'}
                  color={worked ? 'primary' : 'default'}
                  label={t(`common.weekdayShort_${day}`)}
                  data-testid={`working-day-${params.row.id}-${day}`}
                  data-selected={worked ? 'true' : 'false'}
                />
              );
            })}
          </Stack>
        </Tooltip>
      ),
    },
    {
      field: 'city',
      headerName: 'Ville',
      width: 140,
      valueGetter: (_value, row) => row.address.city,
    },
    {
      field: 'certifications',
      headerName: t('hca.certifications'),
      flex: 1,
      minWidth: 220,
      sortable: false,
      renderCell: (params) => (
        <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
          {params.row.certifications.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              —
            </Typography>
          ) : (
            params.row.certifications.map((certification) => (
              <Chip key={certification.name} label={certification.name} />
            ))
          )}
        </Stack>
      ),
    },
    ...(isAdmin
      ? ([
          {
            field: 'role',
            headerName: t('hca.role'),
            width: 130,
            sortable: false,
            renderCell: (params) => {
              const account = accountOf(params.row.id);
              return account ? (
                <Chip
                  size="small"
                  label={t(`role.${account.role}`)}
                  color={account.role === 'hca' ? 'default' : 'primary'}
                  data-testid={`role-${params.row.id}`}
                />
              ) : (
                // An assistant with no account cannot sign in yet, and cannot be
                // promoted either — there is nothing to promote.
                <Typography variant="body2" color="text.secondary">
                  {t('hca.noAccount')}
                </Typography>
              );
            },
          },
        ] as GridColDef<Hca>[])
      : []),
    {
      field: 'actions',
      headerName: t('common.actions'),
      width: 400,
      sortable: false,
      // Outlined, not MUI's default text variant. Two text buttons side by side
      // in a dense grid read as a run-on sentence — "Modifier les
      // qualificationsPromouvoir manager" — and neither looks like something
      // that can be pressed. A border is what makes a button a button.
      renderCell: (params) => (
        <Stack direction="row" spacing={1} alignItems="center" sx={{ height: '100%' }}>
          <Button
            size="small"
            variant="outlined"
            startIcon={<AppIcon name="certification" />}
            onClick={() => openEditor(params.row)}
            data-testid={`edit-certifications-${params.row.id}`}
          >
            {t('hca.editCertifications')}
          </Button>
          {accountOf(params.row.id)?.role === 'hca' ? (
            <Button
              size="small"
              variant="outlined"
              onClick={() => setPromoting(params.row)}
              data-testid={`promote-${params.row.id}`}
            >
              {t('hca.promote')}
            </Button>
          ) : null}
          <IconButton
            size="small"
            color="error"
            onClick={() => {
              setRemovalError(null);
              setRemoving(params.row);
            }}
            aria-label={t('hcas.delete')}
            data-testid={`delete-hca-${params.row.id}`}
          >
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Typography variant="h1">{t('nav.hcas')}</Typography>

      <EntityFilterBar
        state={hcaFilter}
        testId="hca"
        searchLabel="hca.searchFilter"
        tabField="contract_type"
        tabs={HCA_TABS}
        details={HCA_DETAILS}
      />

      <Card>
        <DataGrid
          rows={data ?? []}
          columns={columns}
          getRowId={(row) => row.id ?? row.email}
          loading={isLoading}
          autoHeight
          disableRowSelectionOnClick
          initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
          pageSizeOptions={[25, 50, 100]}
          data-testid="hcas-grid"
        />
      </Card>

      <Dialog
        open={Boolean(promoting)}
        onClose={() => setPromoting(null)}
        data-testid="promote-dialog"
      >
        <DialogTitle>{t('hca.promoteTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            {t('hca.promoteExplain', {
              name: promoting ? `${promoting.first_name} ${promoting.last_name}` : '',
            })}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPromoting(null)} data-testid="promote-cancel">
            {t('common.cancel')}
          </Button>
          <Button
            variant="contained"
            onClick={confirmPromotion}
            disabled={promote.isPending}
            data-testid="promote-confirm"
          >
            {t('hca.promote')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={Boolean(removing)}
        onClose={() => setRemoving(null)}
        fullWidth
        data-testid="delete-hca-dialog"
      >
        <DialogTitle>
          {t('hcas.deleteTitle', {
            name: removing ? `${removing.first_name} ${removing.last_name}` : '',
          })}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {/* What it costs, before it is asked for. A confirmation that does
                not say what it destroys is a confirmation nobody reads. */}
            <Alert severity="warning">{t('hcas.deleteWarning')}</Alert>
            {removalError ? (
              <Alert severity="error" data-testid="delete-hca-error">
                {removalError}
              </Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRemoving(null)} data-testid="cancel-delete-hca">
            {t('common.cancel')}
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={confirmRemoval}
            disabled={remove.isPending}
            data-testid="confirm-delete-hca"
          >
            {t('common.delete')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(editing)} onClose={() => setEditing(null)} fullWidth>
        <DialogTitle>{t('hca.editCertifications')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }} data-testid="certification-editor">
            {draft.map((certification, index) => (
              <Box
                key={`${certification.name}-${index}`}
                sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
              >
                <Chip label={certification.name} sx={{ flexGrow: 1 }} />
                <IconButton
                  size="small"
                  onClick={() =>
                    setDraft(draft.filter((_entry, position) => position !== index))
                  }
                  data-testid={`remove-certification-${index}`}
                >
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Box>
            ))}
            <Box sx={{ display: 'flex', gap: 1 }}>
              <TextField
                select
                label={t('hca.certifications')}
                value={added}
                onChange={(event) => setAdded(event.target.value)}
                sx={{ flexGrow: 1 }}
                slotProps={{
                  select: { native: true },
                  inputLabel: { shrink: true },
                  htmlInput: { 'data-testid': 'new-certification' },
                }}
              >
                <option value="" />
                {available.map((entry) => (
                  <option key={entry.code} value={entry.code}>
                    {entry.label}
                  </option>
                ))}
              </TextField>
              <Button
                onClick={() => {
                  const chosen = available.find((entry) => entry.code === added);
                  if (!chosen) return;
                  setDraft([
                    ...draft,
                    {
                      name: chosen.label,
                      code: chosen.code,
                      issuer: null,
                      obtained_on: null,
                      expires_on: null,
                    },
                  ]);
                  setAdded('');
                }}
                data-testid="add-certification"
              >
                +
              </Button>
            </Box>

            <FormControlLabel
              control={
                <Switch
                  checked={onRounds}
                  onChange={(event) => setOnRounds(event.target.checked)}
                  data-testid="field-employee"
                />
              }
              label={t('hcas.fieldEmployee')}
            />
            <Typography variant="caption" color="text.secondary">
              {t('hcas.fieldEmployeeHint')}
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditing(null)} data-testid="cancel-certifications">
            {t('common.cancel')}
          </Button>
          <Button variant="contained" onClick={save} data-testid="save-certifications">
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
      <WorkingDaysDialog hca={editingDays} onClose={() => setEditingDays(null)} />
    </Stack>
  );
}
