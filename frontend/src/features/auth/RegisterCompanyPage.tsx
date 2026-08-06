import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { ApiError, registerCompany } from '@/api/client';
import { useSession } from '@/store/session';
import logo from '@/assets/brand/logo-full.svg';

/** Shortest password the API accepts, mirrored so the field can say so. */
const MIN_PASSWORD_LENGTH = 12;

interface RegisterCompanyPageProps {
  /** Return to the sign-in card. */
  onCancel: () => void;
}

/**
 * The screen that founds an agency and its first administrator.
 *
 * @param props - How to get back to the sign-in card.
 * @returns The rendered page.
 *
 * @remarks
 * The founder is signed in immediately afterwards with the password they just
 * chose, rather than being returned to the sign-in card to type it again. The
 * API deliberately hands back no token — one place mints credentials — so the
 * sign-in is a second call made here.
 *
 * A deployment that has not opted in answers 404, and this says so plainly
 * instead of showing a generic failure: "not available here" is a different
 * fact from "something went wrong", and only one of them is worth retrying.
 */
export function RegisterCompanyPage({ onCancel }: RegisterCompanyPageProps) {
  const { t } = useTranslation();
  const signIn = useSession((state) => state.signIn);
  const [companyName, setCompanyName] = useState('');
  const [registrationNumber, setRegistrationNumber] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await registerCompany({
        company_name: companyName,
        // Sent as null rather than "" when left blank: absent and blank are
        // different, and the API refuses the blank one.
        registration_number: registrationNumber.trim() || null,
        full_name: fullName,
        email,
        password,
      });
      await signIn(email, password);
    } catch (cause) {
      setError(messageFor(cause, t));
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
      <Card sx={{ width: 460, maxWidth: '100%' }} data-testid="register-company-card">
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={3} component="form" onSubmit={submit}>
            <Box sx={{ textAlign: 'center' }}>
              <Box component="img" src={logo} alt="" sx={{ height: 40 }} />
            </Box>

            <Typography variant="h2">{t('company.registerTitle')}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t('company.registerIntro')}
            </Typography>

            {error ? (
              <Alert severity="error" data-testid="register-company-error">
                {error}
              </Alert>
            ) : null}

            <TextField
              label={t('company.name')}
              value={companyName}
              onChange={(event) => setCompanyName(event.target.value)}
              required
              autoFocus
              inputProps={{ 'data-testid': 'register-company-name' }}
            />
            <TextField
              label={t('company.registrationNumber')}
              helperText={t('company.registrationNumberHelp')}
              value={registrationNumber}
              onChange={(event) => setRegistrationNumber(event.target.value)}
              inputProps={{ 'data-testid': 'register-company-registration' }}
            />
            <TextField
              label={t('company.founderName')}
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              autoComplete="name"
              required
              inputProps={{ 'data-testid': 'register-company-founder' }}
            />
            <TextField
              label={t('auth.email')}
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              required
              inputProps={{ 'data-testid': 'register-company-email' }}
            />
            <TextField
              label={t('auth.password')}
              type="password"
              helperText={t('company.passwordHelp', { count: MIN_PASSWORD_LENGTH })}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              required
              inputProps={{
                'data-testid': 'register-company-password',
                minLength: MIN_PASSWORD_LENGTH,
              }}
            />

            <Button
              type="submit"
              variant="contained"
              size="large"
              disabled={busy}
              data-testid="register-company-submit"
            >
              {busy ? t('common.loading') : t('company.register')}
            </Button>

            <Typography variant="body2" sx={{ textAlign: 'center' }}>
              <Link
                component="button"
                type="button"
                onClick={onCancel}
                data-testid="register-company-cancel"
              >
                {t('company.backToSignIn')}
              </Link>
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}

/**
 * Turn a failure into something worth reading.
 *
 * @param cause - Whatever the call threw.
 * @param t - The translator.
 * @returns The message to show.
 *
 * @remarks
 * The three cases a founder can act on are told apart. A 404 means the
 * deployment does not offer this at all, and retrying will never help; a 409
 * names a clash they can fix by choosing again; a 422 means a field is wrong.
 * Collapsing them into one message would leave somebody retyping a valid form.
 */
function messageFor(cause: unknown, t: (key: string) => string): string {
  if (!(cause instanceof ApiError)) {
    return t('common.error');
  }
  if (cause.status === 404) {
    return t('company.registerUnavailable');
  }
  if (cause.status === 409) {
    return t('company.registerConflict');
  }
  if (cause.status === 422) {
    return t('company.registerInvalid');
  }
  return t('common.error');
}
