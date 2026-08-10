import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useCreateCustomer } from '@/api/queries';
import type { Customer } from '@/api/types';

/** Everything the form collects, flattened for the inputs. */
interface CustomerForm {
  first_name: string;
  last_name: string;
  phone_number: string;
  email: string;
  street: string;
  postal_code: string;
  city: string;
  country: string;
}

const EMPTY: CustomerForm = {
  first_name: '',
  last_name: '',
  phone_number: '',
  email: '',
  street: '',
  postal_code: '',
  city: '',
  country: 'France',
};

interface CustomerDialogProps {
  /** Whether the dialog is open. */
  open: boolean;
  /** Called when it should close. */
  onClose: () => void;
  /** Called with the stored customer once the server has taken it. */
  onCreated?: (customer: Customer) => void;
}

/**
 * Register somebody the agency will care for.
 *
 * @param props - Whether it is open, and what to do when it closes or succeeds.
 * @returns The rendered dialog.
 *
 * @remarks
 * **Every field is required**, which is unusual for a form and deliberate here.
 * A customer with no address cannot be routed to, and a customer with no
 * telephone number cannot be reached when an assistant is running late — so a
 * record missing either is one somebody has to chase later, from a screen that
 * gave no sign anything was missing.
 *
 * The address is typed as four plain fields with **no coordinate**. Geocoding
 * happens server-side while the payload is validated, so a home the map does not
 * know is still registered, with the failure recorded on the address. That is
 * why the dialog closes on success rather than reporting "not found": the
 * customer exists, and the warning about routing belongs on their file.
 *
 * A new customer is always **active**. Registering somebody the agency is not
 * going to serve is not a case worth a control; stopping them later is one
 * click on their file.
 */
export function CustomerDialog({ open, onClose, onCreated }: CustomerDialogProps) {
  const { t } = useTranslation();
  const create = useCreateCustomer();
  const [form, setForm] = useState<CustomerForm>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setForm({ ...EMPTY });
  }, [open]);

  const emailLooksValid = /.+@.+\..+/.test(form.email.trim());
  const valid =
    Boolean(form.first_name.trim()) &&
    Boolean(form.last_name.trim()) &&
    Boolean(form.phone_number.trim()) &&
    emailLooksValid &&
    Boolean(form.street.trim()) &&
    Boolean(form.postal_code.trim()) &&
    Boolean(form.city.trim()) &&
    Boolean(form.country.trim());

  const field = (key: keyof CustomerForm, label: string) => (
    <TextField
      label={label}
      value={form[key]}
      onChange={(event) => setForm({ ...form, [key]: event.target.value })}
      inputProps={{ 'data-testid': `customer-${key.replace(/_/g, '-')}` }}
    />
  );

  const save = () => {
    setError(null);
    create.mutate(
      {
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        phone_number: form.phone_number.trim(),
        email: form.email.trim(),
        address: {
          street: form.street.trim(),
          postal_code: form.postal_code.trim(),
          city: form.city.trim(),
          country: form.country.trim(),
        },
        // A newly registered household is a prospect, not a customer. They
        // may be quoted straight away — that is what the next screen is for —
        // but nothing is scheduled for them until a manager promotes them.
        registration_status: 'prospect',
      },
      {
        onSuccess: (customer) => {
          onCreated?.(customer);
          onClose();
        },
        onError: (cause) =>
          setError(cause instanceof Error ? cause.message : t('common.error')),
      },
    );
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      data-testid="customer-dialog"
    >
      <DialogTitle>{t('customer.add')}</DialogTitle>

      <DialogContent dividers>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? (
            <Alert severity="error" data-testid="customer-dialog-error">
              {error}
            </Alert>
          ) : null}

          <Typography variant="h3">{t('customer.identity')}</Typography>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6 }}>
              {field('first_name', t('customer.firstName'))}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              {field('last_name', t('customer.lastName'))}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              {field('phone_number', t('customer.phone'))}
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>{field('email', t('customer.email'))}</Grid>
          </Grid>

          <Divider />

          <Typography variant="h3">{t('customer.address')}</Typography>
          <Typography variant="caption" color="text.secondary">
            {t('customer.addressIsRouted')}
          </Typography>
          <Grid container spacing={2}>
            <Grid size={12}>{field('street', t('customer.street'))}</Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              {field('postal_code', t('customer.postalCode'))}
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>{field('city', t('customer.city'))}</Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              {field('country', t('customer.country'))}
            </Grid>
          </Grid>
        </Stack>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2 }}>
        <Box sx={{ flexGrow: 1 }} />
        <Button onClick={onClose} data-testid="cancel-customer">
          {t('common.cancel')}
        </Button>
        <Button
          variant="contained"
          onClick={save}
          disabled={!valid || create.isPending}
          data-testid="save-customer"
        >
          {t('common.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
