import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useInterruptQuote, useSetAutoRenew } from '@/api/queries';
import { QuoteStatusChip } from '@/features/quotes/QuoteStatusChip';
import { formatDate, formatMoney } from '@/utils/format';
import type { Quote } from '@/api/types';

interface QuoteArrangementCardProps {
  quote: Quote;
}

/**
 * One ongoing arrangement, with the two controls that end or extend it.
 *
 * @param props - The quote to show.
 * @returns The rendered card.
 *
 * @remarks
 * **Both controls live beside the arrangement they act on**, not on a separate
 * settings screen. Ending an arrangement and renewing one are decisions taken
 * while looking at what it currently delivers — which visits, from when, at
 * what price — and a screen that makes somebody remember a reference number
 * and go elsewhere is a screen where the wrong quote gets cancelled.
 *
 * **The end date is inclusive**, and the field says so. "From the 15th" means
 * the 15th is the last visit; reading it the other way takes away a visit a
 * family is expecting, and nothing would explain where it went.
 *
 * The total shown is what the arrangement costs **as it stands**. Interrupting
 * reprices on the server, so an ended arrangement shows the shorter figure the
 * moment it is saved — and the cancelled visits stay on the quote, which is
 * what lets the document answer why the invoice came in under what was signed.
 */
export function QuoteArrangementCard({ quote }: QuoteArrangementCardProps) {
  const { t, i18n } = useTranslation();
  const interrupt = useInterruptQuote();
  const setAutoRenew = useSetAutoRenew();
  const [lastDay, setLastDay] = useState('');
  const [error, setError] = useState<string | null>(null);

  const days = quote.lines.map((line) => line.service_date).sort();
  const total = quote.aggregates.reduce(
    (running, aggregate) => running + Number(aggregate.total_ttc ?? 0),
    0,
  );
  const canInterrupt = quote.status === 'accepted';

  const end = () => {
    if (!quote.id || !lastDay) return;
    setError(null);
    interrupt.mutate(
      { quoteId: quote.id, lastDay },
      {
        onSuccess: () => setLastDay(''),
        onError: (cause) =>
          setError(cause instanceof Error ? cause.message : t('common.error')),
      },
    );
  };

  return (
    <Card variant="outlined" data-testid={`arrangement-${quote.reference}`}>
      <CardContent>
        <Stack spacing={1.5}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Typography sx={{ flexGrow: 1 }}>{quote.reference}</Typography>
            <QuoteStatusChip status={quote.status} />
            {quote.interrupted_on ? (
              <Tooltip title={t('quote.interruptedTooltip')}>
                <Chip
                  size="small"
                  color="warning"
                  label={t('quote.endsOn', {
                    day: formatDate(quote.interrupted_on, i18n.language),
                  })}
                  data-testid={`arrangement-ends-${quote.reference}`}
                />
              </Tooltip>
            ) : null}
            {quote.renewed_from_id ? (
              <Tooltip title={t('quote.renewedTooltip')}>
                <Chip
                  size="small"
                  variant="outlined"
                  label={t('quote.renewed')}
                  data-testid={`arrangement-renewed-${quote.reference}`}
                />
              </Tooltip>
            ) : null}
          </Box>

          <Typography variant="body2" color="text.secondary">
            {t('quote.arrangementSummary', {
              count: quote.lines.length,
              from: formatDate(days[0] ?? null, i18n.language),
              to: formatDate(days[days.length - 1] ?? null, i18n.language),
            })}
            {' · '}
            {t('quote.validUntil', {
              day: formatDate(quote.valid_until, i18n.language),
            })}
          </Typography>

          <Typography data-testid={`arrangement-total-${quote.reference}`}>
            {formatMoney(total.toFixed(2), i18n.language)}
          </Typography>

          {error ? (
            <Alert severity="error" data-testid="arrangement-error">
              {error}
            </Alert>
          ) : null}

          <FormControlLabel
            control={
              <Switch
                checked={quote.auto_renew}
                onChange={(event) =>
                  quote.id &&
                  setAutoRenew.mutate({
                    quoteId: quote.id,
                    enabled: event.target.checked,
                  })
                }
                data-testid={`auto-renew-${quote.reference}`}
              />
            }
            label={t('quote.autoRenew')}
          />
          <Typography variant="caption" color="text.secondary">
            {t('quote.autoRenewHint')}
          </Typography>

          {canInterrupt ? (
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
              <TextField
                type="date"
                size="small"
                label={t('quote.lastDay')}
                value={lastDay}
                onChange={(event) => setLastDay(event.target.value)}
                helperText={t('quote.lastDayHint')}
                slotProps={{ inputLabel: { shrink: true } }}
                inputProps={{ 'data-testid': `interrupt-date-${quote.reference}` }}
              />
              <Button
                size="small"
                color="warning"
                variant="outlined"
                onClick={end}
                disabled={!lastDay || interrupt.isPending}
                data-testid={`interrupt-${quote.reference}`}
              >
                {quote.interrupted_on ? t('quote.changeEnd') : t('quote.interrupt')}
              </Button>
            </Box>
          ) : null}
        </Stack>
      </CardContent>
    </Card>
  );
}
