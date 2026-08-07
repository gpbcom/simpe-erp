import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Divider from '@mui/material/Divider';
import FormControlLabel from '@mui/material/FormControlLabel';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMyCompany, useUpdateMyCompany } from '@/api/queries';
import { formatDateTime } from '@/utils/format';
import { useSession } from '@/store/session';

/** Everything the form edits, flattened for the inputs. */
interface CompanyForm {
  name: string;
  registration_number: string;
  legal_form: string;
  share_capital: string;
  rcs_number: string;
  vat_number: string;
  phone_number: string;
  contact_email: string;
  street: string;
  postal_code: string;
  city: string;
  country: string;
  is_accepting_applications: boolean;
}

const EMPTY: CompanyForm = {
  name: '',
  registration_number: '',
  legal_form: '',
  share_capital: '',
  rcs_number: '',
  vat_number: '',
  phone_number: '',
  contact_email: '',
  street: '',
  postal_code: '',
  city: '',
  country: 'France',
  is_accepting_applications: true,
};

/**
 * The agency's own record: its identity, and whether it is open to applicants.
 *
 * @returns The rendered page.
 *
 * @remarks
 * **Administrator-only, and reached without an identifier.** A manager runs the
 * agency's work; its legal identity is not part of running the week. And the
 * agency shown is the one on the caller's own credential — the screen never
 * holds an identifier it could point at another tenant with.
 *
 * `is_accepting_applications` is the one field here with an effect on people
 * outside the agency: it decides whether it appears on the list a prospective
 * assistant chooses from when they apply. Closing it does not touch the
 * applications already waiting — somebody who applied yesterday still deserves
 * a decision — and the caption says so, because "stop accepting applications"
 * reads like it might discard them.
 */
export function CompanyPage() {
  const { t, i18n } = useTranslation();
  const user = useSession((state) => state.user);
  const isAdmin = user?.role === 'admin';
  const { data: company, isLoading, isError } = useMyCompany(isAdmin);
  const update = useUpdateMyCompany();

  const [form, setForm] = useState<CompanyForm>(EMPTY);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!company) return;
    setForm({
      name: company.name,
      registration_number: company.registration_number ?? '',
      legal_form: company.legal_form ?? '',
      share_capital: company.share_capital ?? '',
      rcs_number: company.rcs_number ?? '',
      vat_number: company.vat_number ?? '',
      phone_number: company.phone_number ?? '',
      contact_email: company.contact_email ?? '',
      street: company.address?.street ?? '',
      postal_code: company.address?.postal_code ?? '',
      city: company.address?.city ?? '',
      country: company.address?.country ?? 'France',
      is_accepting_applications: company.is_accepting_applications,
    });
  }, [company]);

  const field = (key: keyof CompanyForm, label: string, extra = {}) => (
    <TextField
      label={label}
      value={String(form[key])}
      onChange={(event) => setForm({ ...form, [key]: event.target.value })}
      inputProps={{ 'data-testid': `company-${key.replace(/_/g, '-')}` }}
      {...extra}
    />
  );

  const save = () => {
    setError(null);
    setSaved(false);
    // An address is all-or-nothing. A street with no city cannot be geocoded,
    // and a half-filled one stored is a row the planner would try to route
    // from and silently fail on.
    const hasAddress = Boolean(
      form.street.trim() && form.postal_code.trim() && form.city.trim(),
    );
    update.mutate(
      {
        name: form.name.trim(),
        registration_number: form.registration_number.trim() || null,
        legal_form: form.legal_form.trim() || null,
        share_capital: form.share_capital.trim() || null,
        rcs_number: form.rcs_number.trim() || null,
        vat_number: form.vat_number.trim() || null,
        phone_number: form.phone_number.trim() || null,
        contact_email: form.contact_email.trim() || null,
        address: hasAddress
          ? {
              street: form.street.trim(),
              postal_code: form.postal_code.trim(),
              city: form.city.trim(),
              country: form.country.trim() || 'France',
              // Left unresolved on purpose: the server geocodes an address it
              // is given without one, and a coordinate typed here would be a
              // second answer to a question only the geocoder can settle.
              latitude: null,
              longitude: null,
              geocoding_error: null,
            }
          : null,
        is_accepting_applications: form.is_accepting_applications,
      },
      {
        onSuccess: () => setSaved(true),
        onError: (cause) =>
          setError(cause instanceof Error ? cause.message : t('common.error')),
      },
    );
  };

  if (!isAdmin) {
    return (
      <Alert severity="warning" data-testid="company-forbidden">
        {t('company.administratorOnly')}
      </Alert>
    );
  }
  if (isLoading) return <Typography>{t('common.loading')}</Typography>;
  if (isError || !company) {
    return <Alert severity="error">{t('common.error')}</Alert>;
  }

  const valid = Boolean(form.name.trim());

  return (
    <Stack spacing={3}>
      <Typography variant="h1">{t('company.title')}</Typography>

      {error ? (
        <Alert severity="error" data-testid="company-error">
          {error}
        </Alert>
      ) : null}
      {saved ? (
        <Alert severity="success" data-testid="company-saved">
          {t('common.saved')}
        </Alert>
      ) : null}

      <Card data-testid="company-section">
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h3">{t('company.identity')}</Typography>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, md: 6 }}>{field('name', t('company.name'))}</Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                {field('registration_number', t('company.registrationNumber'), {
                  helperText: t('company.registrationNumberHint'),
                })}
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                {field('contact_email', t('company.contactEmail'), {
                  helperText: t('company.contactEmailHint'),
                })}
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                {field('phone_number', t('company.phoneNumber'))}
              </Grid>
            </Grid>

            <Divider />

            {/*
              What a quote must say about whoever is making the offer. Kept
              in its own section rather than mixed into the identity block:
              these are the fields an accountant fills in once, and burying
              them among the trading name is how they stay empty.
            */}
            <Box>
              <Typography variant="h3">{t('company.legalIdentity')}</Typography>
              <Typography variant="body2" color="text.secondary">
                {t('company.legalIdentityHint')}
              </Typography>
            </Box>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, md: 6 }}>
                {field('legal_form', t('company.legalForm'), {
                  helperText: t('company.legalFormHint'),
                })}
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                {field('share_capital', t('company.shareCapital'))}
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                {field('rcs_number', t('company.rcsNumber'))}
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                {field('vat_number', t('company.vatNumber'), {
                  helperText: t('company.vatNumberHint'),
                })}
              </Grid>
            </Grid>

            <Divider />

            <Typography variant="h3">{t('company.address')}</Typography>
            <Grid container spacing={2}>
              <Grid size={12}>{field('street', t('hca.street'))}</Grid>
              <Grid size={{ xs: 12, sm: 4 }}>
                {field('postal_code', t('hca.postalCode'))}
              </Grid>
              <Grid size={{ xs: 12, sm: 4 }}>{field('city', t('hca.city'))}</Grid>
              <Grid size={{ xs: 12, sm: 4 }}>{field('country', t('hca.country'))}</Grid>
            </Grid>

            <Divider />

            <Typography variant="h3">{t('company.applications')}</Typography>
            <FormControlLabel
              control={
                <Switch
                  checked={form.is_accepting_applications}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      is_accepting_applications: event.target.checked,
                    })
                  }
                  data-testid="company-accepting"
                />
              }
              label={t('company.acceptingApplications')}
            />
            <Typography variant="caption" color="text.secondary">
              {t('company.acceptingApplicationsHint')}
            </Typography>

            <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Button
                variant="contained"
                onClick={save}
                disabled={!valid || update.isPending}
                data-testid="save-company"
              >
                {t('common.save')}
              </Button>
            </Box>

            <Typography variant="caption" color="text.secondary">
              {t('account.created')}:{' '}
              {formatDateTime(company.created_at ?? null, i18n.language)}
              {' · '}
              {t('account.updated')}:{' '}
              {formatDateTime(company.updated_at ?? null, i18n.language)}
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
