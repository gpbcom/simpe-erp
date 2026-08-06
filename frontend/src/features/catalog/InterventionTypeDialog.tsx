import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useCreateInterventionType, useUpdateInterventionType } from '@/api/queries';
import type { InterventionType } from '@/api/types';

/** Everything the form edits, flattened for the inputs. */
interface TypeForm {
  code: string;
  name: string;
  description: string;
  service_category: 'necessity' | 'comfort';
  base_hourly_rate_ht: string;
  is_active: boolean;
}

const EMPTY: TypeForm = {
  code: '',
  name: '',
  description: '',
  service_category: 'necessity',
  base_hourly_rate_ht: '',
  is_active: true,
};

interface InterventionTypeDialogProps {
  /** The entry to edit, or `null` when not editing one. */
  entry: InterventionType | null;
  /** Whether the dialog is open to create a new entry instead. */
  creating: boolean;
  /** The rate an entry falls back to, for the hint. */
  agencyRate: string | null;
  /** Called when the dialog should close. */
  onClose: () => void;
}

/**
 * Add a service to the catalogue, or change what an existing one costs.
 *
 * @param props - The entry, the mode, the fallback rate and the close handler.
 * @returns The rendered dialog.
 *
 * @remarks
 * One dialog for both creating and editing, because the fields are the same and
 * two would be two places for the pricing rules to drift. What differs is
 * whether `code` can be typed.
 *
 * **`code` is fixed once an entry exists.** It is the stable key every quote
 * line ever written against the type refers to, so changing it would orphan
 * them — a quote from last month would name a service the catalogue no longer
 * has. The field is shown, locked, with the reason: hiding it would make the
 * grid's code column look like it came from nowhere.
 *
 * **An empty rate is a real value, not a missing one.** It means "charge
 * whatever the agency charges", and the field says so with the current agency
 * figure in the helper text — so somebody clearing the box can see what they
 * are clearing it *to* rather than wondering whether they have just made the
 * service free.
 */
export function InterventionTypeDialog({
  entry,
  creating,
  agencyRate,
  onClose,
}: InterventionTypeDialogProps) {
  const { t } = useTranslation();
  const update = useUpdateInterventionType();
  const create = useCreateInterventionType();
  const [form, setForm] = useState<TypeForm>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  const open = entry !== null || creating;

  useEffect(() => {
    if (!open) return;
    setError(null);
    setForm(
      entry
        ? {
            code: entry.code,
            name: entry.name,
            description: entry.description ?? '',
            service_category: entry.service_category,
            base_hourly_rate_ht: entry.base_hourly_rate_ht ?? '',
            is_active: entry.is_active,
          }
        : { ...EMPTY },
    );
  }, [entry, creating, open]);

  const rate = form.base_hourly_rate_ht.trim().replace(',', '.');
  const rateIsNumber = rate === '' || (Number(rate) > 0 && !Number.isNaN(Number(rate)));
  const valid = Boolean(form.name.trim()) && Boolean(form.code.trim()) && rateIsNumber;

  const save = () => {
    setError(null);
    const body = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      service_category: form.service_category,
      // Empty means "inherit the agency rate", which the server stores as null.
      // Sending "0" instead would price every line of this service at nothing.
      base_hourly_rate_ht: rate === '' ? null : rate,
      is_active: form.is_active,
    };
    const onError = (cause: unknown) =>
      setError(cause instanceof Error ? cause.message : t('common.error'));

    if (entry?.id) {
      update.mutate({ id: entry.id, body }, { onSuccess: onClose, onError });
    } else {
      create.mutate(
        { ...body, code: form.code.trim().toUpperCase() },
        { onSuccess: onClose, onError },
      );
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      data-testid="type-dialog"
    >
      <DialogTitle>{entry ? t('catalog.edit') : t('catalog.add')}</DialogTitle>

      <DialogContent dividers>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? (
            <Alert severity="error" data-testid="type-dialog-error">
              {error}
            </Alert>
          ) : null}

          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                label={t('catalog.code')}
                value={form.code}
                onChange={(event) => setForm({ ...form, code: event.target.value })}
                disabled={Boolean(entry)}
                helperText={entry ? t('catalog.codeIsFixed') : t('catalog.codeHint')}
                inputProps={{ 'data-testid': 'type-code' }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 8 }}>
              <TextField
                label={t('catalog.name')}
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                inputProps={{ 'data-testid': 'type-name' }}
              />
            </Grid>
            <Grid size={12}>
              <TextField
                label={t('catalog.description')}
                value={form.description}
                onChange={(event) =>
                  setForm({ ...form, description: event.target.value })
                }
                multiline
                rows={2}
                inputProps={{ 'data-testid': 'type-description' }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                select
                label={t('catalog.category')}
                value={form.service_category}
                onChange={(event) =>
                  setForm({
                    ...form,
                    service_category: event.target.value as 'necessity' | 'comfort',
                  })
                }
                helperText={t('catalog.categorySetsVat')}
                slotProps={{
                  select: { native: true },
                  inputLabel: { shrink: true },
                  htmlInput: { 'data-testid': 'type-category' },
                }}
              >
                <option value="necessity">{t('catalog.category_necessity')}</option>
                <option value="comfort">{t('catalog.category_comfort')}</option>
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                label={t('catalog.hourlyRate')}
                value={form.base_hourly_rate_ht}
                onChange={(event) =>
                  setForm({ ...form, base_hourly_rate_ht: event.target.value })
                }
                error={!rateIsNumber}
                helperText={
                  !rateIsNumber
                    ? t('catalog.rateMustBePositive')
                    : t('catalog.emptyMeansAgencyRate', { rate: agencyRate ?? '—' })
                }
                inputProps={{ 'data-testid': 'type-rate' }}
              />
            </Grid>
          </Grid>

          <FormControlLabel
            control={
              <Switch
                checked={form.is_active}
                onChange={(event) =>
                  setForm({ ...form, is_active: event.target.checked })
                }
                data-testid="type-active"
              />
            }
            label={t('catalog.active')}
          />
          <Typography variant="caption" color="text.secondary">
            {t('catalog.retiredExplained')}
          </Typography>
        </Stack>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2 }}>
        <Box sx={{ flexGrow: 1 }} />
        <Button onClick={onClose} data-testid="cancel-type">
          {t('common.cancel')}
        </Button>
        <Button
          variant="contained"
          onClick={save}
          disabled={!valid || update.isPending || create.isPending}
          data-testid="save-type"
        >
          {t('common.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
