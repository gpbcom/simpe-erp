import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import Alert from '@mui/material/Alert';
import Avatar from '@mui/material/Avatar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import Grid from '@mui/material/Grid2';
import Snackbar from '@mui/material/Snackbar';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import LockIcon from '@mui/icons-material/Lock';
import { request } from '@/api/client';
import { keys, useMyProfile } from '@/api/queries';
import { AppIcon } from '@/components/icons/AppIcon';
import { initialsOf } from '@/utils/format';

/**
 * An assistant's own record: what they may change, and what they may not.
 *
 * @returns The rendered page.
 *
 * @remarks
 * The contract type and the qualifications render as **locked chips with an
 * explanation**, not as disabled inputs. A disabled input says "you cannot type
 * here"; a locked chip with "set by your manager" says who to ask. The
 * distinction matters because these are the two fields an assistant most often
 * wants to correct.
 */
export function MyAccountPage() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const { data: profile, isLoading } = useMyProfile();
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    phone_number: '',
    email: '',
    street: '',
    postal_code: '',
    city: '',
  });
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!profile) return;
    setForm({
      first_name: profile.first_name,
      last_name: profile.last_name,
      phone_number: profile.phone_number,
      email: profile.email,
      street: profile.address.street,
      postal_code: profile.address.postal_code,
      city: profile.address.city,
    });
  }, [profile]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await request('/api/v1/me/hca', {
        method: 'PATCH',
        json: {
          first_name: form.first_name,
          last_name: form.last_name,
          phone_number: form.phone_number,
          email: form.email,
          address: {
            street: form.street,
            postal_code: form.postal_code,
            city: form.city,
            country: 'France',
          },
        },
      });
      await client.invalidateQueries({ queryKey: keys.myProfile });
      setSaved(true);
    } catch {
      setError(t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  if (isLoading || !profile) {
    return <Typography>{t('common.loading')}</Typography>;
  }

  const fullName = `${profile.first_name} ${profile.last_name}`;

  return (
    <Stack spacing={3}>
      <Typography variant="h1">{t('nav.myAccount')}</Typography>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Card>
            <CardContent sx={{ textAlign: 'center' }}>
              <Avatar
                src={profile.photo_url ?? undefined}
                sx={{ width: 96, height: 96, mx: 'auto', mb: 2, fontSize: 32 }}
                data-testid="profile-avatar"
              >
                {initialsOf(fullName)}
              </Avatar>
              <Typography variant="h3">{fullName}</Typography>

              <Stack spacing={2} sx={{ mt: 3, textAlign: 'left' }}>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {t('hca.contractType')}
                  </Typography>
                  <Box sx={{ mt: 0.5 }}>
                    <Tooltip title={t('hca.managedByManager')}>
                      <Chip
                        icon={<LockIcon />}
                        label={t(`hca.contract_${profile.contract_type}`)}
                        data-testid="contract-type"
                      />
                    </Tooltip>
                  </Box>
                </Box>

                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {t('hca.certifications')}
                  </Typography>
                  <Box
                    sx={{ mt: 0.5, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}
                    data-testid="certifications"
                  >
                    {profile.certifications.length === 0 ? (
                      <Typography variant="body2" color="text.secondary">
                        —
                      </Typography>
                    ) : (
                      profile.certifications.map((certification) => (
                        <Tooltip
                          key={certification.name}
                          title={t('hca.managedByManager')}
                        >
                          <Chip
                            icon={<AppIcon name="certification" />}
                            label={certification.name}
                          />
                        </Tooltip>
                      ))
                    )}
                  </Box>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 8 }}>
          <Card>
            <CardContent>
              <Stack spacing={2}>
                {error ? <Alert severity="error">{error}</Alert> : null}
                <Grid container spacing={2}>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      label={t('hca.firstName')}
                      value={form.first_name}
                      onChange={(event) =>
                        setForm({ ...form, first_name: event.target.value })
                      }
                      inputProps={{ 'data-testid': 'profile-first-name' }}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      label={t('hca.lastName')}
                      value={form.last_name}
                      onChange={(event) =>
                        setForm({ ...form, last_name: event.target.value })
                      }
                      inputProps={{ 'data-testid': 'profile-last-name' }}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      label={t('hca.phone')}
                      value={form.phone_number}
                      onChange={(event) =>
                        setForm({ ...form, phone_number: event.target.value })
                      }
                      inputProps={{ 'data-testid': 'profile-phone' }}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <TextField
                      label={t('hca.email')}
                      value={form.email}
                      onChange={(event) =>
                        setForm({ ...form, email: event.target.value })
                      }
                      inputProps={{ 'data-testid': 'profile-email' }}
                    />
                  </Grid>
                  <Grid size={12}>
                    <TextField
                      label={t('hca.address')}
                      value={form.street}
                      onChange={(event) =>
                        setForm({ ...form, street: event.target.value })
                      }
                      inputProps={{ 'data-testid': 'profile-street' }}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, sm: 4 }}>
                    <TextField
                      label="Code postal"
                      value={form.postal_code}
                      onChange={(event) =>
                        setForm({ ...form, postal_code: event.target.value })
                      }
                      inputProps={{ 'data-testid': 'profile-postal-code' }}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, sm: 8 }}>
                    <TextField
                      label="Ville"
                      value={form.city}
                      onChange={(event) =>
                        setForm({ ...form, city: event.target.value })
                      }
                      inputProps={{ 'data-testid': 'profile-city' }}
                    />
                  </Grid>
                </Grid>
                <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <Button
                    variant="contained"
                    onClick={save}
                    disabled={busy}
                    data-testid="profile-save"
                  >
                    {t('common.save')}
                  </Button>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Snackbar
        open={saved}
        autoHideDuration={4000}
        onClose={() => setSaved(false)}
        message={t('common.saved')}
        data-testid="profile-saved"
      />
    </Stack>
  );
}
