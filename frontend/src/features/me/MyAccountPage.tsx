import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Avatar from '@mui/material/Avatar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Divider from '@mui/material/Divider';
import Grid from '@mui/material/Grid2';
import Snackbar from '@mui/material/Snackbar';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import PhotoCameraIcon from '@mui/icons-material/PhotoCamera';
import {
  useMyAccount,
  useMyProfile,
  useRemoveMyAccountPhoto,
  useUpdateMyProfile,
  useUploadMyAccountPhoto,
} from '@/api/queries';
import { AbsencesSection } from './AbsencesSection';
import { WorkingDaysSection } from './WorkingDaysSection';
import { AccountSection } from './AccountSection';
import { EmploymentSection } from './EmploymentSection';
import { SkillsSection } from './SkillsSection';
import { PasswordSection } from './PasswordSection';
import { formatDateTime, initialsOf } from '@/utils/format';
import { hasAtLeast, useSession } from '@/store/session';

const LICENCE_CATEGORIES = ['A', 'A1', 'A2', 'B', 'B1', 'BE', 'C', 'D'];
interface ProfileForm {
  first_name: string;
  last_name: string;
  phone_number: string;
  email: string;
  street: string;
  postal_code: string;
  city: string;
  country: string;
  licence_categories: string;
  licence_number: string;
  licence_obtained_on: string;
  licence_expires_on: string;
}

const EMPTY: ProfileForm = {
  first_name: '',
  last_name: '',
  phone_number: '',
  email: '',
  street: '',
  postal_code: '',
  city: '',
  country: 'France',
  licence_categories: '',
  licence_number: '',
  licence_obtained_on: '',
  licence_expires_on: '',
};

/**
 * The caller's own record: everything the system holds about them.
 *
 * @returns The rendered page.
 *
 * @remarks
 * **Every field is shown.** An account page that displays a subset leaves the
 * holder unable to answer "what does this system say about me?" — which is the
 * question it exists to answer, and one they have a right to.
 *
 * Everything is editable **except the ones an assistant does not own**:
 *
 * | Field | Who owns it |
 * |---|---|
 * | Contract type | A manager, via `PATCH /api/v1/hcas/{id}/employment` |
 * | Qualifications | A manager, same route |
 * | Role (position) | An administrator, via `POST /api/v1/users/{id}/promote` |
 *
 * A manager viewing their own record gets the first two as editable fields,
 * because they are the person who would set them. The role stays read-only for
 * everybody here: promoting is an administrator's act performed on the accounts
 * screen, and a page where somebody could raise their own rank is a page with
 * no rank at all.
 *
 * The screen decides what to *offer*; the server decides what it will *accept*.
 * The self-service payload has no `contract_type`, `certifications` or `role`
 * field at all, so a manager's edits go through the manager-gated route rather
 * than widening it. Neither check depends on the other.
 */
export function MyAccountPage() {
  const { t, i18n } = useTranslation();
  const user = useSession((state) => state.user);
  const { data: account, isLoading, isError } = useMyAccount();
  const { data: profile } = useMyProfile(account?.hca_id);
  const update = useUpdateMyProfile();
  const uploadPhoto = useUploadMyAccountPhoto();
  const removePhoto = useRemoveMyAccountPhoto();
  const fileInput = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState<ProfileForm>(EMPTY);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const managesEmployment = hasAtLeast(user?.role, 'manager');

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
      country: profile.address.country,
      licence_categories: (profile.driving_license?.categories ?? []).join(', '),
      licence_number: profile.driving_license?.number ?? '',
      licence_obtained_on: profile.driving_license?.obtained_on ?? '',
      licence_expires_on: profile.driving_license?.expires_on ?? '',
    });
  }, [profile]);

  const field = (key: keyof ProfileForm, label: string, extra = {}) => (
    <TextField
      label={label}
      value={form[key]}
      onChange={(event) => setForm({ ...form, [key]: event.target.value })}
      inputProps={{ 'data-testid': `profile-${key.replace(/_/g, '-')}` }}
      {...extra}
    />
  );

  const save = () => {
    setError(null);
    const categories = form.licence_categories
      .split(',')
      .map((entry) => entry.trim().toUpperCase())
      .filter(Boolean);
    update.mutate(
      {
        first_name: form.first_name,
        last_name: form.last_name,
        phone_number: form.phone_number,
        email: form.email,
        address: {
          street: form.street,
          postal_code: form.postal_code,
          city: form.city,
          country: form.country,
        },
        driving_license: categories.length
          ? {
              categories,
              number: form.licence_number || null,
              obtained_on: form.licence_obtained_on || null,
              expires_on: form.licence_expires_on || null,
            }
          : null,
      },
      {
        onSuccess: () => setSaved(true),
        onError: (cause) =>
          setError(cause instanceof Error ? cause.message : t('common.error')),
      },
    );
  };

  if (isLoading) return <Typography>{t('common.loading')}</Typography>;
  if (isError || !account) {
    return <Alert severity="error">{t('common.error')}</Alert>;
  }

  const fullName = profile
    ? `${profile.first_name} ${profile.last_name}`
    : account.full_name;
  const geocoded =
    !profile ||
    (profile.address.latitude !== null && profile.address.longitude !== null);

  return (
    <Stack spacing={3}>
      <Typography variant="h1">{t('nav.myAccount')}</Typography>

      {error ? <Alert severity="error">{error}</Alert> : null}
      {!geocoded ? (
        <Alert severity="warning" data-testid="geocoding-warning">
          {t('hca.addressNotResolved')}
        </Alert>
      ) : null}

      {/* ── The account: every caller has one ────────────────────── */}
      <Grid container spacing={3}>
        {}
        <Grid size={{ xs: 12, md: 3 }}>
          <Card>
            <CardContent sx={{ textAlign: 'center' }}>
              <Avatar
                src={account.photo_url ?? undefined}
                sx={{ width: 112, height: 112, mx: 'auto', mb: 2, fontSize: 36 }}
                data-testid="profile-avatar"
              >
                {initialsOf(fullName)}
              </Avatar>
              <Typography variant="h3">{fullName}</Typography>

              <input
                ref={fileInput}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                hidden
                data-testid="photo-input"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) uploadPhoto.mutate(file);
                  event.target.value = '';
                }}
              />
              <Stack direction="row" spacing={1} sx={{ mt: 2 }} justifyContent="center">
                <Button
                  size="small"
                  startIcon={<PhotoCameraIcon />}
                  onClick={() => fileInput.current?.click()}
                  disabled={uploadPhoto.isPending}
                  data-testid="upload-photo"
                >
                  {t('account.changePhoto')}
                </Button>
                {account.photo_url ? (
                  <Button
                    size="small"
                    color="inherit"
                    onClick={() => removePhoto.mutate()}
                    disabled={removePhoto.isPending}
                    data-testid="remove-photo"
                  >
                    {t('common.remove')}
                  </Button>
                ) : null}
              </Stack>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ mt: 1, display: 'block' }}
              >
                {profile ? t('hca.photoIsYourPin') : t('account.photoExplained')}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <AccountSection account={account} />
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <PasswordSection />
        </Grid>
      </Grid>

      {/* ── The assistant record: only somebody scheduled has one ── */}
      {!profile ? (
        <Alert severity="info" data-testid="no-assistant-record">
          {t('account.noAssistantRecordExplained')}
        </Alert>
      ) : (
        <Grid container spacing={3}>
          {/* ── The assistant's own record ───────────────────────────── */}
          <Grid size={{ xs: 12, md: 4 }}>
            <Stack spacing={3}>
              <Card data-testid="record-section">
                <CardContent>
                  <Stack spacing={1.5}>
                    <Typography variant="h3">{t('hca.record')}</Typography>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        {t('hca.recordCreated')}
                      </Typography>
                      <Typography variant="body2" data-testid="record-created">
                        {formatDateTime(profile.created_at, i18n.language)}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        {t('hca.recordUpdated')}
                      </Typography>
                      <Typography variant="body2" data-testid="record-updated">
                        {formatDateTime(profile.updated_at, i18n.language)}
                      </Typography>
                    </Box>
                  </Stack>
                </CardContent>
              </Card>
            </Stack>
          </Grid>

          {/* ── Everything the assistant owns ───────────────────────── */}
          <Grid size={{ xs: 12, md: 8 }}>
            <Stack spacing={3}>
              <Card>
                <CardContent>
                  <Stack spacing={2}>
                    <Typography variant="h3">{t('hca.identity')}</Typography>
                    <Grid container spacing={2}>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        {field('first_name', t('hca.firstName'))}
                      </Grid>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        {field('last_name', t('hca.lastName'))}
                      </Grid>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        {field('phone_number', t('hca.phone'))}
                      </Grid>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        {field('email', t('hca.email'))}
                      </Grid>
                    </Grid>

                    <Divider />

                    <Typography variant="h3">{t('hca.address')}</Typography>
                    <Grid container spacing={2}>
                      <Grid size={12}>{field('street', t('hca.street'))}</Grid>
                      <Grid size={{ xs: 12, sm: 4 }}>
                        {field('postal_code', t('hca.postalCode'))}
                      </Grid>
                      <Grid size={{ xs: 12, sm: 4 }}>
                        {field('city', t('hca.city'))}
                      </Grid>
                      <Grid size={{ xs: 12, sm: 4 }}>
                        {field('country', t('hca.country'))}
                      </Grid>
                    </Grid>

                    <Divider />

                    <Typography variant="h3">{t('hca.drivingLicense')}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {t('hca.licenceAffectsRouting')}
                    </Typography>
                    <Grid container spacing={2}>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        {field('licence_categories', t('hca.licenceCategories'), {
                          helperText: LICENCE_CATEGORIES.join(' · '),
                        })}
                      </Grid>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        {field('licence_number', t('hca.licenceNumber'))}
                      </Grid>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        {field('licence_obtained_on', t('hca.licenceObtained'), {
                          type: 'date',
                          InputLabelProps: { shrink: true },
                        })}
                      </Grid>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        {field('licence_expires_on', t('hca.licenceExpires'), {
                          type: 'date',
                          InputLabelProps: { shrink: true },
                        })}
                      </Grid>
                    </Grid>

                    <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
                      <Button
                        variant="contained"
                        onClick={save}
                        disabled={update.isPending}
                        data-testid="profile-save"
                      >
                        {t('common.save')}
                      </Button>
                    </Box>
                  </Stack>
                </CardContent>
              </Card>

              <EmploymentSection profile={profile} editable={managesEmployment} />

              <SkillsSection profile={profile} />

              <WorkingDaysSection profile={profile} />

              <AbsencesSection profile={profile} />
            </Stack>
          </Grid>
        </Grid>
      )}

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
