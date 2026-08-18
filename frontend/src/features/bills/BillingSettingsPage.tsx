import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CircularProgress from '@mui/material/CircularProgress';
import FormControlLabel from '@mui/material/FormControlLabel';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import { useBillingSettings, useUpdateBillingSettings } from '@/api/queries';
import type { BillingPeriodicity } from '@/api/types';
import { EInvoicingWarning } from '@/features/integrations/EInvoicingWarning';
import { IntegrationsGallery } from '@/features/integrations/IntegrationsGallery';

interface FormState {
  periodicity: BillingPeriodicity;
  paymentTermsDays: string;
  penaltyMultiplier: string;
  indemnity: string;
  escompteOffered: boolean;
}

const MIN_TERMS_DAYS = 1;
const MAX_TERMS_DAYS = 60;

const PERIODICITIES: { value: BillingPeriodicity. Label: string }[] = [
  { value: 'weekly', label: 'billingSettings.weekly' },
  { value: 'monthly', label: 'billingSettings.monthly' },
  { value: 'yearly', label: 'billingSettings.yearly' },
];

/**
 * The invoicing rules a manager or administrator owns.
 *
 * @returns The rendered page.
 *
 * @remarks
 * **Every field on this screen is printed on the invoice**, which is the test
 * for whether a rule belongs here rather than in `app.yaml`: these are
 * statements the agency makes to its customers, and changing one is a
 * commercial decision rather than a deployment.
 *
 * **The periodicity here is the default, not the whole answer.** A customer may
 * be put on a granularity of their own from their own file, and is then billed
 * over their window rather than this one. The field says so beneath itself: a
 * manager who read this screen as "everybody is billed monthly" would have no
 * way to account for the weekly invoices coming out of the same run.
 *
 * **Saving re-issues nothing.** The rules apply to the next generation run. An
 * invoice already issued keeps the terms it was printed with, because those
 * terms are part of what the customer was told. The page says so rather than
 * leaving a manager to find out.
 *
 * The whole rule set is sent on every save. The server's payload defaults every
 * field, so a partial body would silently reset the ones this form did not
 * touch — on values that go out to customers.
 *
 * The payment-terms bounds are checked here *and* by the server. This copy is
 * for the message: caught here it names the ceiling before the request, and
 * caught by the server it is a 422 saying the same thing. The server's is the
 * one that actually guards the database — the ceiling is statutory, not a
 * preference.
 */
export function BillingSettingsPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<'rules' | 'integrations'>('rules');
  const { data: settings, isLoading } = useBillingSettings();
  const save = useUpdateBillingSettings();
  const [form, setForm] = useState<FormState | null>(null);

  useEffect(() => {
    if (!settings) return;
    setForm({
      periodicity: settings.periodicity,
      paymentTermsDays: String(settings.payment_terms_days),
      penaltyMultiplier: String(settings.late_penalty_multiplier),
      indemnity: settings.recovery_indemnity_eur,
      escompteOffered: settings.escompte_offered,
    });
  }, [settings]);

  if (isLoading || !form) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  const terms = Number(form.paymentTermsDays);
  const problem =
    terms < MIN_TERMS_DAYS
      ? 'billingSettings.termsTooShort'
      : terms > MAX_TERMS_DAYS
        ? 'billingSettings.termsTooLong'
        : null;

  const field = (key: keyof FormState) => ({
    value: String(form[key]),
    onChange: (event: { target: { value: string } }) =>
      setForm({ ...form, [key]: event.target.value }),
  });

  const submit = () => {
    if (problem) return;
    save.mutate({
      periodicity: form.periodicity,
      payment_terms_days: terms,
      late_penalty_multiplier: Number(form.penaltyMultiplier),
      recovery_indemnity_eur: form.indemnity,
      escompte_offered: form.escompteOffered,
    });
  };

  return (
    <Box data-testid="billing-settings-page">
      <Tabs
        value={tab}
        onChange={(_, value: 'rules' | 'integrations') => setTab(value)}
        sx={{ mb: 2 }}
        data-testid="billing-settings-tabs"
      >
        <Tab
          value="rules"
          label={t('billingSettings.tabRules')}
          data-testid="billing-tab-rules"
        />
        <Tab
          value="integrations"
          label={t('billingSettings.tabIntegrations')}
          data-testid="billing-tab-integrations"
        />
      </Tabs>

      {tab === 'integrations' ? <IntegrationsGallery /> : null}
      {tab === 'integrations' ? null : (
        <Box>
          <Typography variant="h5" sx={{ mb: 2 }}>
            {t('billingSettings.title')}
          </Typography>

          {}
          <EInvoicingWarning />

          <Alert severity="info" sx={{ mb: 2 }} data-testid="billing-settings-notice">
            {t('billingSettings.notice')}
          </Alert>

          <Card>
            <CardContent>
              <Stack spacing={2} sx={{ maxWidth: 480 }}>
                {}
                <TextField
                  select
                  helperText={t('billingSettings.periodicityHelp')}
                  label={t('billingSettings.periodicity')}
                  {...field('periodicity')}
                  slotProps={{
                    select: { native: true },
                    inputLabel: { shrink: true },
                    htmlInput: { 'data-testid': 'billing-periodicity' },
                  }}
                >
                  {PERIODICITIES.map((option) => (
                    <option key={option.value} value={option.value}>
                      {t(option.label)}
                    </option>
                  ))}
                </TextField>

                <TextField
                  type="number"
                  label={t('billingSettings.paymentTerms')}
                  {...field('paymentTermsDays')}
                  slotProps={{ htmlInput: { 'data-testid': 'billing-payment-terms' } }}
                />

                <TextField
                  type="number"
                  label={t('billingSettings.penaltyMultiplier')}
                  {...field('penaltyMultiplier')}
                  slotProps={{
                    htmlInput: { 'data-testid': 'billing-penalty-multiplier' },
                  }}
                />

                <TextField
                  label={t('billingSettings.indemnity')}
                  {...field('indemnity')}
                  slotProps={{ htmlInput: { 'data-testid': 'billing-indemnity' } }}
                />

                <FormControlLabel
                  control={
                    <Switch
                      checked={form.escompteOffered}
                      onChange={(event) =>
                        setForm({ ...form, escompteOffered: event.target.checked })
                      }
                      slotProps={{
                        input: { 'data-testid': 'billing-escompte' } as Record<
                          string,
                          string
                        >,
                      }}
                    />
                  }
                  label={t('billingSettings.escompte')}
                />

                {problem ? (
                  <Alert severity="warning" data-testid="billing-settings-problem">
                    {t(problem)}
                  </Alert>
                ) : null}
                {save.isError ? (
                  <Alert severity="error" data-testid="billing-settings-error">
                    {t('billingSettings.saveFailed')}
                  </Alert>
                ) : null}
                {save.isSuccess ? (
                  <Alert severity="success" data-testid="billing-settings-saved">
                    {t('billingSettings.saved')}
                  </Alert>
                ) : null}

                <Button
                  variant="contained"
                  onClick={submit}
                  disabled={problem !== null || save.isPending}
                  data-testid="billing-settings-save"
                >
                  {t('billingSettings.save')}
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Box>
      )}
    </Box>
  );
}
