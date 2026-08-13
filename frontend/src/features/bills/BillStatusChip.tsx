import Chip from '@mui/material/Chip';
import { useTranslation } from 'react-i18next';
import { BILL_STATUS_COLOUR } from '@/theme/palette';
import type { BillStatus } from '@/api/types';

/** The label key each status is written with. */
const LABELS: Record<BillStatus, string> = {
  'to-be-validated': 'bill.statusToBeValidated',
  accepted: 'bill.statusAccepted',
  'waiting-payment': 'bill.statusWaitingPayment',
  paid: 'bill.statusPaid',
};

interface BillStatusChipProps {
  status: BillStatus;
}

/**
 * One invoice status, drawn the same way everywhere it appears.
 *
 * @param props - The status to draw.
 * @returns The rendered chip.
 *
 * @remarks
 * Shared rather than repeated, for the reason the quote's chip is: a status
 * that is amber in the list and grey in the drawer is a status the reader stops
 * trusting.
 *
 * `to-be-validated` is outlined as well as amber. It is the only state in which
 * the customer has been sent nothing at all, and the whole point of generating
 * invoices into it is that a manager notices they are there.
 */
export function BillStatusChip({ status }: BillStatusChipProps) {
  const { t } = useTranslation();
  return (
    <Chip
      size="small"
      label={t(LABELS[status])}
      color={BILL_STATUS_COLOUR[status]}
      variant={status === 'to-be-validated' ? 'outlined' : 'filled'}
      data-testid={`bill-status-${status}`}
    />
  );
}
