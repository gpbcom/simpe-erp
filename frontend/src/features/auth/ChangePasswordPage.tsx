import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { ApiError, request } from '@/api/client';
import { useSession } from '@/store/session';

/**
 * The forced password change.
 *
 * @returns The rendered page.
 *
 * @remarks
 * Reached when the account carries `must_change_password`. The server answers
 * **403 on every other route** while that flag is set, so this is not a
 * suggestion — nothing else in the application works until it is done.
 */
export function ChangePasswordPage() {
  const { t } = useTranslation();
  const refresh = useSession((state) => state.refresh);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await request('/api/v1/auth/password', {
        method: 'POST',
        json: { current_password: current, new_password: next },
      });
      await refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        bgcolor: 'background.default',
        p: 2,
      }}
    >
      <Card sx={{ width: 420, maxWidth: '100%' }}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={3} component="form" onSubmit={submit}>
            <Typography variant="h2">{t('auth.changePassword')}</Typography>
            <Alert severity="info">{t('auth.mustChangePassword')}</Alert>
            {error ? (
              <Alert severity="error" data-testid="password-error">
                {error}
              </Alert>
            ) : null}
            <TextField
              label={t('auth.currentPassword')}
              type="password"
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
              autoComplete="current-password"
              required
              inputProps={{ 'data-testid': 'current-password' }}
            />
            <TextField
              label={t('auth.newPassword')}
              type="password"
              value={next}
              onChange={(event) => setNext(event.target.value)}
              autoComplete="new-password"
              required
              inputProps={{ 'data-testid': 'new-password' }}
            />
            <Button
              type="submit"
              variant="contained"
              disabled={busy}
              data-testid="password-submit"
            >
              {t('common.save')}
            </Button>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
