import Chip from '@mui/material/Chip';
import { useTranslation } from 'react-i18next';
import { QUOTE_STATUS_COLOUR } from '@/theme/palette';
import type { QuoteStatus } from '@/api/types';

interface QuoteStatusChipProps {

  status: QuoteStatus;
}

/**
 * One quote status, drawn the same way everywhere it appears.
 *
 * @param props - The status to draw.
 * @returns The rendered chip.
 *
 * @remarks
 * Shared rather than repeated, because a status that is amber in the list and
 * grey in the detail is a status the reader stops trusting. `pending-validation`
 * is the amber one on purpose: it is the only state that is waiting on a
 * person, and the whole validation workflow exists to make it noticeable.
 */
export function QuoteStatusChip({ status }: QuoteStatusChipProps) {
  const { t } = useTranslation();
  return (
    <Chip
      label={t(`quote.status_${status}`)}
      color={QUOTE_STATUS_COLOUR[status]}
      variant={status === 'draft' ? 'outlined' : 'filled'}
      data-testid={`quote-status-${status}`}
    />
  );
}
