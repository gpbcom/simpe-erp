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
import { ApiError } from '@/api/client';
import { useSession } from '@/store/session';
import logo from '@/assets/brand/logo-full.svg';

/**
 * The sign-in screen.
 *
 * @returns The rendered page.
 */
export function LoginPage() {
  const { t } = useTranslation();
  const signIn = useSession((state) => state.signIn);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await signIn(email, password);
    } catch (cause) {
      // The API answers the same 401 whether the address is unknown or the
      // password is wrong, so this message must not try to be more specific
      // than that — guessing would undo the server's care not to be an
      // account-enumeration oracle.
      setError(
        cause instanceof ApiError && cause.status === 401
          ? t('auth.invalidCredentials')
          : t('common.error'),
      );
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
      <Card sx={{ width: 400, maxWidth: '100%' }}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={3} component="form" onSubmit={submit}>
            <Box sx={{ textAlign: 'center' }}>
              <Box component="img" src={logo} alt="" sx={{ height: 40 }} />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                {t('app.tagline')}
              </Typography>
            </Box>

            <Typography variant="h2">{t('auth.signInTitle')}</Typography>

            {error ? (
              <Alert severity="error" data-testid="login-error">
                {error}
              </Alert>
            ) : null}

            <TextField
              label={t('auth.email')}
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              required
              autoFocus
              inputProps={{ 'data-testid': 'login-email' }}
            />
            <TextField
              label={t('auth.password')}
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
              inputProps={{ 'data-testid': 'login-password' }}
            />
            <Button
              type="submit"
              variant="contained"
              size="large"
              disabled={busy}
              data-testid="login-submit"
            >
              {busy ? t('common.loading') : t('auth.signIn')}
            </Button>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
