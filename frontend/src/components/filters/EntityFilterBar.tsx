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
import type { EntityFilterState } from './entityFilter';
export interface FilterTab {
  key: string;
  value?: string;
  label: string;
}

/** One control folded away behind "more filters". */
export interface FilterDetail {
  field: string;
  label: string;
  kind: 'text' | 'flag' | 'choice';
  /**
   * For a `flag`, the two labels; for a `choice`, one entry per value.
   *
   * @remarks
   * A flag's options are given rather than assumed, because "yes" and "no" read
   * differently per field: *located* and *not located* says more than *true*
   * and *false* on an address that failed to geocode.
   */
  options?: { value: string. Label: string }[];
}

interface EntityFilterBarProps {
  state: EntityFilterState;
  testId: string;
  searchLabel: string;
  tabField?: string;
  tabs?: FilterTab[];
  details?: FilterDetail[];
}

/**
 * Everything that narrows one list, drawn the same way on every screen.
 *
 * @param props - The filter state and this screen's controls.
 * @returns The rendered bar.
 *
 * @remarks
 * **One bar for seven screens, because the gesture is the same everywhere.** A
 * manager narrowing a list of assistants is doing what they do to the customer
 * book. Two screens that answer the same question with differently-shaped
 * controls are two screens somebody has to learn.
 *
 * The detail filters are folded away. Six boxes open at once say the screen is
 * complicated. The one or two used every day stay in the open, and the button
 * says how many of the others are on — so a folded filter can never narrow a
 * list invisibly.
 *
 * Flags are native selects with three options rather than checkboxes, because
 * they have three states. A checkbox cannot say "only those *without* one",
 * which is exactly the question that finds the records somebody forgot.
 */
export function EntityFilterBar({
  state,
  testId,
  searchLabel,
  tabField,
  tabs,
  details = [],
}: EntityFilterBarProps) {
  const { t } = useTranslation();
  const { draft, setText, setChoice, setFlag, reset, isFiltered } = state;
  const [expanded, setExpanded] = useState(false);

  const detailCount = details.filter(
    (entry) => draft[entry.field] !== undefined && draft[entry.field] !== '',
  ).length;

  const tab = Math.max(
    0,
    tabs && tabField ? tabs.findIndex((entry) => entry.value === draft[tabField]) : 0,
  );

  const toFlag = (value: string): boolean | undefined =>
    value === '' ? undefined : value === 'true';

  const fromValue = (value: FilterValueOf): string =>
    value === undefined ? '' : String(value);

  return (
    <Stack spacing={2}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        alignItems={{ sm: 'center' }}
      >
        <TextField
          placeholder={t(searchLabel)}
          value={(draft.search as string | undefined) ?? ''}
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
            htmlInput: { 'data-testid': `${testId}-search` },
          }}
        />
        {details.length > 0 ? (
          <Button
            size="small"
            onClick={() => setExpanded((open) => !open)}
            endIcon={expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            data-testid={`toggle-${testId}-filters`}
          >
            {detailCount > 0
              ? t('filters.moreFiltersCount', { count: detailCount })
              : t('filters.moreFilters')}
          </Button>
        ) : null}
        {isFiltered ? (
          <Button size="small" onClick={reset} data-testid={`clear-${testId}-filters`}>
            {t('filters.clearFilters')}
          </Button>
        ) : null}
      </Stack>

      {tabs && tabField ? (
        <Tabs
          value={tab}
          onChange={(_event, next: number) => setChoice(tabField, tabs[next]?.value)}
          variant="scrollable"
          scrollButtons="auto"
          data-testid={`${testId}-tabs`}
        >
          {tabs.map((entry) => (
            <Tab
              key={entry.key}
              label={t(entry.label)}
              data-testid={`${testId}-tab-${entry.key}`}
            />
          ))}
        </Tabs>
      ) : null}

      <Collapse in={expanded} unmountOnExit>
        <Box data-testid={`${testId}-filters`}>
          <Grid container spacing={2}>
            {details.map((entry) => (
              <Grid key={entry.field} size={{ xs: 12, sm: 6, md: 3 }}>
                <TextField
                  select={entry.kind !== 'text'}
                  fullWidth
                  size="small"
                  label={t(entry.label)}
                  value={fromValue(draft[entry.field])}
                  onChange={(event) => {
                    if (entry.kind === 'text') {
                      setText(entry.field, event.target.value);
                    } else if (entry.kind === 'flag') {
                      setFlag(entry.field, toFlag(event.target.value));
                    } else {
                      setChoice(entry.field, event.target.value || undefined);
                    }
                  }}
                  slotProps={{
                    ...(entry.kind === 'text' ? {} : { select: { native: true } }),
                    inputLabel: { shrink: true },
                    htmlInput: { 'data-testid': `${testId}-filter-${entry.field}` },
                  }}
                >
                  {entry.kind === 'text'
                    ? null
                    : [
                        <option key="" value="">
                          {t('filters.any')}
                        </option>,
                        ...(entry.options ?? []).map((option) => (
                          <option key={option.value} value={option.value}>
                            {t(option.label)}
                          </option>
                        )),
                      ]}
                </TextField>
              </Grid>
            ))}
          </Grid>
        </Box>
      </Collapse>
    </Stack>
  );
}

type FilterValueOf = string | boolean | undefined;
