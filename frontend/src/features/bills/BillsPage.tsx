import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { EInvoicingWarning } from '@/features/integrations/EInvoicingWarning';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { useBills } from '@/api/queries';
import { EntityFilterBar } from '@/components/filters/EntityFilterBar';
import type { FilterDetail } from '@/components/filters/EntityFilterBar';
import {
  useEntityFilter,
  type EntityFilterSpec,
} from '@/components/filters/entityFilter';
import { BillDetailDrawer } from './BillDetailDrawer';
import { BillStatusChip } from './BillStatusChip';
import { GenerateBillsDialog } from './GenerateBillsDialog';
import type { Bill } from '@/api/types';

const BILL_FILTER_SPEC: EntityFilterSpec = {
  textFields: ['search', 'number', 'customer_id'],
  flagFields: ['is_sent'],
  enumFields: {
    status: ['to-be-validated', 'accepted', 'waiting-payment', 'paid'],
  },
};

const BILL_DETAILS: FilterDetail[] = [
  {
    field: 'status',
    label: 'bills.filterStatus',
    kind: 'choice',
    options: [
      { value: 'to-be-validated', label: 'bill.statusToBeValidated' },
      { value: 'accepted', label: 'bill.statusAccepted' },
      { value: 'waiting-payment', label: 'bill.statusWaitingPayment' },
      { value: 'paid', label: 'bill.statusPaid' },
    ],
  },
  {
    field: 'is_sent',
    label: 'bills.filterSent',
    kind: 'flag',
    options: [
      { value: 'true', label: 'bills.filterSentYes' },
      { value: 'false', label: 'bills.filterSentNo' },
    ],
  },
];

/**
 * Every invoice the agency has issued.
 *
 * @returns The rendered page.
 *
 * @remarks
 * The list is the whole billing screen: generating, reviewing, validating and
 * downloading all start here. There is no separate validation queue — filtering
 * to `to-be-validated` is the queue, for the reason the quote screen has no
 * second page either: two grids to keep in step is two places to fix a column.
 *
 * **Generating sends nothing.** The button writes invoices that wait for a
 * manager; the drawer is where one is validated, and validating is what emails
 * the customer.
 */
export function BillsPage() {
  const { t, i18n } = useTranslation();
  const [selected, setSelected] = useState<Bill | null>(null);
  const [generating, setGenerating] = useState(false);
  const billFilter = useEntityFilter(BILL_FILTER_SPEC);
  const { data: bills, isLoading } = useBills(billFilter.filter);

  const money = (amount: string): string =>
    `${Number(amount).toLocaleString(i18n.language, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} €`;

  const columns: GridColDef<Bill>[] = [
    { field: 'number', headerName: t('bill.number'), width: 160 },
    {
      field: 'customer_full_name',
      headerName: t('bill.customer'),
      flex: 1,
      minWidth: 180,
    },
    {
      field: 'period_start',
      headerName: t('bill.period'),
      width: 210,
      valueGetter: (_value, row) => `${row.period_start} → ${row.period_end}`,
    },
    { field: 'due_on', headerName: t('bill.dueOn'), width: 120 },
    {
      field: 'total_ttc',
      headerName: t('bill.totalTtc'),
      width: 130,
      align: 'right',
      headerAlign: 'right',
      valueGetter: (_value, row) => money(row.total_ttc),
    },
    {
      field: 'status',
      headerName: t('bill.status'),
      width: 180,
      renderCell: (params) => <BillStatusChip status={params.row.status} />,
    },
  ];

  return (
    <Box data-testid="bills-page">
      {/* Where a manager actually works, which is why the warning is here
          and not only in the settings. */}
      <EInvoicingWarning withLink />
      <Stack
        direction="row"
        spacing={2}
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 2 }}
      >
        <Typography variant="h5">{t('bills.title')}</Typography>
        <Button
          variant="contained"
          onClick={() => setGenerating(true)}
          data-testid="generate-bills"
        >
          {t('bills.generate')}
        </Button>
      </Stack>

      <EntityFilterBar
        state={billFilter}
        testId="bill"
        searchLabel="bills.search"
        details={BILL_DETAILS}
      />

      <Box sx={{ height: 620, mt: 2 }}>
        <DataGrid
          rows={bills ?? []}
          columns={columns}
          loading={isLoading}
          getRowId={(row) => row.id ?? row.number}
          onRowClick={(params) => setSelected(params.row)}
          disableRowSelectionOnClick
          initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
          pageSizeOptions={[25, 50, 100]}
          sx={{ '& .MuiDataGrid-row': { cursor: 'pointer' } }}
          data-testid="bills-grid"
        />
      </Box>

      <BillDetailDrawer selected={selected} onClose={() => setSelected(null)} />
      <GenerateBillsDialog open={generating} onClose={() => setGenerating(false)} />
    </Box>
  );
}
