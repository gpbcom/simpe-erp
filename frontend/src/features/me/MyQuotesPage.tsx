import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMyQuotes, useSubmitQuote } from '@/api/queries';
import { QuoteEditorDialog } from '@/features/quotes/QuoteEditorDialog';
import { QuoteStatusChip } from '@/features/quotes/QuoteStatusChip';
import { AppIcon } from '@/components/icons/AppIcon';
import EditIcon from '@mui/icons-material/Edit';
import { formatDate, formatMoney } from '@/utils/format';
import type { Quote } from '@/api/types';

/**
 * The quotes an assistant wrote, and the button that submits one.
 *
 * @returns The rendered page.
 *
 * @remarks
 * The submit action appears **only on a draft**. A quote already waiting on a
 * manager, or one they have ruled on, has nothing an assistant can do to it —
 * showing a disabled button on every other row would be forty disabled buttons
 * advertising an action that is never available.
 */
export function MyQuotesPage() {
  const { t, i18n } = useTranslation();
  const { data, isLoading } = useMyQuotes();
  const submit = useSubmitQuote();
  const [editing, setEditing] = useState<Quote | null>(null);

  const total = (quote: Quote): string => {
    const sum = quote.lines.reduce(
      (running, line) => running + Number(line.total_ttc ?? 0),
      0,
    );
    return formatMoney(sum.toFixed(2), i18n.language);
  };

  const columns: GridColDef<Quote>[] = [
    { field: 'reference', headerName: t('quote.reference'), width: 120 },
    {
      field: 'status',
      headerName: t('quote.status'),
      width: 170,
      renderCell: (params) => <QuoteStatusChip status={params.row.status} />,
    },
    {
      field: 'lines',
      headerName: t('quote.lines'),
      width: 110,
      valueGetter: (_value, row) => row.lines.length,
    },
    {
      field: 'total',
      headerName: t('quote.totalTtc'),
      width: 140,
      valueGetter: (_value, row) => total(row),
    },
    {
      field: 'submitted_at',
      headerName: t('quote.submittedAt'),
      width: 160,
      valueGetter: (_value, row) => formatDate(row.submitted_at, i18n.language),
    },
    {
      field: 'actions',
      headerName: t('common.actions'),
      width: 340,
      sortable: false,
      renderCell: (params) =>
        params.row.status === 'draft' ? (
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              variant="outlined"
              startIcon={<EditIcon />}
              onClick={() => setEditing(params.row)}
              data-testid={`edit-quote-${params.row.reference}`}
            >
              {t('quote.edit')}
            </Button>
            <Button
              size="small"
              variant="contained"
              startIcon={<AppIcon name="quoteValidate" />}
              onClick={() => submit.mutate(params.row.id ?? '')}
              data-testid={`submit-quote-${params.row.reference}`}
            >
              {t('quote.submit')}
            </Button>
          </Stack>
        ) : null,
    },
  ];

  return (
    <Stack spacing={2}>
      <Box sx={{ display: 'flex', alignItems: 'center' }}>
        <Typography variant="h1" sx={{ flexGrow: 1 }}>
          {t('nav.myQuotes')}
        </Typography>
      </Box>

      <Card>
        <DataGrid
          rows={data ?? []}
          columns={columns}
          getRowId={(row) => row.id ?? row.reference}
          loading={isLoading}
          autoHeight
          disableRowSelectionOnClick
          initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
          pageSizeOptions={[25, 50, 100]}
          data-testid="my-quotes-grid"
        />
      </Card>

      <QuoteEditorDialog quote={editing} scope="own" onClose={() => setEditing(null)} />
    </Stack>
  );
}
