import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { EntityFilterBar } from '@/components/filters/EntityFilterBar';
import type { FilterDetail, FilterTab } from '@/components/filters/EntityFilterBar';
import { useEntityFilter } from '@/components/filters/entityFilter';
import type { EntityFilterSpec } from '@/components/filters/entityFilter';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import AddIcon from '@mui/icons-material/Add';
import { useInterventionTypes, usePricingRules } from '@/api/queries';
import { InterventionTypeDialog } from './InterventionTypeDialog';
import { formatMoney } from '@/utils/format';
import type { InterventionType } from '@/api/types';

const CATALOG_FILTER_SPEC: EntityFilterSpec = {
  textFields: ['search', 'code', 'name'],
  flagFields: ['is_active'],
  enumFields: { service_category: ['necessity', 'comfort'] },
};

const CATALOG_TABS: FilterTab[] = [
  { key: 'all', label: 'catalog.filter_all' },
  { key: 'necessity', value: 'necessity', label: 'catalog.filter_necessity' },
  { key: 'comfort', value: 'comfort', label: 'catalog.filter_comfort' },
];

const CATALOG_DETAILS: FilterDetail[] = [
  { field: 'code', label: 'catalog.filterCode', kind: 'text' },
  { field: 'name', label: 'catalog.filterName', kind: 'text' },
  {
    field: 'is_active',
    label: 'catalog.filterActive',
    kind: 'flag',
    options: [
      { value: 'true', label: 'catalog.filterActiveYes' },
      { value: 'false', label: 'catalog.filterActiveNo' },
    ],
  },
];

/**
 * The catalogue: what the agency sells, and what each entry costs an hour.
 *
 * @returns The rendered page.
 *
 * @remarks
 * **This is where a rate is set.** Every quote line names a catalogue entry,
 * and the entry's hourly rate is what the line is priced from — so this screen
 * decides what the agency charges, and it is the only place that does. Nothing
 * on a quote lets an operator type an amount: the server prices from here.
 *
 * An entry that names **no rate of its own falls back to the agency rate**, and
 * the grid shows that plainly — the inherited figure in muted type with the
 * word "agency" beside it, rather than an empty cell. An empty cell reads as
 * "free", and the difference between "inherits €31.905" and "costs nothing" is
 * the difference between a correct quote and one that bills a family nothing.
 *
 * **The VAT category is not a column here.** It used to be, and it read as a
 * property of the service — which is what the data model used to say and what
 * turned out to be wrong. The same service is necessity care for one customer
 * and comfort care for another, so the rate is chosen on the quote line, by the
 * person who knows which the customer is. A column here would state a fact
 * about the service that the next quote written against it may contradict.
 *
 * What the catalogue entry still carries is a *suggested* category, offered to
 * fill the field in when an operator picks the service. That is a default, not
 * a rule, and it is edited in the dialog rather than displayed as a column.
 *
 * The agency-wide rules — the default rate, the weekday and holiday surcharges
 * — are shown but **not editable here**. They live in the deployment's
 * configuration, because a change to what every service costs is a commercial
 * decision with a release behind it rather than a form somebody fills in on a
 * Tuesday. The caption says so; a read-only field that does not explain itself
 * reads as a bug.
 */
export function InterventionTypesPage() {
  const { t, i18n } = useTranslation();
  const catalogFilter = useEntityFilter(CATALOG_FILTER_SPEC);
  const { data: types, isLoading } = useInterventionTypes(true, catalogFilter.filter);
  const { data: rules } = usePricingRules();
  const [editing, setEditing] = useState<InterventionType | null>(null);
  const [creating, setCreating] = useState(false);

  const columns: GridColDef<InterventionType>[] = [
    { field: 'code', headerName: t('catalog.code'), width: 130 },
    { field: 'name', headerName: t('catalog.name'), flex: 1, minWidth: 180 },
    {
      field: 'base_hourly_rate_ht',
      headerName: t('catalog.hourlyRate'),
      width: 190,
      sortable: false,
      renderCell: (params) => {
        const own = params.row.base_hourly_rate_ht;
        const inherited = rules?.base_hourly_rate_ht ?? null;
        return own !== null ? (
          <Typography variant="body2" data-testid={`type-rate-${params.row.code}`}>
            {formatMoney(own, i18n.language)}
          </Typography>
        ) : (
          <Typography
            variant="body2"
            color="text.secondary"
            data-testid={`type-rate-${params.row.code}`}
          >
            {inherited ? formatMoney(inherited, i18n.language) : '—'} ·{' '}
            {t('catalog.agencyRate')}
          </Typography>
        );
      },
    },
    {
      field: 'is_active',
      headerName: t('catalog.status'),
      width: 130,
      sortable: false,
      renderCell: (params) => (
        <Chip
          size="small"
          variant={params.row.is_active ? 'filled' : 'outlined'}
          color={params.row.is_active ? 'success' : 'default'}
          label={t(params.row.is_active ? 'catalog.active' : 'catalog.retired')}
          data-testid={`type-status-${params.row.code}`}
        />
      ),
    },
    {
      field: 'actions',
      headerName: '',
      width: 140,
      sortable: false,
      renderCell: (params) => (
        <Button
          size="small"
          onClick={() => setEditing(params.row)}
          data-testid={`edit-type-${params.row.code}`}
        >
          {t('common.edit')}
        </Button>
      ),
    },
  ];

  return (
    <Stack spacing={3}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Typography variant="h1" sx={{ flexGrow: 1 }}>
          {t('catalog.title')}
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreating(true)}
          data-testid="new-type"
        >
          {t('catalog.add')}
        </Button>
      </Box>

      <EntityFilterBar
        state={catalogFilter}
        testId="catalog"
        searchLabel="catalog.searchFilter"
        tabField="service_category"
        tabs={CATALOG_TABS}
        details={CATALOG_DETAILS}
      />

      {/* ── What every entry is priced against ─────────────────────── */}
      <Card data-testid="pricing-rules">
        <CardContent>
          <Stack spacing={1.5}>
            <Typography variant="h3">{t('catalog.agencyRules')}</Typography>
            <Alert severity="info" data-testid="pricing-rules-readonly">
              {t('catalog.rulesAreConfiguration')}
            </Alert>

            <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  {t('catalog.agencyRate')}
                </Typography>
                <Typography data-testid="agency-rate">
                  {rules ? formatMoney(rules.base_hourly_rate_ht, i18n.language) : '—'}
                </Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  {t('catalog.weekdaySurcharges')}
                </Typography>
                <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                  {Object.entries(rules?.weekday_surcharges ?? {}).length === 0 ? (
                    <Typography variant="body2" data-testid="no-weekday-surcharge">
                      {t('catalog.noSurcharge')}
                    </Typography>
                  ) : (
                    Object.entries(rules?.weekday_surcharges ?? {}).map(
                      ([day, multiplier]) => (
                        <Chip
                          key={day}
                          size="small"
                          label={`${t(`catalog.day_${day}`, day)} ×${multiplier}`}
                          data-testid={`weekday-surcharge-${day}`}
                        />
                      ),
                    )
                  )}
                </Box>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  {t('catalog.holidaySurcharges')}
                </Typography>
                <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                  {(rules?.holiday_surcharges ?? []).length === 0 ? (
                    <Typography variant="body2" data-testid="no-holiday-surcharge">
                      {t('catalog.noSurcharge')}
                    </Typography>
                  ) : (
                    (rules?.holiday_surcharges ?? []).map((holiday) => (
                      <Chip
                        key={`${holiday.month}-${holiday.day}`}
                        size="small"
                        label={`${holiday.label} ×${holiday.surcharge}`}
                        data-testid={`holiday-surcharge-${holiday.month}-${holiday.day}`}
                      />
                    ))
                  )}
                </Box>
              </Box>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      <Box sx={{ height: 560 }}>
        <DataGrid
          rows={types ?? []}
          columns={columns}
          loading={isLoading}
          getRowId={(row) => row.id ?? row.code}
          disableRowSelectionOnClick
          initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
          pageSizeOptions={[25, 50, 100]}
          data-testid="catalog-grid"
        />
      </Box>

      <InterventionTypeDialog
        entry={editing}
        creating={creating}
        agencyRate={rules?.base_hourly_rate_ht ?? null}
        onClose={() => {
          setEditing(null);
          setCreating(false);
        }}
      />
    </Stack>
  );
}
