import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import InputAdornment from '@mui/material/InputAdornment';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import SearchIcon from '@mui/icons-material/Search';
import { useCustomers } from '@/api/queries';
import { CustomerDetailDrawer } from './CustomerDetailDrawer';
import type { Customer } from '@/api/types';

/**
 * Everybody the agency cares for.
 *
 * @returns The rendered page.
 *
 * @remarks
 * This screen was in the navigation for a long time with **no route behind
 * it** — clicking "Bénéficiaires" fell through to the catch-all and silently
 * redirected home, which reads as the click not registering. It is built now
 * rather than hidden again, because a manager looking up a family is one of
 * the two or three things this application is opened for.
 *
 * A grid rather than the card layout the assistant's own portfolio uses. A
 * manager scans forty households looking for one; an assistant reads the eight
 * they visit. Cards are better for reading and worse for finding.
 */
export function CustomersPage() {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Customer | null>(null);
  const { data: customers, isLoading } = useCustomers(search || undefined);

  const columns: GridColDef<Customer>[] = [
    {
      field: 'last_name',
      headerName: t('customer.name'),
      flex: 1,
      minWidth: 200,
      renderCell: (params) => (
        <span data-testid={`customer-name-${params.row.id}`}>
          {params.row.first_name} {params.row.last_name}
        </span>
      ),
    },
    { field: 'phone_number', headerName: t('customer.phone'), width: 170 },
    { field: 'email', headerName: t('customer.email'), flex: 1, minWidth: 200 },
    {
      field: 'city',
      headerName: t('hca.city'),
      width: 160,
      sortable: false,
      valueGetter: (_value, row) => row.address.city,
    },
    {
      field: 'registration_status',
      headerName: t('customer.status'),
      width: 140,
      sortable: false,
      renderCell: (params) => (
        <Chip
          size="small"
          variant={params.row.registration_status === 'active' ? 'filled' : 'outlined'}
          color={params.row.registration_status === 'active' ? 'success' : 'default'}
          label={t(`customer.status_${params.row.registration_status}`)}
          data-testid={`customer-status-${params.row.id}`}
        />
      ),
    },
  ];

  return (
    <Stack spacing={3}>
      <Typography variant="h1">{t('nav.customers')}</Typography>

      <TextField
        placeholder={t('customer.search')}
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        sx={{ maxWidth: 420 }}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          },
          htmlInput: { 'data-testid': 'customer-search' },
        }}
      />

      {(customers ?? []).length === 0 && !isLoading ? (
        <Typography color="text.secondary" data-testid="no-customer">
          {t('customer.noMatch')}
        </Typography>
      ) : null}

      <Box sx={{ height: 620 }}>
        <DataGrid
          rows={customers ?? []}
          columns={columns}
          loading={isLoading}
          getRowId={(row) => row.id ?? row.email}
          // The whole row opens the file. A manager clicking a name expects the
          // person, not a cell.
          onRowClick={(params) => setSelected(params.row)}
          disableRowSelectionOnClick
          initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
          pageSizeOptions={[25, 50, 100]}
          sx={{ '& .MuiDataGrid-row': { cursor: 'pointer' } }}
          data-testid="customers-grid"
        />
      </Box>

      <CustomerDetailDrawer customer={selected} onClose={() => setSelected(null)} />
    </Stack>
  );
}
