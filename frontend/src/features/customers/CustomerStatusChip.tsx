import Chip from '@mui/material/Chip';
import { useTranslation } from 'react-i18next';
import { REGISTRATION_STATUS_COLOUR } from '@/theme/palette';
import type { RegistrationStatus } from '@/api/types';

interface CustomerStatusChipProps {
  /** The status to draw. */
  status: RegistrationStatus;
  /** The hook the campaign finds this chip by. */
  testId: string;
}

/**
 * One customer's standing, drawn the same way everywhere it appears.
 *
 * @param props - The status and the customer it belongs to.
 * @returns The rendered chip.
 *
 * @remarks
 * Shared rather than repeated. The same chip is drawn in the grid, in the
 * detail drawer and in an assistant's own portfolio, and until now each spelled
 * its own colour rule — which is how `prospect` would have arrived amber in one
 * place and grey in the other two.
 *
 * A prospect is amber for the same reason a quote awaiting validation is: it is
 * the state waiting on a person, and the work behind it stays out of every
 * planning run until somebody acts.
 */
export function CustomerStatusChip({ status, testId }: CustomerStatusChipProps) {
  const { t } = useTranslation();
  return (
    <Chip
      size="small"
      label={t(`customer.status_${status}`)}
      color={REGISTRATION_STATUS_COLOUR[status]}
      variant={status === 'stopped' ? 'outlined' : 'filled'}
      data-testid={testId}
    />
  );
}
