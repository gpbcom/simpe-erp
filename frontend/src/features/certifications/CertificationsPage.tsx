import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { EntityFilterBar } from '@/components/filters/EntityFilterBar';
import type { FilterDetail } from '@/components/filters/EntityFilterBar';
import { useEntityFilter } from '@/components/filters/entityFilter';
import type { EntityFilterSpec } from '@/components/filters/entityFilter';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import AddIcon from '@mui/icons-material/Add';
import { useCertificationTypes } from '@/api/queries';
import { CertificationTypeDialog } from './CertificationTypeDialog';
import type { CertificationType } from '@/api/types';

/** Which of the certification filter's fields are text, flags and closed lists. */
const CERTIFICATION_FILTER_SPEC: EntityFilterSpec = {
  textFields: ['search', 'code', 'label'],
  flagFields: ['is_active'],
  enumFields: {},
};

/** What is folded away behind "more filters". */
const CERTIFICATION_DETAILS: FilterDetail[] = [
  { field: 'code', label: 'certification.filterCode', kind: 'text' },
  { field: 'label', label: 'certification.filterLabel', kind: 'text' },
  {
    field: 'is_active',
    label: 'certification.filterActive',
    kind: 'flag',
    options: [
      { value: 'true', label: 'certification.filterActiveYes' },
      { value: 'false', label: 'certification.filterActiveNo' },
    ],
  },
];

/**
 * The certification catalogue: which qualifications the agency recognises.
 *
 * @returns The rendered page.
 *
 * @remarks
 * **The code is the contract, not the label.** An assistant's stored
 * qualification and a service's requirement are matched on `code`, so the
 * column is shown first and locked once created — renaming one would leave a
 * workforce holding certifications for something that no longer exists, and
 * disqualify all of them on the next planning run.
 *
 * Retired entries are **listed rather than hidden**, greyed with a status chip.
 * A manager wondering why they cannot pick a qualification needs to see that it
 * exists and is retired; a screen that simply omits it answers "why is DEAVS
 * not in the list?" with silence.
 *
 * Deleting is offered but usually refused. The server counts the assistants
 * holding the code and the services requiring it, and answers 409 naming both
 * — no foreign key protects those references, so the check is the only thing
 * standing between a delete and a requirement that points at nothing.
 */
export function CertificationsPage() {
  const { t } = useTranslation();
  const certificationFilter = useEntityFilter(CERTIFICATION_FILTER_SPEC);
  const { data: entries, isLoading } = useCertificationTypes(
    true,
    certificationFilter.filter,
  );
  const [editing, setEditing] = useState<CertificationType | null>(null);
  const [creating, setCreating] = useState(false);

  const columns: GridColDef<CertificationType>[] = [
    { field: 'code', headerName: t('certifications.code'), width: 140 },
    { field: 'label', headerName: t('certifications.label'), flex: 1, minWidth: 240 },
    {
      field: 'description',
      headerName: t('certifications.description'),
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
      headerName: t('certifications.status'),
      width: 130,
      sortable: false,
      renderCell: (params) => (
        <Chip
          size="small"
          variant={params.row.is_active ? 'filled' : 'outlined'}
          color={params.row.is_active ? 'success' : 'default'}
          label={t(
            params.row.is_active ? 'certifications.active' : 'certifications.retired',
          )}
          data-testid={`certification-status-${params.row.code}`}
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
          data-testid={`edit-certification-${params.row.code}`}
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
          {t('certifications.title')}
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreating(true)}
          data-testid="new-certification"
        >
          {t('certifications.add')}
        </Button>
      </Box>

      <EntityFilterBar
        state={certificationFilter}
        testId="certification"
        searchLabel="certification.searchFilter"
        details={CERTIFICATION_DETAILS}
      />

      <Alert severity="info" data-testid="certifications-explained">
        {t('certifications.whatThisIs')}
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
          data-testid="certifications-grid"
        />
      </Box>

      <CertificationTypeDialog
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
