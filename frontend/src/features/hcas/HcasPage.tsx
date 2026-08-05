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
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import DeleteIcon from '@mui/icons-material/Delete';
import SearchIcon from '@mui/icons-material/Search';
import { useQueryClient } from '@tanstack/react-query';
import { request } from '@/api/client';
import { keys, useHcas } from '@/api/queries';
import { AppIcon } from '@/components/icons/AppIcon';
import { initialsOf } from '@/utils/format';
import type { Certification, Hca } from '@/api/types';

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
 */
export function HcasPage() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [search, setSearch] = useState('');
  const { data, isLoading } = useHcas(search || undefined);
  const [editing, setEditing] = useState<Hca | null>(null);
  const [draft, setDraft] = useState<Certification[]>([]);
  const [added, setAdded] = useState('');

  const openEditor = (hca: Hca) => {
    setEditing(hca);
    setDraft([...hca.certifications]);
    setAdded('');
  };

  const save = async () => {
    if (!editing?.id) return;
    await request(`/api/v1/hcas/${editing.id}/employment`, {
      method: 'PATCH',
      json: { contract_type: editing.contract_type, certifications: draft },
    });
    await client.invalidateQueries({ queryKey: keys.hcas(search || undefined) });
    setEditing(null);
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
    {
      field: 'actions',
      headerName: t('common.actions'),
      width: 200,
      sortable: false,
      renderCell: (params) => (
        <Button
          size="small"
          startIcon={<AppIcon name="certification" />}
          onClick={() => openEditor(params.row)}
          data-testid={`edit-certifications-${params.row.id}`}
        >
          {t('hca.editCertifications')}
        </Button>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Typography variant="h1">{t('nav.hcas')}</Typography>

      <TextField
        placeholder={t('common.search')}
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        sx={{ maxWidth: 420 }}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon fontSize="small" />
            </InputAdornment>
          ),
        }}
        inputProps={{ 'data-testid': 'hca-search' }}
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
                label={t('hca.certifications')}
                value={added}
                onChange={(event) => setAdded(event.target.value)}
                inputProps={{ 'data-testid': 'new-certification' }}
              />
              <Button
                onClick={() => {
                  if (!added.trim()) return;
                  setDraft([
                    ...draft,
                    {
                      name: added.trim(),
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
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditing(null)}>{t('common.cancel')}</Button>
          <Button variant="contained" onClick={save} data-testid="save-certifications">
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
