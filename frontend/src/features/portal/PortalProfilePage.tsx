import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { usePortalProfile, useUpdatePortalProfile } from '@/api/queries';
import { CustomerStatusChip } from '@/features/customers/CustomerStatusChip';
import type { CustomerProfileUpdate } from '@/api/types';

const EMPTY: CustomerProfileUpdate = {
  first_name: '',
  last_name: '',
  phone_number: '',
  email: '',
  address: { street: '', postal_code: '', city: '', country: 'France' },
};

/**
 * The household's own details, and the one screen where they correct them.
 *
 * @returns The rendered page.
 *
 * @remarks
 * **Everything on this form is theirs to change; everything absent is not.**
 * There is no registration status and no billing periodicity — the first
 * decides whether the planner schedules their work, and the second is a
 * commercial term the agency agrees. Neither is a field the server would
 * accept, so leaving them off is honest rather than decorative.
 *
 * The address is the one that matters. It is where care is delivered and what
 * every planning run routes to, so a household correcting a mistyped street is
 * the fastest path to work reaching the right door — and the server re-geocodes
 * it on the way in, which is why an address the map cannot find is saved with
 * the failure recorded rather than refused.
 */
export function PortalProfilePage() {
  const { t } = useTranslation();
  const { data: customer, isLoading } = usePortalProfile();
  const save = useUpdatePortalProfile();
  const [form, setForm] = useState<CustomerProfileUpdate>(EMPTY);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!customer) return;
    setForm({
      first_name: customer.first_name,
      last_name: customer.last_name,
      phone_number: customer.phone_number,
      email: customer.email,
      address: {
        street: customer.address.street,
        postal_code: customer.address.postal_code,
        city: customer.address.city,
        country: customer.address.country,
      },
    });
  }, [customer]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSaved(false);
    setError(null);
    save.mutate(form, {
      onSuccess: () => setSaved(true),
      onError: (cause) =>
        setError(cause instanceof Error ? cause.message : t('common.error')),
    });
  };

  if (isLoading) return <Typography>{t('common.loading')}</Typography>;

  return (
    <Stack spacing={3} component="form" onSubmit={submit}>
      <Stack direction="row" spacing={2} alignItems="center">
        <Typography variant="h1" sx={{ flexGrow: 1 }}>
          {t('portal.myDetails')}
        </Typography>
        {customer ? (
          <CustomerStatusChip
            status={customer.registration_status}
            testId="portal-status"
          />
        ) : null}
      </Stack>

      {customer && !customer.address.latitude ? (
        <Alert severity="warning" data-testid="portal-address-unresolved">
          {t('portal.addressNotResolved')}
        </Alert>
      ) : null}

      {saved ? (
        <Alert severity="success" data-testid="portal-profile-saved">
          {t('portal.detailsSaved')}
        </Alert>
      ) : null}
      {error ? (
        <Alert severity="error" data-testid="portal-profile-error">
          {error}
        </Alert>
      ) : null}

      <Card>
        <CardContent>
          <Typography variant="h3" sx={{ mb: 2 }}>
            {t('customer.identity')}
          </Typography>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth
                required
                label={t('customer.firstName')}
                value={form.first_name}
                onChange={(event) =>
                  setForm({ ...form, first_name: event.target.value })
                }
                slotProps={{ htmlInput: { 'data-testid': 'portal-first-name' } }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth
                required
                label={t('customer.lastName')}
                value={form.last_name}
                onChange={(event) =>
                  setForm({ ...form, last_name: event.target.value })
                }
                slotProps={{ htmlInput: { 'data-testid': 'portal-last-name' } }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth
                required
                label={t('customer.phone')}
                value={form.phone_number}
                onChange={(event) =>
                  setForm({ ...form, phone_number: event.target.value })
                }
                slotProps={{ htmlInput: { 'data-testid': 'portal-phone' } }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth
                required
                type="email"
                label={t('customer.email')}
                value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })}
                slotProps={{ htmlInput: { 'data-testid': 'portal-email' } }}
              />
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h3">{t('customer.address')}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t('customer.addressIsRouted')}
          </Typography>
          <Grid container spacing={2}>
            <Grid size={12}>
              <TextField
                fullWidth
                required
                label={t('customer.street')}
                value={form.address.street}
                onChange={(event) =>
                  setForm({
                    ...form,
                    address: { ...form.address, street: event.target.value },
                  })
                }
                slotProps={{ htmlInput: { 'data-testid': 'portal-street' } }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                fullWidth
                required
                label={t('customer.postalCode')}
                value={form.address.postal_code}
                onChange={(event) =>
                  setForm({
                    ...form,
                    address: { ...form.address, postal_code: event.target.value },
                  })
                }
                slotProps={{ htmlInput: { 'data-testid': 'portal-postal-code' } }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                fullWidth
                required
                label={t('customer.city')}
                value={form.address.city}
                onChange={(event) =>
                  setForm({
                    ...form,
                    address: { ...form.address, city: event.target.value },
                  })
                }
                slotProps={{ htmlInput: { 'data-testid': 'portal-city' } }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                fullWidth
                required
                label={t('customer.country')}
                value={form.address.country}
                onChange={(event) =>
                  setForm({
                    ...form,
                    address: { ...form.address, country: event.target.value },
                  })
                }
                slotProps={{ htmlInput: { 'data-testid': 'portal-country' } }}
              />
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Stack direction="row" justifyContent="flex-end">
        <Button
          type="submit"
          variant="contained"
          disabled={save.isPending}
          data-testid="portal-save-profile"
        >
          {t('common.save')}
        </Button>
      </Stack>
    </Stack>
  );
}
