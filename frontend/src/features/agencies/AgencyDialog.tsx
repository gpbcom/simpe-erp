import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Grid from '@mui/material/Grid2';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useCreateAgency, useDeleteAgency, useUpdateAgency } from '@/api/queries';
import type { Agency, AgencyType } from '@/api/types';

interface AgencyForm {
  name: string;
  agency_type: AgencyType;
  street: string;
  postal_code: string;
  city: string;
  country: string;
}

const EMPTY: AgencyForm = {
  name: '',
  agency_type: 'office',
  street: '',
  postal_code: '',
  city: '',
  country: 'France',
};

const TYPES: AgencyType[] = ['hq', 'warehouse', 'office'];

interface AgencyDialogProps {
  agency: Agency | null;
  creating: boolean;
  onClose: () => void;
}

/**
 * Open a site, or change what an existing one says.
 *
 * @param props - The site, the mode and the close handler.
 * @returns The rendered dialog.
 *
 * @remarks
 * **The address is optional, and deliberately so.** Founding a company asks for
 * no address, so the head office created alongside it can have none either. The
 * consequence is worth knowing rather than hiding: a site with no coordinate
 * can never win a "closest team" contest, and its teams are reachable only
 * through the busyness tie-break.
 *
 * **The type is a request, not a decision.** The first site of a company is its
 * head office whatever the form said, and a second head office is refused —
 * both are questions about *other rows*, which no form can answer about itself.
 * The hint under the field says so, because a value that silently changes on
 * save reads as a bug.
 *
 * Deleting is offered here and usually refused: the server counts the teams and
 * the people still attached and answers 409 naming both. The message is shown
 * verbatim, because it already says which screen to go and empty first.
 */
export function AgencyDialog({ agency, creating, onClose }: AgencyDialogProps) {
  const { t } = useTranslation();
  const [form, setForm] = useState<AgencyForm>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const createAgency = useCreateAgency();
  const updateAgency = useUpdateAgency();
  const deleteAgency = useDeleteAgency();
  const open = Boolean(agency) || creating;

  useEffect(() => {
    setError(null);
    if (agency) {
      setForm({
        name: agency.name,
        agency_type: agency.agency_type,
        street: agency.address?.street ?? '',
        postal_code: agency.address?.postal_code ?? '',
        city: agency.address?.city ?? '',
        country: agency.address?.country ?? 'France',
      });
      return;
    }
    setForm(EMPTY);
  }, [agency, creating]);

  const submit = async () => {
    setError(null);
    const address = form.street.trim()
      ? {
          street: form.street.trim(),
          postal_code: form.postal_code.trim(),
          city: form.city.trim(),
          country: form.country.trim() || 'France',
          latitude: null,
          longitude: null,
          geocoding_error: null,
        }
      : null;
    const body = { name: form.name.trim(), agency_type: form.agency_type, address };
    try {
      if (agency?.id) {
        await updateAgency.mutateAsync({ id: agency.id, body });
      } else {
        await createAgency.mutateAsync(body);
      }
      onClose();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  const remove = async () => {
    if (!agency?.id) return;
    setError(null);
    try {
      await deleteAgency.mutateAsync(agency.id);
      onClose();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t(agency ? 'agencies.edit' : 'agencies.create')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? (
            <Alert severity="error" data-testid="agency-dialog-error">
              {error}
            </Alert>
          ) : null}
          <TextField
            label={t('agencies.name')}
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            slotProps={{ htmlInput: { 'data-testid': 'agency-name' } }}
            fullWidth
          />
          <TextField
            select
            label={t('agencies.type')}
            value={form.agency_type}
            helperText={t('agencies.typeHint')}
            onChange={(event) =>
              setForm({ ...form, agency_type: event.target.value as AgencyType })
            }
            slotProps={{ htmlInput: { 'data-testid': 'agency-type' } }}
            fullWidth
          >
            {TYPES.map((type) => (
              <MenuItem key={type} value={type} data-testid={`agency-type-${type}`}>
                {t(`agencyType.${type}`)}
              </MenuItem>
            ))}
          </TextField>
          <Grid container spacing={2}>
            <Grid size={12}>
              <TextField
                label={t('agencies.address')}
                value={form.street}
                onChange={(event) => setForm({ ...form, street: event.target.value })}
                slotProps={{ htmlInput: { 'data-testid': 'agency-street' } }}
                fullWidth
              />
            </Grid>
            <Grid size={4}>
              <TextField
                label={t('customer.postalCode')}
                value={form.postal_code}
                onChange={(event) =>
                  setForm({ ...form, postal_code: event.target.value })
                }
                slotProps={{ htmlInput: { 'data-testid': 'agency-postal-code' } }}
                fullWidth
              />
            </Grid>
            <Grid size={8}>
              <TextField
                label={t('customer.city')}
                value={form.city}
                onChange={(event) => setForm({ ...form, city: event.target.value })}
                slotProps={{ htmlInput: { 'data-testid': 'agency-city' } }}
                fullWidth
              />
            </Grid>
          </Grid>
        </Stack>
      </DialogContent>
      <DialogActions>
        {agency?.id ? (
          <Button color="error" onClick={remove} data-testid="delete-agency">
            {t('agencies.delete')}
          </Button>
        ) : null}
        <Button onClick={onClose} data-testid="agency-cancel">
          {t('common.cancel')}
        </Button>
        <Button
          variant="contained"
          onClick={submit}
          disabled={!form.name.trim()}
          data-testid="agency-save"
        >
          {t('common.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
