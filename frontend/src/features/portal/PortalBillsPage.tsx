import { useTranslation } from 'react-i18next';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import DownloadIcon from '@mui/icons-material/Download';
import { usePortalBills, useDownloadPortalBill } from '@/api/queries';
import { BillStatusChip } from '@/features/bills/BillStatusChip';
import { formatDate, formatMoney } from '@/utils/format';

/**
 * Every invoice the agency has issued to the household.
 *
 * @returns The rendered page.
 *
 * @remarks
 * - **The total is the gross**, not the untaxed figure. A household pays
 *   `total_ttc`; showing them the amount the agency books would be a smaller
 *   number in the place they look for what they owe.
 * - The due date sits beside it, because "when" is the second question after
 *   "how much" and an invoice list that answers only the first sends somebody
 *   into the PDF to find it.
 * - Cards and the shared status chip, for the same reasons as the quotes
 *   screen: a phone-sized list, and a status that means one thing on both
 *   sides of the agency.
 */
export function PortalBillsPage() {
  const { t, i18n } = useTranslation();
  const { data: bills, isLoading } = usePortalBills();
  const download = useDownloadPortalBill();

  if (isLoading) return <Typography>{t('common.loading')}</Typography>;

  return (
    <Stack spacing={2}>
      <Typography variant="h1">{t('portal.myBills')}</Typography>

      {(bills ?? []).length === 0 ? (
        <Typography color="text.secondary" data-testid="portal-no-bill">
          {t('portal.noBill')}
        </Typography>
      ) : null}

      <Stack spacing={1.5} data-testid="portal-bills">
        {(bills ?? []).map((bill) => (
          <Card key={bill.id} data-testid={`portal-bill-${bill.number}`}>
            <CardContent>
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={2}
                alignItems={{ sm: 'center' }}
              >
                <Stack spacing={0.5} sx={{ flexGrow: 1 }}>
                  <Typography variant="h3">{bill.number}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {t('portal.dueOn', {
                      date: formatDate(bill.due_on, i18n.language),
                    })}
                  </Typography>
                </Stack>
                <Typography variant="h3" data-testid={`portal-bill-total-${bill.number}`}>
                  {formatMoney(bill.total_ttc, i18n.language)}
                </Typography>
                <BillStatusChip status={bill.status} />
                <Button
                  startIcon={<DownloadIcon />}
                  onClick={() =>
                    download.mutate({ id: bill.id ?? '', number: bill.number })
                  }
                  disabled={download.isPending}
                  data-testid={`portal-download-bill-${bill.number}`}
                >
                  {t('portal.downloadPdf')}
                </Button>
              </Stack>
            </CardContent>
          </Card>
        ))}
      </Stack>
    </Stack>
  );
}
