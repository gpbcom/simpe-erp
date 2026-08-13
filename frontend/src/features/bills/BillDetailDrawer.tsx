import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useBill, useDownloadBill, useSetBillStatus } from '@/api/queries';
import { AppIcon } from '@/components/icons/AppIcon';
import { BillStatusChip } from './BillStatusChip';
import type { Bill, BillStatus } from '@/api/types';

const ORDER: BillStatus[] = ['to-be-validated', 'accepted', 'waiting-payment', 'paid'];

const FORWARD_LABELS: Partial<Record<BillStatus, string>> = {
  accepted: 'bills.validate',
  paid: 'bills.markPaid',
};

interface BillDetailDrawerProps {
  /** The row that was clicked, or `null` when the drawer is closed. */
  selected: Bill | null;
  /** Close it. */
  onClose: () => void;
}

/**
 * One invoice: the visits it charges for, and what may be done to it.
 *
 * @param props - The clicked row, and how to close.
 * @returns The rendered drawer.
 *
 * @remarks
 * **The rows are visits, never quotes.** Each names a date, a service, the
 * assistant who delivered it and the hours worked. No quote reference appears
 * anywhere — the screen must not show what the document does not, because a
 * manager reading one and quoting it to a customer would be reading from a
 * different document than the one they hold.
 *
 * The record is re-read rather than trusted: the grid row is a snapshot taken
 * when the page loaded, and an invoice validated in another tab since would
 * otherwise offer a move that has already happened.
 *
 * Only the **legal** neighbours are offered. The lifecycle moves one step at a
 * time, and the server decides against the stored status — so a screen showing
 * a stale row offers a move that is refused with a 409 rather than one that
 * silently skips a step.
 */
export function BillDetailDrawer({ selected, onClose }: BillDetailDrawerProps) {
  const { t, i18n } = useTranslation();
  const { data: fresh } = useBill(selected?.id ?? '');
  const bill = fresh ?? selected;
  const setStatus = useSetBillStatus(bill?.id ?? '');
  const download = useDownloadBill();

  if (!bill) return null;

  const index = ORDER.indexOf(bill.status);
  const next = ORDER[index + 1];
  const previous = ORDER[index - 1];

  const money = (amount: string): string =>
    `${Number(amount).toLocaleString(i18n.language, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} €`;

  const hours = (minutes: number): string =>
    `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')}`;

  return (
    <Drawer anchor="right" open onClose={onClose}>
      <Box sx={{ width: 720, p: 3 }} data-testid="bill-detail-drawer">
        <Stack
          direction="row"
          spacing={2}
          alignItems="center"
          justifyContent="space-between"
        >
          <Typography variant="h6">
            {t('bills.detailTitle', { number: bill.number })}
          </Typography>
          <BillStatusChip status={bill.status} />
        </Stack>

        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          {bill.customer_full_name} · {bill.period_start} → {bill.period_end}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {`${t('bill.issuedOn')} ${bill.issued_on} · ${t('bill.dueOn')} ${bill.due_on}`}
        </Typography>
        <Typography
          variant="body2"
          color="text.secondary"
          data-testid="bill-sent-state"
        >
          {bill.sent_at
            ? `${t('bill.sentOn')} ${bill.sent_at.slice(0, 10)}`
            : t('bill.notSent')}
        </Typography>

        {}
        {bill.recipient.kind !== 'individual' ? (
          <Typography
            variant="body2"
            color="text.secondary"
            data-testid="bill-recipient"
          >
            {`${t('bill.billedTo')} ${bill.recipient.name}`}
            {bill.recipient.siren ? ` · ${bill.recipient.siren}` : ''}
            {` · ${t(`bill.recipient_${bill.recipient.kind}`)}`}
          </Typography>
        ) : null}

        <Divider sx={{ my: 2 }} />

        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          {t('bill.lines')}
        </Typography>

        {bill.lines.length === 0 ? (
          <Typography variant="body2" data-testid="bill-no-line">
            {t('bills.noLine')}
          </Typography>
        ) : (
          <Table size="small" data-testid="bill-lines">
            <TableHead>
              <TableRow>
                <TableCell>{t('bill.day')}</TableCell>
                <TableCell>{t('bill.service')}</TableCell>
                <TableCell>{t('bill.assistant')}</TableCell>
                <TableCell align="right">{t('bill.hours')}</TableCell>
                <TableCell align="right">{t('bill.unitPrice')}</TableCell>
                <TableCell align="right">{t('bill.vatRate')}</TableCell>
                <TableCell align="right">{t('bill.totalHt')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {bill.lines.map((line, position) => (
                <TableRow key={line.id ?? `${line.quote_line_id}-${position}`}>
                  <TableCell>{line.day ?? line.service_date}</TableCell>
                  <TableCell>{line.name}</TableCell>
                  <TableCell>{line.hca_full_name ?? t('bill.notPlanned')}</TableCell>
                  <TableCell align="right">{hours(line.duration_minutes)}</TableCell>
                  <TableCell align="right">{money(line.hourly_rate_ht)}</TableCell>
                  <TableCell align="right">
                    {`${(Number(line.vat_rate) * 100).toFixed(1)} %`}
                  </TableCell>
                  <TableCell align="right">{money(line.total_ht)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        <Stack spacing={0.5} sx={{ mt: 2, alignItems: 'flex-end' }}>
          <Typography variant="body2">
            {`${t('bill.totalHt')} : ${money(bill.total_ht)}`}
          </Typography>
          <Typography variant="body2">
            {`${t('bill.vat')} : ${money(bill.total_vat)}`}
          </Typography>
          <Typography variant="subtitle1" data-testid="bill-total-ttc">
            {`${t('bill.totalTtc')} : ${money(bill.total_ttc)}`}
          </Typography>
        </Stack>

        {setStatus.isError ? (
          <Alert severity="error" sx={{ mt: 2 }} data-testid="bill-status-error">
            {t('bills.statusFailed')}
          </Alert>
        ) : null}
        {download.isError ? (
          <Alert severity="error" sx={{ mt: 2 }} data-testid="bill-download-error">
            {t('bills.downloadFailed')}
          </Alert>
        ) : null}

        <Stack direction="row" spacing={1} sx={{ mt: 3, flexWrap: 'wrap', gap: 1 }}>
          <Button
            startIcon={<AppIcon name="export" />}
            onClick={() => download.mutate({ id: bill.id ?? '', number: bill.number })}
            disabled={!bill.document_key || download.isPending}
            data-testid="bill-download"
          >
            {t('bills.download')}
          </Button>

          {next ? (
            <Button
              variant="contained"
              onClick={() => setStatus.mutate({ status: next })}
              disabled={setStatus.isPending}
              data-testid={`bill-advance-${next}`}
            >
              {t(FORWARD_LABELS[next] ?? 'common.save')}
            </Button>
          ) : null}

          {previous ? (
            <Button
              color="inherit"
              onClick={() => setStatus.mutate({ status: previous })}
              disabled={setStatus.isPending}
              data-testid={`bill-step-back-${previous}`}
            >
              {t('bills.stepBack')}
            </Button>
          ) : null}
        </Stack>
      </Box>
    </Drawer>
  );
}
