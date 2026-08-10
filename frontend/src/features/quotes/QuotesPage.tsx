import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import Card from '@mui/material/Card';
import Snackbar from '@mui/material/Snackbar';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import Typography from '@mui/material/Typography';
import {
  useCustomers,
  useQuotes,
  useAcceptQuote,
  useRefuseQuote,
  useRejectQuote,
  useSendQuote,
  useValidateQuote,
} from '@/api/queries';
import { NewQuoteDialog } from './NewQuoteDialog';
import { QuoteEditorDialog } from './QuoteEditorDialog';
import { QuotePlanningFeedback } from './QuotePlanningFeedback';
import { QuoteStatusChip } from './QuoteStatusChip';
import { AppIcon } from '@/components/icons/AppIcon';
import EditIcon from '@mui/icons-material/Edit';
import { formatDate, formatMoney } from '@/utils/format';
import { EntityFilterBar } from '@/components/filters/EntityFilterBar';
import type { FilterDetail } from '@/components/filters/EntityFilterBar';
import { useEntityFilter } from '@/components/filters/entityFilter';
import type { EntityFilterSpec } from '@/components/filters/entityFilter';
import type { Quote, QuoteStatus } from '@/api/types';

/** The tabs across the top, in the order work flows through them. */
const TABS: { key: string; status?: QuoteStatus }[] = [
  { key: 'all' },
  { key: 'pending', status: 'pending-validation' },
  { key: 'draft', status: 'draft' },
  { key: 'sent', status: 'sent' },
  { key: 'accepted', status: 'accepted' },
  { key: 'rejected', status: 'rejected' },
];

/**
 * The quote filter's fields, **without ``status``**.
 *
 * @remarks
 * The status tabs above already own that field and default to the validation
 * queue, which is the first thing a manager should reach. Putting it in the
 * filter too would be two mechanisms for one value, and the one that lost would
 * do so silently.
 */
const QUOTE_FILTER_SPEC: EntityFilterSpec = {
  textFields: ['search', 'reference', 'customer_id', 'authored_by'],
  flagFields: ['is_ongoing', 'auto_renew'],
  enumFields: {},
};

/** What is folded away behind "more filters". */
const QUOTE_DETAILS: FilterDetail[] = [
  { field: 'reference', label: 'quote.filterReference', kind: 'text' },
  { field: 'customer_id', label: 'quote.filterCustomer', kind: 'text' },
  { field: 'authored_by', label: 'quote.filterAuthor', kind: 'text' },
  {
    field: 'is_ongoing',
    label: 'quote.filterOngoing',
    kind: 'flag',
    options: [
      { value: 'true', label: 'quote.filterOngoingYes' },
      { value: 'false', label: 'quote.filterOngoingNo' },
    ],
  },
  {
    field: 'auto_renew',
    label: 'quote.filterAutoRenew',
    kind: 'flag',
    options: [
      { value: 'true', label: 'quote.filterAutoRenewYes' },
      { value: 'false', label: 'quote.filterAutoRenewNo' },
    ],
  },
];

/**
 * Every quote in the agency, and the manager's validation queue.
 *
 * @returns The rendered page.
 *
 * @remarks
 * The validation queue is not a separate screen — it is this one, filtered to
 * `pending-validation`, and it is the second tab so it is the first thing a
 * manager reaches. Building it as its own page would have meant two grids to
 * keep in step and two places to fix a column.
 */
export function QuotesPage() {
  const { t, i18n } = useTranslation();
  const [tab, setTab] = useState(1);
  const [editing, setEditing] = useState<Quote | null>(null);
  const [writing, setWriting] = useState(false);
  const status = TABS[tab]?.status;
  const quoteFilter = useEntityFilter(QUOTE_FILTER_SPEC);
  const { data, isLoading } = useQuotes(status, quoteFilter.filter);
  const { data: customers } = useCustomers();
  // What validating actually did, said once, where the manager is looking.
  // Validation now accepts the quote outright, so the confirmation says the
  // work is committed rather than leaving the manager to wonder. It used to
  // stop at `sent` and need a second acceptance nothing asked for, which is
  // how a validated fortnight of work reached no planning run at all.
  const [validated, setValidated] = useState(false);
  const validate = useValidateQuote();
  const refuse = useRefuseQuote();
  const send = useSendQuote();
  const accept = useAcceptQuote();
  const reject = useRejectQuote();

  const customerName = (customerId: string): string => {
    const found = (customers ?? []).find((entry) => entry.id === customerId);
    return found ? `${found.first_name} ${found.last_name}` : customerId;
  };

  const total = (quote: Quote): number =>
    quote.lines.reduce((running, line) => running + Number(line.total_ttc ?? 0), 0);

  const columns: GridColDef<Quote>[] = [
    { field: 'reference', headerName: t('quote.reference'), width: 110 },
    {
      field: 'customer_id',
      headerName: t('quote.customer'),
      flex: 1,
      minWidth: 180,
      valueGetter: (_value, row) => customerName(row.customer_id),
    },
    {
      field: 'status',
      headerName: t('quote.status'),
      width: 170,
      renderCell: (params) => <QuoteStatusChip status={params.row.status} />,
    },
    {
      field: 'planning_feedback',
      headerName: t('quote.planning'),
      width: 170,
      sortable: false,
      // Only the quotes with a problem carry anything. A column of empty
      // cells with one chip in it is exactly what makes the one chip visible.
      renderCell: (params) =>
        params.row.planning_feedback ? (
          <Chip
            size="small"
            color="warning"
            label={t('quote.planningReturnedChip')}
            data-testid={`planning-returned-${params.row.reference}`}
          />
        ) : null,
    },
    {
      field: 'lines',
      headerName: t('quote.lines'),
      width: 90,
      valueGetter: (_value, row) => row.lines.length,
    },
    {
      field: 'total',
      headerName: t('quote.totalTtc'),
      width: 130,
      valueGetter: (_value, row) => total(row),
      valueFormatter: (value: number) => formatMoney(value.toFixed(2), i18n.language),
    },
    {
      field: 'issued_on',
      headerName: t('quote.issuedOn'),
      width: 140,
      valueGetter: (_value, row) => formatDate(row.issued_on, i18n.language),
    },
    {
      field: 'actions',
      headerName: t('common.actions'),
      width: 380,
      sortable: false,
      // Rendered only for a quote awaiting validation. A manager looking at an
      // accepted quote has no decision to make about it, and a row of greyed
      // buttons on every other line would bury the ones that matter.
      renderCell: (params) => (
        <Stack direction="row" spacing={1}>
          {/* **Editable at every status**, matching what the service allows.
              This was drafts only, on the reasoning that what a customer was
              sent must stay what they were sent — but the planner now sends
              quotes back to be validated when their work will not fit, and
              those are past draft by definition. A quote returned for a new
              date that nobody can change is a dead end.

              The trade is real and worth naming: nothing records what the
              figures were before an edit, and an edit reprices against the
              catalogue as it stands now. */}
          <Button
            size="small"
            variant="outlined"
            startIcon={<EditIcon />}
            onClick={() => setEditing(params.row)}
            data-testid={`edit-${params.row.reference}`}
          >
            {t('quote.edit')}
          </Button>
          {params.row.status === 'draft' ? (
            <>
              {/* Sending accepts the quote: a manager writes one for an
                  arrangement they have already settled with the family, and
                  the hours have to reach the planner. Nothing else in the
                  agency moves a hand-written quote past `sent`, so without
                  this the visits were promised and never scheduled. */}
              <Button
                size="small"
                variant="contained"
                startIcon={<AppIcon name="quoteValidate" />}
                onClick={() => send.mutate(params.row.id ?? '')}
                disabled={send.isPending}
                data-testid={`send-${params.row.reference}`}
              >
                {t('quote.send')}
              </Button>
            </>
          ) : null}
          {params.row.status === 'pending-validation' ? (
            <>
              <Button
                size="small"
                variant="contained"
                color="success"
                startIcon={<AppIcon name="quoteValidate" />}
                onClick={() =>
                  validate.mutate(params.row.id ?? '', {
                    onSuccess: () => setValidated(true),
                  })
                }
                data-testid={`validate-${params.row.reference}`}
              >
                {t('quote.validate')}
              </Button>
              <Button
                size="small"
                variant="outlined"
                color="warning"
                startIcon={<AppIcon name="quoteRefuse" />}
                onClick={() => refuse.mutate(params.row.id ?? '')}
                data-testid={`refuse-${params.row.reference}`}
              >
                {t('quote.refuse')}
              </Button>
            </>
          ) : null}
          {/* Kept for quotes already stored as `sent`. Nothing produces that
              status any more — validating accepts outright — but rows written
              before that change still exist, and without these two buttons
              they would sit in a tab with no way forward. */}
          {params.row.status === 'sent' ? (
            <>
              <Button
                size="small"
                variant="contained"
                color="success"
                startIcon={<AppIcon name="quoteValidate" />}
                onClick={() => accept.mutate(params.row.id ?? '')}
                disabled={accept.isPending}
                data-testid={`accept-${params.row.reference}`}
              >
                {t('quote.accept')}
              </Button>
              <Button
                size="small"
                variant="outlined"
                color="error"
                startIcon={<AppIcon name="quoteRefuse" />}
                onClick={() => reject.mutate(params.row.id ?? '')}
                disabled={reject.isPending}
                data-testid={`reject-${params.row.reference}`}
              >
                {t('quote.reject')}
              </Button>
            </>
          ) : null}
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" spacing={2}>
        <Typography variant="h1" sx={{ flexGrow: 1 }}>
          {t('nav.quotes')}
        </Typography>
        <Button
          variant="contained"
          startIcon={<AppIcon name="quote" />}
          onClick={() => setWriting(true)}
          data-testid="new-quote"
        >
          {t('quote.new')}
        </Button>
      </Stack>

      <NewQuoteDialog open={writing} onClose={() => setWriting(false)} />

      <Typography variant="h1">{t('nav.quotes')}</Typography>

      <Card>
        <Tabs
          value={tab}
          onChange={(_event, next: number) => setTab(next)}
          data-testid="quote-tabs"
        >
          {TABS.map((entry, index) => (
            <Tab
              key={entry.key}
              label={
                entry.status ? t(`quote.status_${entry.status}`) : t('common.filter')
              }
              data-testid={`quote-tab-${entry.key}`}
              value={index}
            />
          ))}
        </Tabs>

        <Box sx={{ px: 2, pt: 2 }}>
          <EntityFilterBar
            state={quoteFilter}
            testId="quote"
            searchLabel="quote.search"
            details={QUOTE_DETAILS}
          />
        </Box>

        {/* The explanation sits above the list rather than behind a click.
            A quote back in the validation queue with no visible reason reads
            as the system having lost it, and the offered slots are what turn
            the follow-up call into a decision. */}
        {(data ?? [])
          .filter((quote) => quote.planning_feedback)
          .map((quote) => (
            <Box key={quote.id ?? quote.reference} sx={{ px: 2, pt: 2 }}>
              <QuotePlanningFeedback
                feedback={quote.planning_feedback}
                quoteId={quote.id ?? undefined}
              />
            </Box>
          ))}

        {!isLoading && (data ?? []).length === 0 && status === 'pending-validation' ? (
          <Box sx={{ p: 6, textAlign: 'center' }} data-testid="empty-validation-queue">
            <Typography color="text.secondary">{t('quote.emptyQueue')}</Typography>
          </Box>
        ) : (
          <DataGrid
            rows={data ?? []}
            columns={columns}
            getRowId={(row) => row.id ?? row.reference}
            loading={isLoading}
            autoHeight
            disableRowSelectionOnClick
            initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
            pageSizeOptions={[25, 50, 100]}
            data-testid="quotes-grid"
          />
        )}
      </Card>

      <QuoteEditorDialog
        quote={editing}
        scope="manager"
        onClose={() => setEditing(null)}
      />

      <Snackbar
        open={validated}
        autoHideDuration={8000}
        onClose={() => setValidated(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity="success"
          onClose={() => setValidated(false)}
          data-testid="validated-and-accepted"
        >
          {t('quote.validatedAwaitingAcceptance')}
        </Alert>
      </Snackbar>
    </Stack>
  );
}
