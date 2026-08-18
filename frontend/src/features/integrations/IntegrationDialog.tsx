import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useDisableIntegration, useEnableIntegration } from '@/api/queries';
import type { IntegrationCard } from '@/api/types';

const FIELDS = ['api_key', 'account_id', 'legal_entity_id'] as const;

/**
 * Connecting one platform, in as few actions as the task allows.
 *
 * @param props - The card that was clicked, and how to close.
 * @returns The rendered dialog.
 *
 * @remarks
 * **Two clicks and a paste.** The card opens this. The button saves. There is
 * no separate "test" step because the server proves the credentials against the
 * live platform as part of enabling — a rejected key comes back as an error
 * into the dialog that is still open, which is where the person who typed it is
 * looking.
 *
 * **Only the fields this platform needs are rendered**, from `required_fields`
 * on the card. Storecove wants a legal-entity reference created in its own
 * console; B2Brouter wants an account. The other two want a key alone. Asking
 * every platform for every field would be three empty boxes and a question
 * about which matter.
 *
 * **The stored key is never shown, because the server never sends it.** A
 * configured platform shows the masked tail so a manager can tell whether the
 * key in front of them is the one they think it is, and re-entering replaces it.
 */
export function IntegrationDialog({
  card,
  onClose,
}: {
  card: IntegrationCard;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const enable = useEnableIntegration();
  const disable = useDisableIntegration();
  const [values, setValues] = useState<Record<string, string>>({});

  const missing = card.required_fields.some((name) => !values[name]?.trim());

  const save = () => {
    enable.mutate(
      {
        provider: card.provider,
        body: {
          api_key: values.api_key ?? '',
          account_id: values.account_id || null,
          legal_entity_id: values.legal_entity_id || null,
        },
      },
      { onSuccess: onClose },
    );
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle data-testid="integration-dialog-title">
        {t('integrations.connect', { name: card.name })}
      </DialogTitle>
      <DialogContent data-testid="integration-dialog">
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {t('integrations.dialogLead', { name: card.name })}{' '}
            <Link href={card.documentation_url} target="_blank" rel="noreferrer">
              {t('integrations.documentation')}
            </Link>
          </Typography>

          {card.documentation_verified ? null : (
            <Alert severity="warning" data-testid="integration-dialog-unverified">
              {t('integrations.unverifiedHelp', { name: card.name })}
            </Alert>
          )}

          {card.configured ? (
            <Alert severity="info" data-testid="integration-dialog-hint">
              {t('integrations.alreadyConfigured', {
                hint: card.credential_hint,
              })}
            </Alert>
          ) : null}

          {FIELDS.filter((name) => card.required_fields.includes(name)).map(
            (name, index) => (
              <TextField
                key={name}
                autoFocus={index === 0}
                type={name === 'api_key' ? 'password' : 'text'}
                label={t(`integrations.field.${name}`)}
                helperText={t(`integrations.fieldHelp.${name}`)}
                value={values[name] ?? ''}
                onChange={(event) =>
                  setValues({ ...values, [name]: event.target.value })
                }
                slotProps={{
                  htmlInput: { 'data-testid': `integration-field-${name}` },
                }}
              />
            ),
          )}

          {enable.isError ? (
            <Alert severity="error" data-testid="integration-dialog-error">
              {t('integrations.refused')}
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        {card.enabled ? (
          <Button
            color="warning"
            onClick={() => disable.mutate(card.provider, { onSuccess: onClose })}
            disabled={disable.isPending}
            data-testid="integration-disable"
          >
            {t('integrations.disable')}
          </Button>
        ) : null}
        <Button onClick={onClose} data-testid="integration-cancel">
          {t('integrations.cancel')}
        </Button>
        <Button
          variant="contained"
          onClick={save}
          disabled={missing || enable.isPending}
          data-testid="integration-save"
        >
          {t('integrations.enable')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
