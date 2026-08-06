import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import Grid from '@mui/material/Grid2';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import CloseIcon from '@mui/icons-material/Close';
import { useCustomerQuotes } from '@/api/queries';
import { QuoteArrangementCard } from './QuoteArrangementCard';
import { formatDate, formatDateTime } from '@/utils/format';
import type { Customer, Quote } from '@/api/types';

/**
 * The statuses that mean the agency has committed to delivering the work.
 *
 * `sent` is included: a quote a manager has issued is an offer outstanding, and
 * a family ringing about "the quote you sent" expects to find it here rather
 * than in a history nobody looks at.
 */
const LIVE: Quote['status'][] = ['accepted', 'sent', 'pending-validation'];

interface CustomerDetailDrawerProps {
  /** The customer to show, or `null` when the drawer is closed. */
  customer: Customer | null;
  /** Called when the drawer should close. */
  onClose: () => void;
}

/**
 * Everything the agency holds about one person, and what it is delivering.
 *
 * @param props - The customer and the close handler.
 * @returns The rendered drawer.
 *
 * @remarks
 * **Ongoing arrangements come first, history second.** The question this
 * screen is opened to answer is almost always "what are we doing for them at
 * the moment?" — a list ordered by date puts last year's rejected quote at the
 * top as often as not.
 *
 * "Ongoing" is read from the status and, for an accepted quote, from whether it
 * has been given an end date that has already passed. Both readings are shown
 * on the card rather than applied silently: a quote the screen has decided to
 * call finished, with nothing saying why, is a quote somebody will ring up
 * about.
 */
export function CustomerDetailDrawer({ customer, onClose }: CustomerDetailDrawerProps) {
  const { t, i18n } = useTranslation();
  const { data: quotes, isLoading } = useCustomerQuotes(customer?.id ?? '');

  const ongoing = (quotes ?? []).filter((quote) => LIVE.includes(quote.status));
  const past = (quotes ?? []).filter((quote) => !LIVE.includes(quote.status));
  const geocoded =
    customer !== null &&
    customer.address.latitude !== null &&
    customer.address.longitude !== null;

  /** One labelled fact. */
  const fact = (label: string, value: string, testId: string) => (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography data-testid={testId}>{value || '—'}</Typography>
    </Box>
  );

  return (
    <Drawer
      anchor="right"
      open={customer !== null}
      onClose={onClose}
      slotProps={{ paper: { sx: { width: { xs: '100%', md: 720 }, p: 3 } } }}
    >
      {customer === null ? null : (
        <Stack spacing={3} data-testid="customer-detail">
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="h2" sx={{ flexGrow: 1 }}>
              {customer.first_name} {customer.last_name}
            </Typography>
            <Chip
              size="small"
              label={t(`customer.status_${customer.registration_status}`)}
              data-testid="detail-status"
            />
            <IconButton onClick={onClose} data-testid="close-customer-detail">
              <CloseIcon />
            </IconButton>
          </Box>

          {!geocoded ? (
            // Worth an alert rather than an empty coordinate field: an address
            // that did not resolve means nobody can be routed to this home, and
            // every quote for them silently drops out of the planning run.
            <Alert severity="warning" data-testid="customer-not-geocoded">
              {t('customer.addressNotResolved')}
            </Alert>
          ) : null}

          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6 }}>
              {fact(t('customer.phone'), customer.phone_number, 'detail-phone')}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              {fact(t('customer.email'), customer.email, 'detail-email')}
            </Grid>
            <Grid size={12}>
              {fact(
                t('company.address'),
                `${customer.address.street}, ${customer.address.postal_code} ` +
                  `${customer.address.city}, ${customer.address.country}`,
                'detail-address',
              )}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              {fact(
                t('account.created'),
                formatDateTime(customer.created_at, i18n.language),
                'detail-created',
              )}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              {fact(
                t('account.updated'),
                formatDateTime(customer.updated_at, i18n.language),
                'detail-updated',
              )}
            </Grid>
          </Grid>

          <Divider />

          <Typography variant="h3">{t('customer.ongoingQuotes')}</Typography>
          {isLoading ? <Typography>{t('common.loading')}</Typography> : null}
          {!isLoading && ongoing.length === 0 ? (
            <Typography color="text.secondary" data-testid="no-ongoing-quote">
              {t('customer.noOngoingQuote')}
            </Typography>
          ) : null}
          <Stack spacing={1.5} data-testid="ongoing-quotes">
            {ongoing.map((quote) => (
              <QuoteArrangementCard key={quote.id} quote={quote} />
            ))}
          </Stack>

          {past.length > 0 ? (
            <>
              <Divider />
              <Typography variant="h3">{t('customer.pastQuotes')}</Typography>
              <Stack spacing={1} data-testid="past-quotes">
                {past.map((quote) => (
                  <Box
                    key={quote.id}
                    sx={{ display: 'flex', gap: 2, alignItems: 'center' }}
                    data-testid={`past-quote-${quote.reference}`}
                  >
                    <Typography variant="body2" sx={{ flexGrow: 1 }}>
                      {quote.reference}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {formatDate(quote.issued_on, i18n.language)}
                    </Typography>
                    <Chip
                      size="small"
                      variant="outlined"
                      label={t(`quote.status_${quote.status}`)}
                    />
                  </Box>
                ))}
              </Stack>
            </>
          ) : null}
        </Stack>
      )}
    </Drawer>
  );
}
