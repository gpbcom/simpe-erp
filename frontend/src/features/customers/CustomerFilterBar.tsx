import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Collapse from '@mui/material/Collapse';
import Grid from '@mui/material/Grid2';
import InputAdornment from '@mui/material/InputAdornment';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SearchIcon from '@mui/icons-material/Search';
import type { CustomerFilterState, CustomerTextField } from './useCustomerFilter';
import type { RegistrationStatus } from '@/api/types';

const TABS: { key: string; status?: RegistrationStatus }[] = [
  { key: 'all' },
  { key: 'prospect', status: 'prospect' },
  { key: 'active', status: 'active' },
  { key: 'stopped', status: 'stopped' },
];

const DETAILS: { field: CustomerTextField; label: string }[] = [
  { field: 'city', label: 'customer.city' },
  { field: 'postal_code', label: 'customer.postalCode' },
  { field: 'email', label: 'customer.email' },
  { field: 'phone', label: 'customer.phone' },
];

interface CustomerFilterBarProps {
  filter: CustomerFilterState;
}

/**
 * Everything that narrows the customer book.
 *
 * @param props - The filter state.
 * @returns The rendered bar.
 *
 * @remarks
 * **Prospects are the second tab**, where the validation queue sits on the
 * quotes screen and for the same reason: it is the list somebody has to act on.
 * A prospect can be holding accepted work that no planning run will touch, and
 * the only thing that changes it is a manager finding them.
 *
 * The four detail filters are folded away. Six boxes open at once say the
 * screen is complicated; the two that get used every day — the search and the
 * status — stay in the open, and the button says how many of the others are on
 * so a folded filter can never narrow the book invisibly.
 *
 * The flags are native selects with three options rather than checkboxes,
 * because they have three states. A checkbox cannot say "only those *without*
 * an ongoing arrangement", which is how a manager finds the families the agency
 * has quoted and then forgotten.
 */
export function CustomerFilterBar({ filter }: CustomerFilterBarProps) {
  const { t } = useTranslation();
  const { draft, setText, setStatus, setFlag, reset, isFiltered } = filter;
  const [expanded, setExpanded] = useState(false);

  const detailCount =
    DETAILS.filter((entry) => draft[entry.field]).length +
    (draft.has_ongoing_arrangement === undefined ? 0 : 1) +
    (draft.is_geocoded === undefined ? 0 : 1);

  const tab = Math.max(
    0,
    TABS.findIndex((entry) => entry.status === draft.status),
  );

  const toFlag = (value: string): boolean | undefined =>
    value === '' ? undefined : value === 'true';

  const fromFlag = (value: boolean | undefined): string =>
    value === undefined ? '' : String(value);

  return (
    <Stack spacing={2}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        alignItems={{ sm: 'center' }}
      >
        <TextField
          placeholder={t('customer.search')}
          value={draft.search ?? ''}
          onChange={(event) => setText('search', event.target.value)}
          sx={{ maxWidth: 420, flexGrow: 1 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
            htmlInput: { 'data-testid': 'customer-search' },
          }}
        />
        <Button
          size="small"
          onClick={() => setExpanded((open) => !open)}
          endIcon={expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          data-testid="toggle-customer-filters"
        >
          {detailCount > 0
            ? t('customer.moreFiltersCount', { count: detailCount })
            : t('customer.moreFilters')}
        </Button>
        {isFiltered ? (
          <Button size="small" onClick={reset} data-testid="clear-customer-filters">
            {t('customer.clearFilters')}
          </Button>
        ) : null}
      </Stack>

      <Tabs
        value={tab}
        onChange={(_event, next: number) => setStatus(TABS[next]?.status)}
        data-testid="customer-status-tabs"
      >
        {TABS.map((entry) => (
          <Tab
            key={entry.key}
            label={t(`customer.filter_${entry.key}`)}
            data-testid={`customer-tab-${entry.key}`}
          />
        ))}
      </Tabs>

      <Collapse in={expanded} unmountOnExit>
        <Box data-testid="customer-filters">
          <Grid container spacing={2}>
            {DETAILS.map((entry) => (
              <Grid key={entry.field} size={{ xs: 12, sm: 6, md: 3 }}>
                <TextField
                  fullWidth
                  size="small"
                  label={t(entry.label)}
                  value={draft[entry.field] ?? ''}
                  onChange={(event) => setText(entry.field, event.target.value)}
                  slotProps={{
                    inputLabel: { shrink: true },
                    htmlInput: { 'data-testid': `customer-filter-${entry.field}` },
                  }}
                />
              </Grid>
            ))}
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <TextField
                select
                fullWidth
                size="small"
                label={t('customer.filterOngoing')}
                value={fromFlag(draft.has_ongoing_arrangement)}
                onChange={(event) =>
                  setFlag('has_ongoing_arrangement', toFlag(event.target.value))
                }
                slotProps={{
                  select: { native: true },
                  inputLabel: { shrink: true },
                  htmlInput: { 'data-testid': 'customer-filter-ongoing' },
                }}
              >
                <option value="">{t('customer.filterAny')}</option>
                <option value="true">{t('customer.filterOngoingYes')}</option>
                <option value="false">{t('customer.filterOngoingNo')}</option>
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <TextField
                select
                fullWidth
                size="small"
                label={t('customer.filterGeocoded')}
                value={fromFlag(draft.is_geocoded)}
                onChange={(event) => setFlag('is_geocoded', toFlag(event.target.value))}
                slotProps={{
                  select: { native: true },
                  inputLabel: { shrink: true },
                  htmlInput: { 'data-testid': 'customer-filter-geocoded' },
                }}
              >
                <option value="">{t('customer.filterAny')}</option>
                <option value="true">{t('customer.filterGeocodedYes')}</option>
                <option value="false">{t('customer.filterGeocodedNo')}</option>
              </TextField>
            </Grid>
          </Grid>
        </Box>
      </Collapse>
    </Stack>
  );
}
