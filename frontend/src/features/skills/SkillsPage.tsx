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
import { useSkillTypes } from '@/api/queries';
import { SkillTypeDialog } from './SkillTypeDialog';
import type { SkillType } from '@/api/types';

/**
 * The skill catalogue: which skills the agency recognises.
 *
 * @returns The rendered page.
 *
 * @remarks
 * **The catalogue is a manager's, even though the declarations are not.** An
 * assistant says what they can do from their own account screen; what the
 * agency is willing to recognise and plan against is decided here. A workforce
 * able to invent catalogue entries would produce a list nobody could require
 * anything from.
 *
 * **The code is the contract, not the label.** An assistant's declared skill
 * and a service's requirement are matched on `code`, so the column is shown
 * first and locked once created — renaming one would un-skill every holder on
 * the next planning run.
 *
 * Retired entries are **listed rather than hidden**, greyed with a status chip,
 * for the same reason as in the certification catalogue: a manager wondering
 * why they cannot pick a skill needs to see that it exists and is retired.
 */
export function SkillsPage() {
  const { t } = useTranslation();
  const { data: entries, isLoading } = useSkillTypes(true);
  const [editing, setEditing] = useState<SkillType | null>(null);
  const [creating, setCreating] = useState(false);

  const columns: GridColDef<SkillType>[] = [
    { field: 'code', headerName: t('skills.code'), width: 160 },
    { field: 'label', headerName: t('skills.label'), flex: 1, minWidth: 240 },
    {
      field: 'description',
      headerName: t('skills.description'),
      flex: 1,
      minWidth: 200,
      sortable: false,
      renderCell: (params) => (
        <Typography variant="body2" color="text.secondary">
          {params.row.description ?? '—'}
        </Typography>
      ),
    },
    {
      field: 'is_active',
      headerName: t('skills.status'),
      width: 130,
      sortable: false,
      renderCell: (params) => (
        <Chip
          size="small"
          variant={params.row.is_active ? 'filled' : 'outlined'}
          color={params.row.is_active ? 'success' : 'default'}
          label={t(params.row.is_active ? 'skills.active' : 'skills.retired')}
          data-testid={`skill-status-${params.row.code}`}
        />
      ),
    },
    {
      field: 'actions',
      headerName: '',
      width: 140,
      sortable: false,
      renderCell: (params) => (
        <Button
          size="small"
          onClick={() => setEditing(params.row)}
          data-testid={`edit-skill-${params.row.code}`}
        >
          {t('common.edit')}
        </Button>
      ),
    },
  ];

  return (
    <Stack spacing={3}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Typography variant="h1" sx={{ flexGrow: 1 }}>
          {t('skills.title')}
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreating(true)}
          data-testid="new-skill"
        >
          {t('skills.add')}
        </Button>
      </Box>

      <Alert severity="info" data-testid="skills-explained">
        {t('skills.whatThisIs')}
      </Alert>

      <Box sx={{ height: 560 }}>
        <DataGrid
          rows={entries ?? []}
          columns={columns}
          loading={isLoading}
          getRowId={(row) => row.id ?? row.code}
          disableRowSelectionOnClick
          initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
          pageSizeOptions={[25, 50, 100]}
          data-testid="skills-grid"
        />
      </Box>

      <SkillTypeDialog
        entry={editing}
        creating={creating}
        onClose={() => {
          setEditing(null);
          setCreating(false);
        }}
      />
    </Stack>
  );
}
