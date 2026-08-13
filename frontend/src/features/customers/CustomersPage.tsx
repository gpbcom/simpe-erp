import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Alert from '@mui/material/Alert';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import DeleteIcon from '@mui/icons-material/Delete';
import PersonAddIcon from '@mui/icons-material/PersonAdd';
import { useCustomerQuotes, useCustomers, useDeleteCustomer } from '@/api/queries';
import { CustomerDetailDrawer } from './CustomerDetailDrawer';
import { CustomerDialog } from './CustomerDialog';
import { CustomerFilterBar } from './CustomerFilterBar';
import { CustomerStatusChip } from './CustomerStatusChip';
import { useCustomerFilter } from './useCustomerFilter';
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
 *
 * **Registering somebody starts here**, beside the search that proves they are
 * not already on file. A manager taking a telephone enquiry looks the family up
 * first; putting the button anywhere else would mean leaving the one screen that
 * can answer "do we already know them?" in order to say that we do not.
 *
 * **The filters live in the URL**, not in this component's state, so a narrowed
 * book is a link somebody can send. They are applied by the server: the grid
 * holds one page, and a filter run in the browser would search the rows it
 * happens to have and quietly miss the rest.
 */
export function CustomersPage() {
  const { t } = useTranslation();
  const filter = useCustomerFilter();
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<Customer | null>(null);
  const { data: customers, isLoading } = useCustomers(filter.filter);
  const [removing, setRemoving] = useState<Customer | null>(null);
  const [removalError, setRemovalError] = useState<string | null>(null);
  const remove = useDeleteCustomer();
  const { data: doomedQuotes } = useCustomerQuotes(removing?.id ?? '');

  const confirmRemoval = () => {
    if (!removing?.id) return;
    setRemovalError(null);
    remove.mutate(removing.id, {
      onSuccess: () => setRemoving(null),
      onError: (cause) =>
        setRemovalError(cause instanceof Error ? cause.message : t('common.error')),
    });
  };

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
        <CustomerStatusChip
          status={params.row.registration_status}
          testId={`customer-status-${params.row.id}`}
        />
      ),
    },
    {
      field: 'actions',
      headerName: '',
      width: 70,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        <IconButton
          size="small"
          color="error"
          onClick={(event) => {
            event.stopPropagation();
            setRemovalError(null);
            setRemoving(params.row);
          }}
          aria-label={t('customers.delete')}
          data-testid={`delete-customer-${params.row.id}`}
        >
          <DeleteIcon fontSize="small" />
        </IconButton>
      ),
    },
  ];

  return (
    <Stack spacing={3}>
      <Typography variant="h1">{t('nav.customers')}</Typography>

      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={2}
        alignItems={{ md: 'flex-start' }}
      >
        <Box sx={{ flexGrow: 1 }}>
          <CustomerFilterBar filter={filter} />
        </Box>
        <Button
          variant="contained"
          startIcon={<PersonAddIcon />}
          onClick={() => setCreating(true)}
          data-testid="add-customer"
        >
          {t('customer.add')}
        </Button>
      </Stack>

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
          onRowClick={(params) => setSelected(params.row)}
          disableRowSelectionOnClick
          initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
          pageSizeOptions={[25, 50, 100]}
          sx={{ '& .MuiDataGrid-row': { cursor: 'pointer' } }}
          data-testid="customers-grid"
        />
      </Box>

      <Dialog
        open={Boolean(removing)}
        onClose={() => setRemoving(null)}
        fullWidth
        data-testid="delete-customer-dialog"
      >
        <DialogTitle>
          {t('customers.deleteTitle', {
            name: removing ? `${removing.first_name} ${removing.last_name}` : '',
          })}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="warning">{t('customers.deleteWarning')}</Alert>
            <Typography variant="body2" data-testid="delete-customer-counts">
              {t('customers.deleteCounts', { quotes: (doomedQuotes ?? []).length })}
            </Typography>
            {removalError ? (
              <Alert severity="error" data-testid="delete-customer-error">
                {removalError}
              </Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setRemoving(null)}
            data-testid="cancel-delete-customer"
          >
            {t('common.cancel')}
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={confirmRemoval}
            disabled={remove.isPending}
            data-testid="confirm-delete-customer"
          >
            {t('common.delete')}
          </Button>
        </DialogActions>
      </Dialog>

      <CustomerDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(customer) => setSelected(customer)}
      />

      <CustomerDetailDrawer selected={selected} onClose={() => setSelected(null)} />
    </Stack>
  );
}
