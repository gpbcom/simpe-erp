import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useCancelVisit } from '@/api/queries';
import { formatTime } from '@/utils/format';
import type { Intervention } from '@/api/types';

interface PortalCancelDialogProps {
  /** The visit to cancel, or `null` when the dialog is closed. */
  visit: Intervention | null;
  /** Called when the dialog should close without cancelling. */
  onClose: () => void;
  /** Called once the visit has been cancelled. */
  onDone: () => void;
}

/**
 * Confirm cancelling one visit, and say what it costs.
 *
 * @param props - The visit, and the two handlers.
 * @returns The rendered dialog.
 *
 * @remarks
 * **A confirmation that does not say what happens is a confirmation nobody
 * reads.** Cancelling here is not "remove a block from a calendar": the line
 * comes off the quote, the quote is repriced, and it goes back to the agency to
 * be agreed again. Until a manager does that, *nothing on that quote is
 * scheduled* — not only the cancelled visit.
 *
 * That last consequence is the one worth spelling out. A household who cancels
 * one Tuesday and finds their whole week gone would reasonably think the
 * application had broken.
 */
export function PortalCancelDialog({
  visit,
  onClose,
  onDone,
}: PortalCancelDialogProps) {
  const { t } = useTranslation();
  const cancel = useCancelVisit();
  const [error, setError] = useState<string | null>(null);

  const confirm = () => {
    if (!visit?.id) return;
    setError(null);
    cancel.mutate(visit.id, {
      onSuccess: onDone,
      onError: (cause) =>
        setError(cause instanceof Error ? cause.message : t('common.error')),
    });
  };

  return (
    <Dialog
      open={Boolean(visit)}
      onClose={onClose}
      fullWidth
      data-testid="portal-cancel-dialog"
    >
      <DialogTitle>{t('portal.cancelTitle')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {visit ? (
            <Typography data-testid="portal-cancel-visit-summary">
              {visit.name} · {visit.day} · {formatTime(visit.start_time)} –{' '}
              {formatTime(visit.end_time)}
            </Typography>
          ) : null}
          <Alert severity="warning">{t('portal.cancelWarning')}</Alert>
          {error ? (
            <Alert severity="error" data-testid="portal-cancel-error">
              {error}
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} data-testid="portal-cancel-dismiss">
          {t('common.cancel')}
        </Button>
        <Button
          variant="contained"
          color="error"
          onClick={confirm}
          disabled={cancel.isPending}
          data-testid="portal-cancel-confirm"
        >
          {t('portal.cancelConfirm')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
