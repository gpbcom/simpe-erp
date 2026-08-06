import { useState } from 'react';
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

/**
 * Replacing the account's own password.
 *
 * @returns The rendered section.
 *
 * @remarks
 * **The current password is asked for even though the caller is signed in.**
 * The server demands it, and the reason is worth repeating on screen: a session
 * left open on a shared machine is exactly the situation where somebody else
 * would change the password, and knowing the old one is what tells the holder
 * apart from whoever found the browser.
 *
 * The confirmation field is the client's own, not the server's. Its only job is
 * to catch a typo before it becomes a credential nobody knows — the server has
 * no way to tell a mistyped new password from an intended one.
 */
export function PasswordSection() {
  const { t } = useTranslation();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mismatch = confirm.length > 0 && next !== confirm;
  const ready = Boolean(current) && Boolean(next) && next === confirm && !busy;

  const submit = async () => {
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      await request('/api/v1/auth/password', {
        method: 'POST',
        json: { current_password: current, new_password: next },
      });
      setCurrent('');
      setNext('');
      setConfirm('');
      setDone(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card data-testid="password-section">
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h3">{t('account.password')}</Typography>

          {error ? (
            <Alert severity="error" data-testid="password-section-error">
              {error}
            </Alert>
          ) : null}
          {done ? (
            <Alert severity="success" data-testid="password-section-saved">
              {t('account.passwordChanged')}
            </Alert>
          ) : null}

          <TextField
            type="password"
            label={t('account.currentPassword')}
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            helperText={t('account.currentPasswordHint')}
            inputProps={{ 'data-testid': 'account-current-password' }}
          />
          <TextField
            type="password"
            label={t('account.newPassword')}
            value={next}
            onChange={(event) => setNext(event.target.value)}
            inputProps={{ 'data-testid': 'account-new-password' }}
          />
          <TextField
            type="password"
            label={t('account.confirmPassword')}
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            error={mismatch}
            helperText={mismatch ? t('account.passwordMismatch') : ' '}
            inputProps={{ 'data-testid': 'account-confirm-password' }}
          />

          <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              variant="contained"
              disabled={!ready}
              onClick={() => void submit()}
              data-testid="save-password"
            >
              {t('account.changePassword')}
            </Button>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}
