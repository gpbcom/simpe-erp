import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Divider from '@mui/material/Divider';
import Grid from '@mui/material/Grid2';
import InputAdornment from '@mui/material/InputAdornment';
import Link from '@mui/material/Link';
import Pagination from '@mui/material/Pagination';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import SearchIcon from '@mui/icons-material/Search';
import { alpha, useTheme } from '@mui/material/styles';
import { useIntegrations } from '@/api/queries';
import type { IntegrationCard, TransmissionKind } from '@/api/types';
import { BRAND } from '@/theme/palette';
import { EInvoicingWarning } from './EInvoicingWarning';
import { IntegrationDialog } from './IntegrationDialog';

/** How many cards a page holds, matching the four-column grid. */
const PER_PAGE = 8;

/** The tabs, and the coverage each filters on. */
const CATEGORIES: { key: string; coverage: TransmissionKind | null }[] = [
  { key: 'all', coverage: null },
  { key: 'invoice', coverage: 'invoice' },
  { key: 'reporting', coverage: 'payment-report' },
  { key: 'public', coverage: 'chorus-pro' },
];

/** The sort orders offered. */
const SORTS = ['alpha', 'status'] as const;

/** A tile colour per platform, so a card is recognisable at a glance. */
const TILE_COLOURS: Record<string, string> = {
  b2brouter: '#1F6FEB',
  storecove: '#0F6E6E',
  invopop: '#7C3AED',
  iopole: '#C8791A',
};

/**
 * The integrations gallery: every certified platform, and how to connect one.
 *
 * @returns The rendered gallery.
 *
 * @remarks
 * **Laid out to the reference design** — a heading and lead, a centred tab row,
 * a sort control and a search field on one line, then a responsive
 * four-column grid of tiles. Two departures, both deliberate:
 *
 * - **Monogram tiles rather than vendor logos.** This repository ships only
 *   SimpleERP's own marks, and vendoring four third-party trademarks is a
 *   licensing decision rather than a design one. The tile keeps the reference's
 *   position and size.
 * - **The tabs filter on what a platform can transmit** — invoices, payment
 *   reporting, public bodies — rather than on the reference's own categories,
 *   which describe a different catalogue. It is also the one filter that
 *   matters here: an agency invoicing a conseil départemental needs to know
 *   which platforms reach Chorus Pro *before* it picks one.
 *
 * **Pagination renders only when there is more than one page.** With four
 * platforms it never appears; the component is already right if the list grows.
 *
 * The whole screen is about two clicks: a card opens the dialog, and the dialog
 * saves. Switching platform is the same two, because enabling one disables the
 * previous server-side.
 */
export function IntegrationsGallery() {
  const { t } = useTranslation();
  const theme = useTheme();
  const { data: cards, isLoading } = useIntegrations();
  const [category, setCategory] = useState('all');
  const [sort, setSort] = useState<(typeof SORTS)[number]>('alpha');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [chosen, setChosen] = useState<IntegrationCard | null>(null);

  const dark = theme.palette.mode === 'dark';

  const shown = useMemo(() => {
    const wanted = CATEGORIES.find((entry) => entry.key === category)?.coverage;
    const needle = search.trim().toLowerCase();
    const matching = (cards ?? []).filter(
      (card) =>
        (!wanted || card.coverage.includes(wanted)) &&
        (!needle || card.name.toLowerCase().includes(needle)),
    );
    // Enabled first under "status", because the one an agency transmits
    // through is the one it came here to check on.
    return [...matching].sort((left, right) =>
      sort === 'alpha'
        ? left.name.localeCompare(right.name)
        : Number(right.enabled) - Number(left.enabled) ||
          left.name.localeCompare(right.name),
    );
  }, [cards, category, search, sort]);

  const pages = Math.max(1, Math.ceil(shown.length / PER_PAGE));
  const visible = shown.slice((page - 1) * PER_PAGE, page * PER_PAGE);
  const connected = (cards ?? []).some((card) => card.enabled);

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box data-testid="integrations-gallery">
      <Typography variant="h5" sx={{ mb: 0.5 }}>
        {t('integrations.title')}
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        {t('integrations.lead')}
      </Typography>

      {connected ? null : <EInvoicingWarning />}

      <Divider />
      <Tabs
        value={category}
        onChange={(_, value: string) => {
          setCategory(value);
          setPage(1);
        }}
        centered
        sx={{ mb: 1 }}
        data-testid="integrations-tabs"
      >
        {CATEGORIES.map((entry) => (
          <Tab
            key={entry.key}
            value={entry.key}
            label={t(`integrations.category.${entry.key}`)}
            data-testid={`integrations-tab-${entry.key}`}
          />
        ))}
      </Tabs>
      <Divider sx={{ mb: 2 }} />

      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        justifyContent="space-between"
        alignItems={{ sm: 'center' }}
        sx={{ mb: 3 }}
      >
        <TextField
          select
          size="small"
          label={t('integrations.sortBy')}
          value={sort}
          onChange={(event) =>
            setSort(event.target.value as (typeof SORTS)[number])
          }
          sx={{ minWidth: 240 }}
          slotProps={{
            select: { native: true },
            inputLabel: { shrink: true },
            htmlInput: { 'data-testid': 'integrations-sort' },
          }}
        >
          {SORTS.map((option) => (
            <option key={option} value={option}>
              {t(`integrations.sort.${option}`)}
            </option>
          ))}
        </TextField>
        <TextField
          size="small"
          placeholder={t('integrations.search')}
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 280 }}
          slotProps={{
            input: {
              endAdornment: (
                <InputAdornment position="end">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
            htmlInput: { 'data-testid': 'integrations-search' },
          }}
        />
      </Stack>

      <Grid container spacing={2.5} data-testid="integrations-grid">
        {visible.map((card) => (
          <Grid size={{ xs: 12, sm: 6, md: 3 }} key={card.provider}>
            <Card
              variant="outlined"
              onClick={() => setChosen(card)}
              sx={{
                height: '100%',
                cursor: 'pointer',
                borderColor: card.enabled ? BRAND.primary : undefined,
                borderWidth: card.enabled ? 2 : 1,
                transition: 'border-color .15s, transform .15s',
                '&:hover': {
                  borderColor: BRAND.primary,
                  transform: 'translateY(-2px)',
                },
              }}
              data-testid={`integration-card-${card.provider}`}
            >
              <CardContent sx={{ textAlign: 'center' }}>
                <Box
                  sx={{
                    width: 76,
                    height: 76,
                    mx: 'auto',
                    mb: 1.5,
                    borderRadius: 1.5,
                    display: 'grid',
                    placeItems: 'center',
                    color: '#fff',
                    bgcolor: TILE_COLOURS[card.provider] ?? BRAND.primary,
                    fontSize: '2rem',
                    fontWeight: 700,
                  }}
                  aria-hidden
                >
                  {card.name.slice(0, 1)}
                </Box>
                <Typography sx={{ fontWeight: 600 }}>{card.name}</Typography>
                <Stack
                  direction="row"
                  spacing={0.5}
                  justifyContent="center"
                  sx={{ mt: 1, flexWrap: 'wrap', rowGap: 0.5 }}
                >
                  {card.enabled ? (
                    <Chip
                      size="small"
                      color="primary"
                      label={t('integrations.enabled')}
                      data-testid={`integration-enabled-${card.provider}`}
                    />
                  ) : null}
                  {card.configured && !card.enabled ? (
                    <Chip size="small" label={t('integrations.configured')} />
                  ) : null}
                  {card.documentation_verified ? null : (
                    <Chip
                      size="small"
                      color="warning"
                      variant="outlined"
                      label={t('integrations.unverified')}
                      data-testid={`integration-unverified-${card.provider}`}
                    />
                  )}
                </Stack>
                {card.last_check_error ? (
                  <Typography
                    variant="caption"
                    color="error"
                    sx={{ display: 'block', mt: 1 }}
                    data-testid={`integration-error-${card.provider}`}
                  >
                    {t('integrations.checkFailed')}
                  </Typography>
                ) : null}
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {shown.length === 0 ? (
        <Alert severity="info" sx={{ mt: 2 }} data-testid="integrations-empty">
          {t('integrations.noMatch')}
        </Alert>
      ) : null}

      {/* Only when it does something. The reference design paginates 169
          entries; four would render a control whose every state is identical. */}
      {pages > 1 ? (
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="center"
          sx={{
            mt: 3,
            pt: 2,
            borderTop: 1,
            borderColor: 'divider',
            bgcolor: alpha(BRAND.primary, dark ? 0.08 : 0.03),
          }}
          data-testid="integrations-pagination"
        >
          <Pagination
            count={pages}
            page={page}
            onChange={(_, value) => setPage(value)}
            size="small"
          />
          <Typography variant="body2" color="text.secondary">
            {t('integrations.showing', {
              from: (page - 1) * PER_PAGE + 1,
              to: Math.min(page * PER_PAGE, shown.length),
              total: shown.length,
            })}
          </Typography>
        </Stack>
      ) : null}

      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: 'block', mt: 3 }}
      >
        {t('integrations.registryNote')}{' '}
        <Link
          href="https://www.impots.gouv.fr/facturation-electronique"
          target="_blank"
          rel="noreferrer"
        >
          impots.gouv.fr
        </Link>
      </Typography>

      {chosen ? (
        <IntegrationDialog card={chosen} onClose={() => setChosen(null)} />
      ) : null}
    </Box>
  );
}
