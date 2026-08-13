import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useBillingRun, useBillingSettings, useStartBillingRun } from '@/api/queries';
import { windowFor } from './billingWindow';

interface GenerateBillsDialogProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Ask for a period to be billed, and watch the run that does it.
 *
 * @param props - Whether the dialog is showing, and how to close it.
 * @returns The rendered dialog.
 *
 * @remarks
 * **A day, never a window.** The period comes from the agency's own
 * periodicity, so nobody can invoice a fortnight the settings do not describe
 * and produce a window nobody could reproduce afterwards. The resolved window
 * is shown read-only beside the picker.
 *
 * That window is the **default** one, and the alert says so. A customer with a
 * granularity of their own is billed over theirs, which is why the run reports
 * how many invoices it wrote rather than promising one per customer: a yearly
 * customer whose year is still open is passed over, and a manager counting rows
 * against the customer book would otherwise read that as a failure.
 *
 * The run answers 202 with an identifier; the invoices are written by a worker,
 * so the dialog polls until the run is terminal. A **partial** run is finished
 * — the invoices that could be written are written — and its failure count is
 * reported rather than hidden, because a month with three customers unbilled is
 * only actionable if somebody is told.
 *
 * The dialog says plainly that nothing is sent. Generating leaves every invoice
 * waiting for validation, and a manager who assumed otherwise would spend the
 * afternoon looking for emails that were never meant to go.
 */
export function GenerateBillsDialog({ open, onClose }: GenerateBillsDialogProps) {
  const { t } = useTranslation();
  const { data: settings } = useBillingSettings();
  const start = useStartBillingRun();
  const [day, setDay] = useState('');
  const [runId, setRunId] = useState('');
  const { data: run } = useBillingRun(runId);

  const preview = day && settings ? windowFor(day, settings.periodicity) : null;

  const submit = () => {
    start.mutate(
      { reference_date: day },
      { onSuccess: (created) => setRunId(created.id ?? '') },
    );
  };

  const close = () => {
    setDay('');
    setRunId('');
    start.reset();
    onClose();
  };

  const running =
    start.isPending ||
    (run !== undefined && (run.status === 'pending' || run.status === 'running'));

  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="sm">
      <DialogTitle>{t('bills.generateTitle')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }} data-testid="generate-bills-dialog">
          <Typography variant="body2" color="text.secondary">
            {t('bills.generateHelp')}
          </Typography>

          <TextField
            type="date"
            label={t('bills.referenceDate')}
            value={day}
            onChange={(event) => setDay(event.target.value)}
            InputLabelProps={{ shrink: true }}
            inputProps={{ 'data-testid': 'generate-reference-date' }}
          />

          {preview ? (
            <Alert severity="info" data-testid="generate-window">
              {`${t('bills.window', {
                start: preview.start,
                end: preview.end,
              })} ${t('bills.windowIsTheDefault')}`}
            </Alert>
          ) : null}

          {running ? (
            <Alert severity="info" data-testid="generate-running">
              {t('bills.generating')}
            </Alert>
          ) : null}

          {start.isError ? (
            <Alert severity="error" data-testid="generate-error">
              {t('bills.generateFailed')}
            </Alert>
          ) : null}

          {run && run.status === 'succeeded' ? (
            <Alert severity="success" data-testid="generate-succeeded">
              {t('bills.generated', { count: run.bill_ids.length })}
            </Alert>
          ) : null}

          {run && run.status === 'partial' ? (
            <Alert severity="warning" data-testid="generate-partial">
              {`${t('bills.generated', { count: run.bill_ids.length })} ${t(
                'bills.partial',
                { count: run.failed_customer_ids.length },
              )}`}
            </Alert>
          ) : null}

          {run && run.status === 'failed' ? (
            <Alert severity="error" data-testid="generate-failed">
              {t('bills.generateFailed')}
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close} data-testid="generate-close">
          {t('common.close')}
        </Button>
        <Button
          variant="contained"
          onClick={submit}
          disabled={!day || running}
          data-testid="generate-submit"
        >
          {t('bills.generate')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
