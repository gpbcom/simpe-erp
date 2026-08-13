import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import AddIcon from '@mui/icons-material/Add';
import { useAgencies, useTeams, useUsers } from '@/api/queries';
import { TeamDialog } from './TeamDialog';
import { TeamDocumentsDialog } from './TeamDocumentsDialog';
import { TeamMembersDialog } from './TeamMembersDialog';
import type { Team } from '@/api/types';

/**
 * The teams the caller may read, and what each of them is.
 *
 * @returns The rendered page.
 *
 * @remarks
 * **The narrowing is the server's.** An administrator sees the whole company, a
 * manager sees the teams they run, and an assistant sees the one they are on —
 * decided in the statement rather than by filtering this grid, because a page
 * narrowed after the read has already loaded rows the caller may not see.
 *
 * The site and the manager are resolved **here**, from two lists this screen
 * already holds for its own pickers. Joining them server-side would put two
 * more tables in a statement read on every navigation, for names the client can
 * already spell.
 *
 * A team is the unit the planner works in: its run rebuilds its own week and
 * nobody else's. That is why disbanding one is refused while it still holds
 * quotes — the work would stay accepted and be read by no run again.
 */
export function TeamsPage() {
  const { t } = useTranslation();
  const { data: teams, isLoading, isError } = useTeams();
  const { data: agencies } = useAgencies();
  const { data: accounts } = useUsers();
  const [editing, setEditing] = useState<Team | null>(null);
  const [creating, setCreating] = useState(false);
  const [members, setMembers] = useState<Team | null>(null);
  const [documents, setDocuments] = useState<Team | null>(null);

  const siteNames = useMemo(() => {
    const resolved = new Map<string, string>();
    for (const agency of agencies ?? []) {
      if (agency.id) resolved.set(agency.id, agency.name);
    }
    return resolved;
  }, [agencies]);

  const managerNames = useMemo(() => {
    const resolved = new Map<string, string>();
    for (const account of accounts ?? []) {
      if (account.id) resolved.set(account.id, account.full_name);
    }
    return resolved;
  }, [accounts]);

  const columns: GridColDef<Team>[] = [
    { field: 'name', headerName: t('teams.name'), flex: 1, minWidth: 180 },
    {
      field: 'agency_id',
      headerName: t('teams.agency'),
      flex: 1,
      minWidth: 160,
      sortable: false,
      renderCell: (params) => (
        <span data-testid={`team-agency-${params.row.id}`}>
          {siteNames.get(params.row.agency_id) ?? params.row.agency_id}
        </span>
      ),
    },
    {
      field: 'manager_user_id',
      headerName: t('teams.manager'),
      flex: 1,
      minWidth: 160,
      sortable: false,
      renderCell: (params) => (
        <span data-testid={`team-manager-${params.row.id}`}>
          {managerNames.get(params.row.manager_user_id) ?? params.row.manager_user_id}
        </span>
      ),
    },
    {
      field: 'member_count',
      headerName: t('teams.members'),
      width: 110,
      renderCell: (params) => (
        <span data-testid={`team-members-${params.row.id}`}>
          {params.row.member_count}
        </span>
      ),
    },
    {
      field: 'actions',
      headerName: '',
      width: 300,
      sortable: false,
      renderCell: (params) => (
        <Stack direction="row" spacing={1}>
          <Button
            size="small"
            onClick={() => setEditing(params.row)}
            data-testid={`edit-team-${params.row.id}`}
          >
            {t('common.edit')}
          </Button>
          <Button
            size="small"
            onClick={() => setMembers(params.row)}
            data-testid={`team-people-${params.row.id}`}
          >
            {t('teams.members')}
          </Button>
          <Button
            size="small"
            onClick={() => setDocuments(params.row)}
            data-testid={`team-documents-${params.row.id}`}
          >
            {t('teams.documents')}
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={3}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Typography variant="h1" sx={{ flexGrow: 1 }}>
          {t('teams.title')}
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreating(true)}
          data-testid="new-team"
        >
          {t('teams.create')}
        </Button>
      </Box>

      <Alert severity="info" data-testid="teams-explained">
        {t('teams.subtitle')}
      </Alert>

      {isError ? (
        <Alert severity="error" data-testid="teams-error">
          {t('teams.loadError')}
        </Alert>
      ) : null}

      {!isLoading && !isError && (teams ?? []).length === 0 ? (
        <Alert severity="warning" data-testid="teams-empty">
          {t('teams.empty')}
        </Alert>
      ) : null}

      <Box sx={{ height: 520 }}>
        <DataGrid
          rows={teams ?? []}
          columns={columns}
          loading={isLoading}
          getRowId={(row) => row.id ?? row.name}
          disableRowSelectionOnClick
          initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
          pageSizeOptions={[25, 50]}
          data-testid="teams-grid"
        />
      </Box>

      <TeamDialog
        team={editing}
        creating={creating}
        onClose={() => {
          setEditing(null);
          setCreating(false);
        }}
      />
      <TeamMembersDialog team={members} onClose={() => setMembers(null)} />
      <TeamDocumentsDialog team={documents} onClose={() => setDocuments(null)} />
    </Stack>
  );
}
