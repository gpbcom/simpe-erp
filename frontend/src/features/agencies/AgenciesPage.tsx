import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import AddIcon from '@mui/icons-material/Add';
import { useAgencies } from '@/api/queries';
import { AGENCY_TYPE_COLOUR } from '@/theme/palette';
import { AgencyDialog } from './AgencyDialog';
import { AgencyMembersDialog } from './AgencyMembersDialog';
import type { Agency } from '@/api/types';

/**
 * The sites the company operates from.
 *
 * @returns The rendered page.
 *
 * @remarks
 * **A company is not its head office.** Before this screen existed the two were
 * the same record, so an agency with a warehouse and a branch office had
 * nowhere to say so — and "the team nearest the customer" had no place to
 * measure a distance from.
 *
 * The head office is **shown rather than editable as such**. Exactly one site
 * holds it, and moving it would be two writes that must both succeed; a
 * half-applied move leaves a company with none. The server refuses both the
 * promotion and the demotion, so the type field simply will not take.
 *
 * The two counts are columns rather than something to click through for,
 * because they are what the delete refusal is built on: a site is removable
 * only once nothing works from it, and a manager staring at "cannot be deleted"
 * needs to see which of the two numbers is not yet zero.
 */
export function AgenciesPage() {
  const { t } = useTranslation();
  const { data: agencies, isLoading, isError } = useAgencies();
  const [editing, setEditing] = useState<Agency | null>(null);
  const [creating, setCreating] = useState(false);
  const [members, setMembers] = useState<Agency | null>(null);

  const columns: GridColDef<Agency>[] = [
    { field: 'name', headerName: t('agencies.name'), flex: 1, minWidth: 200 },
    {
      field: 'agency_type',
      headerName: t('agencies.type'),
      width: 150,
      sortable: false,
      renderCell: (params) => (
        <Chip
          size="small"
          color={AGENCY_TYPE_COLOUR[params.row.agency_type]}
          label={t(`agencyType.${params.row.agency_type}`)}
          data-testid={`agency-type-${params.row.id}`}
        />
      ),
    },
    {
      field: 'address',
      headerName: t('agencies.address'),
      flex: 1,
      minWidth: 240,
      sortable: false,
      renderCell: (params) => (
        <Typography variant="body2" color="text.secondary">
          {params.row.address
            ? `${params.row.address.street}, ${params.row.address.postal_code} ${params.row.address.city}`
            : '—'}
        </Typography>
      ),
    },
    {
      field: 'member_count',
      headerName: t('agencies.members'),
      width: 110,
      renderCell: (params) => (
        <span data-testid={`agency-members-${params.row.id}`}>
          {params.row.member_count}
        </span>
      ),
    },
    {
      field: 'team_count',
      headerName: t('agencies.teams'),
      width: 110,
      renderCell: (params) => (
        <span data-testid={`agency-teams-${params.row.id}`}>
          {params.row.team_count}
        </span>
      ),
    },
    {
      field: 'actions',
      headerName: '',
      width: 220,
      sortable: false,
      renderCell: (params) => (
        <Stack direction="row" spacing={1}>
          <Button
            size="small"
            onClick={() => setEditing(params.row)}
            data-testid={`edit-agency-${params.row.id}`}
          >
            {t('common.edit')}
          </Button>
          <Button
            size="small"
            onClick={() => setMembers(params.row)}
            data-testid={`agency-people-${params.row.id}`}
          >
            {t('agencies.members')}
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={3}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Typography variant="h1" sx={{ flexGrow: 1 }}>
          {t('agencies.title')}
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreating(true)}
          data-testid="new-agency"
        >
          {t('agencies.create')}
        </Button>
      </Box>

      <Alert severity="info" data-testid="agencies-explained">
        {t('agencies.subtitle')}
      </Alert>

      {isError ? (
        <Alert severity="error" data-testid="agencies-error">
          {t('agencies.loadError')}
        </Alert>
      ) : null}

      {!isLoading && !isError && (agencies ?? []).length === 0 ? (
        <Alert severity="warning" data-testid="agencies-empty">
          {t('agencies.empty')}
        </Alert>
      ) : null}

      <Box sx={{ height: 520 }}>
        <DataGrid
          rows={agencies ?? []}
          columns={columns}
          loading={isLoading}
          getRowId={(row) => row.id ?? row.name}
          disableRowSelectionOnClick
          initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
          pageSizeOptions={[25, 50]}
          data-testid="agencies-grid"
        />
      </Box>

      <AgencyDialog
        agency={editing}
        creating={creating}
        onClose={() => {
          setEditing(null);
          setCreating(false);
        }}
      />
      <AgencyMembersDialog agency={members} onClose={() => setMembers(null)} />
    </Stack>
  );
}
