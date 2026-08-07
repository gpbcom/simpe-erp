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
import {
  useCreateSkillType,
  useDeleteSkillType,
  useUpdateSkillType,
} from '@/api/queries';
import type { SkillType } from '@/api/types';

/** Everything the form edits, flattened for the inputs. */
interface SkillForm {
  code: string;
  label: string;
  description: string;
  is_active: boolean;
}

const EMPTY: SkillForm = {
  code: '',
  label: '',
  description: '',
  is_active: true,
};

interface SkillTypeDialogProps {
  /** The entry to edit, or `null` when not editing one. */
  entry: SkillType | null;
  /** Whether the dialog is open to create a new entry instead. */
  creating: boolean;
  /** Called when the dialog should close. */
  onClose: () => void;
}

/**
 * Add a skill to the catalogue, or change what an existing one says.
 *
 * @param props - The entry, the mode and the close handler.
 * @returns The rendered dialog.
 *
 * @remarks
 * One dialog for both creating and editing, because the fields are the same.
 * What differs is whether `code` can be typed.
 *
 * **`code` is fixed once an entry exists.** It is what every assistant's
 * declared skill and every service's requirement is matched on, so renaming it
 * would un-skill every holder on the next planning run. The server refuses it
 * outright — the payload carries no `code` at all — and the input is locked
 * with the reason beneath it. A locked field that does not explain itself
 * reads as a bug.
 *
 * **Deleting is offered only from here, and usually refused.** The server
 * counts the assistants who declared the code and the services requiring it and
 * answers 409 naming both, because no foreign key protects those references.
 * The refusal is shown verbatim: it already says to retire the entry instead,
 * and retiring is one switch away in the same dialog.
 */
export function SkillTypeDialog({ entry, creating, onClose }: SkillTypeDialogProps) {
  const { t } = useTranslation();
  const update = useUpdateSkillType();
  const create = useCreateSkillType();
  const remove = useDeleteSkillType();
  const [form, setForm] = useState<SkillForm>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  const open = entry !== null || creating;

  useEffect(() => {
    if (!open) return;
    setError(null);
    setForm(
      entry
        ? {
            code: entry.code,
            label: entry.label,
            description: entry.description ?? '',
            is_active: entry.is_active,
          }
        : { ...EMPTY },
    );
  }, [entry, creating, open]);

  // Unaccented, because the code travels into exports and URLs where an accent
  // is escaped differently by every consumer. The server refuses one anyway;
  // saying so here means the operator is not told after they press save.
  const codeIsWellFormed = /^[A-Za-z0-9_-]{1,32}$/.test(form.code.trim());
  const valid = Boolean(form.label.trim()) && codeIsWellFormed;

  const onError = (cause: unknown) =>
    setError(cause instanceof Error ? cause.message : t('common.error'));

  const save = () => {
    setError(null);
    const body = {
      label: form.label.trim(),
      description: form.description.trim() || null,
      is_active: form.is_active,
    };
    if (entry?.id) {
      update.mutate({ id: entry.id, body }, { onSuccess: onClose, onError });
    } else {
      create.mutate(
        { ...body, code: form.code.trim().toUpperCase() },
        { onSuccess: onClose, onError },
      );
    }
  };

  const destroy = () => {
    if (!entry?.id) return;
    setError(null);
    remove.mutate(entry.id, { onSuccess: onClose, onError });
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      data-testid="skill-dialog"
    >
      <DialogTitle>{entry ? t('skills.edit') : t('skills.add')}</DialogTitle>

      <DialogContent dividers>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? (
            <Alert severity="error" data-testid="skill-dialog-error">
              {error}
            </Alert>
          ) : null}

          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                label={t('skills.code')}
                value={form.code}
                onChange={(event) => setForm({ ...form, code: event.target.value })}
                disabled={Boolean(entry)}
                error={form.code.trim() !== '' && !codeIsWellFormed}
                helperText={entry ? t('skills.codeIsFixed') : t('skills.codeHint')}
                slotProps={{ htmlInput: { 'data-testid': 'skill-code' } }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 8 }}>
              <TextField
                label={t('skills.label')}
                value={form.label}
                onChange={(event) => setForm({ ...form, label: event.target.value })}
                slotProps={{ htmlInput: { 'data-testid': 'skill-label' } }}
              />
            </Grid>
            <Grid size={12}>
              <TextField
                label={t('skills.description')}
                value={form.description}
                onChange={(event) =>
                  setForm({ ...form, description: event.target.value })
                }
                multiline
                rows={2}
                slotProps={{ htmlInput: { 'data-testid': 'skill-description' } }}
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
                data-testid="skill-active"
              />
            }
            label={t('skills.active')}
          />
          <Typography variant="caption" color="text.secondary">
            {t('skills.retiredExplained')}
          </Typography>
        </Stack>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2 }}>
        {entry ? (
          <Button
            color="error"
            onClick={destroy}
            disabled={remove.isPending}
            data-testid="delete-skill"
          >
            {t('common.delete')}
          </Button>
        ) : null}
        <Box sx={{ flexGrow: 1 }} />
        <Button onClick={onClose} data-testid="cancel-skill">
          {t('common.cancel')}
        </Button>
        <Button
          variant="contained"
          onClick={save}
          disabled={!valid || update.isPending || create.isPending}
          data-testid="save-skill"
        >
          {t('common.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
