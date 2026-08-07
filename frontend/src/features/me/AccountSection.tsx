import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import LockIcon from '@mui/icons-material/Lock';
import { useUpdateMyAccount } from '@/api/queries';
import { formatDateTime } from '@/utils/format';
import type { User } from '@/api/types';

interface AccountSectionProps {
  /** The account behind the credential. */
  account: User;
}

/**
 * The account itself: what signs in, and what the system records about it.
 *
 * @param props - The account to show.
 * @returns The rendered section.
 *
 * @remarks
 * **Every account has one**, which is the point. The rest of this screen
 * describes an *assistant record* — a person a manager schedules — and a
 * manager or an administrator has none. This section is what they see, and
 * before it existed they saw an error page instead of their own details.
 *
 * Two fields are editable, and they are the two the holder owns:
 *
 * | Field | Why it is here |
 * |---|---|
 * | Display name | What a colleague reads beside every quote they write |
 * | Sign-in address | What they type to get in, and where their mail goes |
 *
 * Everything else is shown but **not** editable, each for its own reason:
 *
 * | Field | Who owns it |
 * |---|---|
 * | Position | An administrator, on the workforce screen |
 * | Sign-in permitted | An administrator; self-service would let somebody lock themselves out of the only screen that could undo it |
 * | Agency | Fixed when the account was created; changing it would move somebody between agencies' data |
 * | Assistant record | The binding a manager makes when granting an account |
 * | Created, updated | Records of what happened, not settings |
 *
 * They are **shown rather than hidden**. An account page that omits what it
 * will not let you change answers "what does this system say about me?" with
 * silence, which is the question it exists to answer.
 */
export function AccountSection({ account }: AccountSectionProps) {
  const { t, i18n } = useTranslation();
  const update = useUpdateMyAccount();
  const [fullName, setFullName] = useState(account.full_name);
  const [email, setEmail] = useState(account.email);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setFullName(account.full_name);
    setEmail(account.email);
  }, [account]);

  const dirty = fullName !== account.full_name || email !== account.email;
  const valid = Boolean(fullName.trim()) && /.+@.+\..+/.test(email.trim());

  const save = () => {
    setError(null);
    setSaved(false);
    update.mutate(
      // The language is sent back unchanged. The payload replaces the whole
      // account, so omitting it would reset the holder's preference to French
      // every time they corrected a typo in their name.
      { full_name: fullName.trim(), email: email.trim(), language: account.language },
      {
        onSuccess: () => setSaved(true),
        onError: (cause) =>
          setError(cause instanceof Error ? cause.message : t('common.error')),
      },
    );
  };

  /** A value the holder may read but not set, with the reason attached. */
  const locked = (label: string, value: string, why: string, testId: string) => (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Box sx={{ mt: 0.5 }}>
        <Tooltip title={why}>
          <Chip icon={<LockIcon />} label={value} data-testid={testId} />
        </Tooltip>
      </Box>
    </Box>
  );

  return (
    <Card data-testid="account-section">
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h3">{t('account.title')}</Typography>

          {error ? (
            <Alert severity="error" data-testid="account-error">
              {error}
            </Alert>
          ) : null}
          {saved ? (
            <Alert severity="success" data-testid="account-saved">
              {t('common.saved')}
            </Alert>
          ) : null}

          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                label={t('account.fullName')}
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                inputProps={{ 'data-testid': 'account-full-name' }}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                label={t('account.email')}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                helperText={t('account.emailHint')}
                inputProps={{ 'data-testid': 'account-email' }}
              />
            </Grid>
          </Grid>

          <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              variant="contained"
              disabled={!dirty || !valid || update.isPending}
              onClick={save}
              data-testid="save-account"
            >
              {t('common.save')}
            </Button>
          </Box>

          <Divider />

          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              {locked(
                t('account.position'),
                t(`role.${account.role}`),
                t('account.positionLocked'),
                'account-role',
              )}
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              {locked(
                t('account.signInPermitted'),
                account.is_active ? t('common.yes') : t('common.no'),
                t('account.activeLocked'),
                'account-active',
              )}
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              {locked(
                t('account.assistantRecord'),
                account.hca_id ?? t('account.noAssistantRecord'),
                t('account.assistantRecordLocked'),
                'account-hca-id',
              )}
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              {locked(
                t('account.agency'),
                account.company_id ?? '—',
                t('account.agencyLocked'),
                'account-company',
              )}
            </Grid>
          </Grid>

          <Typography variant="caption" color="text.secondary">
            {t('account.created')}: {formatDateTime(account.created_at, i18n.language)}
            {' · '}
            {t('account.updated')}: {formatDateTime(account.updated_at, i18n.language)}
          </Typography>
        </Stack>
      </CardContent>
    </Card>
  );
}
