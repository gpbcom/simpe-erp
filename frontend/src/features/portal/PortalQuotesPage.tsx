import { useTranslation } from 'react-i18next';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import DownloadIcon from '@mui/icons-material/Download';
import { usePortalQuotes, useDownloadPortalQuote } from '@/api/queries';
import { QuoteStatusChip } from '@/features/quotes/QuoteStatusChip';
import { formatDate } from '@/utils/format';

/**
 * Every quote the agency has written for the household.
 *
 * @returns The rendered page.
 *
 * @remarks
 * - **Unfiltered, including refused and expired ones.** A household asking
 *   "what did you quote me in March" is asking about the history. A list
 *   narrowed to what is live answers a different question without saying so.
 * - Cards rather than a grid. This is a handful of documents read on a phone,
 *   not ninety rows scanned for one — the opposite of the manager's screen, and
 *   the same reasoning that gives an assistant cards for their portfolio.
 * - The status chip is the **same component** the agency's own screens use, so
 *   "awaiting validation" means the same thing and looks the same on both
 *   sides — which matters most right after a household has changed something
 *   and is looking for confirmation that the agency has it.
 */
export function PortalQuotesPage() {
  const { t, i18n } = useTranslation();
  const { data: quotes, isLoading } = usePortalQuotes();
  const download = useDownloadPortalQuote();

  if (isLoading) return <Typography>{t('common.loading')}</Typography>;

  return (
    <Stack spacing={2}>
      <Typography variant="h1">{t('portal.myQuotes')}</Typography>

      {(quotes ?? []).length === 0 ? (
        <Typography color="text.secondary" data-testid="portal-no-quote">
          {t('portal.noQuote')}
        </Typography>
      ) : null}

      <Stack spacing={1.5} data-testid="portal-quotes">
        {(quotes ?? []).map((quote) => (
          <Card key={quote.id} data-testid={`portal-quote-${quote.reference}`}>
            <CardContent>
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={2}
                alignItems={{ sm: 'center' }}
              >
                <Stack spacing={0.5} sx={{ flexGrow: 1 }}>
                  <Typography variant="h3">{quote.reference}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {formatDate(quote.issued_on, i18n.language)}
                  </Typography>
                </Stack>
                <QuoteStatusChip status={quote.status} />
                <Button
                  startIcon={<DownloadIcon />}
                  onClick={() =>
                    download.mutate({
                      id: quote.id ?? '',
                      reference: quote.reference,
                    })
                  }
                  disabled={download.isPending}
                  data-testid={`portal-download-quote-${quote.reference}`}
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
