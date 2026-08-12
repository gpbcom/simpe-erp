import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useBillingSettings, useSetCustomerBillingPeriodicity } from '@/api/queries';
import type { BillingPeriodicity, Customer } from '@/api/types';

/** The value the select holds when the customer follows the agency. */
const AGENCY = '';

/** The granularities a customer may be put on, with the label each carries. */
const PERIODICITIES: { value: BillingPeriodicity; label: string }[] = [
  { value: 'weekly', label: 'billingSettings.weekly' },
  { value: 'monthly', label: 'billingSettings.monthly' },
  { value: 'yearly', label: 'billingSettings.yearly' },
];

interface CustomerBillingCardProps {
  /** The customer whose invoicing granularity is being read or changed. */
  customer: Customer;
}

/**
 * How often this customer is invoiced.
 *
 * @param props - The customer.
 * @returns The rendered block.
 *
 * @remarks
 * **The first option is the agency's rule, and it is the ordinary answer.** It
 * is offered as a value rather than as an empty select, because taking an
 * override off has to be as reachable as putting one on — otherwise a customer
 * moved to weekly billing once stays there for good, and nothing on the screen
 * says why they are getting four invoices a month.
 *
 * The agency's own periodicity is named in that option rather than left as
 * "default". A manager choosing between "the agency's rule" and "monthly" needs
 * to know whether those are the same thing today.
 *
 * **Saving re-issues nothing**, and the card says so. The change decides what
 * the next generation run bills them over; an invoice already written keeps the
 * period it was written for, and a manager who assumed otherwise would be
 * waiting for documents that are never coming.
 */
export function CustomerBillingCard({ customer }: CustomerBillingCardProps) {
  const { t } = useTranslation();
  const { data: settings } = useBillingSettings();
  const save = useSetCustomerBillingPeriodicity();

  const change = (value: string) => {
    if (!customer.id) return;
    save.mutate({
      customerId: customer.id,
      periodicity: value === AGENCY ? null : (value as BillingPeriodicity),
    });
  };

  const agencyLabel = settings
    ? t('customer.billingFollowsAgency', {
        periodicity: t(`billingSettings.${settings.periodicity}`),
      })
    : t('customer.billingFollowsAgencyUnknown');

  return (
    <Stack spacing={1.5} data-testid="customer-billing">
      <Typography variant="h3">{t('customer.billing')}</Typography>

      <TextField
        select
        size="small"
        label={t('customer.billingPeriodicity')}
        value={customer.billing_periodicity ?? AGENCY}
        onChange={(event) => change(event.target.value)}
        disabled={save.isPending}
        sx={{ maxWidth: 360 }}
        slotProps={{
          select: { native: true },
          inputLabel: { shrink: true },
          htmlInput: { 'data-testid': 'customer-billing-periodicity' },
        }}
      >
        <option value={AGENCY}>{agencyLabel}</option>
        {PERIODICITIES.map((option) => (
          <option key={option.value} value={option.value}>
            {t(option.label)}
          </option>
        ))}
      </TextField>

      <Typography variant="caption" color="text.secondary">
        {t('customer.billingNotice')}
      </Typography>

      {save.isError ? (
        <Alert severity="error" data-testid="customer-billing-error">
          {t('customer.billingSaveFailed')}
        </Alert>
      ) : null}
      {save.isSuccess ? (
        <Alert severity="success" data-testid="customer-billing-saved">
          {t('customer.billingSaved')}
        </Alert>
      ) : null}
    </Stack>
  );
}
