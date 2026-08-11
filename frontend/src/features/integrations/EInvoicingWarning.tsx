import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Button from '@mui/material/Button';
import { useIntegrations } from '@/api/queries';

/**
 * Says out loud that this agency cannot transmit an invoice yet.
 *
 * @param props - Whether to offer a way to the gallery.
 * @returns The banner, or nothing when a platform is connected.
 *
 * @remarks
 * **Electronic invoicing is an obligation, not a feature**, which is why an
 * agency with nothing connected is told rather than left to notice an empty
 * list. From September 2027 a PME must issue electronic invoices and perform
 * e-reporting; invoicing a conseil départemental through Chorus Pro has been
 * mandatory since 2020.
 *
 * **Rendered on the bills list as well as in the settings**, because the bills
 * list is where a manager actually works. A warning only on a settings screen
 * is a warning nobody sees until they go looking for the thing it is warning
 * about.
 *
 * Renders nothing while loading rather than flashing a warning that may be
 * wrong — an agency that *has* connected a platform must never be told for a
 * moment that it has not.
 */
export function EInvoicingWarning({ withLink = false }: { withLink?: boolean }) {
  const { t } = useTranslation();
  const { data: cards, isLoading } = useIntegrations();

  if (isLoading || !cards || cards.some((card) => card.enabled)) {
    return null;
  }

  return (
    <Alert
      severity="warning"
      sx={{ mb: 2 }}
      data-testid="einvoicing-warning"
      action={
        withLink ? (
          <Button
            component={RouterLink}
            to="/billing-settings"
            size="small"
            color="inherit"
            data-testid="einvoicing-warning-link"
          >
            {t('integrations.warningAction')}
          </Button>
        ) : undefined
      }
    >
      <AlertTitle>{t('integrations.warningTitle')}</AlertTitle>
      {t('integrations.warningBody')}
    </Alert>
  );
}
