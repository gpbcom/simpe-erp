import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import Grid from '@mui/material/Grid2';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import {
  useCertificationTypes,
  useInterventionTypes,
  usePricingRules,
  useReplaceQuoteLines,
  useSkillTypes,
} from '@/api/queries';
import { QuoteStatusChip } from './QuoteStatusChip';
import { LineCertifications } from './LineCertifications';
import { LineSkills } from './LineSkills';
import { formatMoney } from '@/utils/format';
import type { NewQuoteLine, Quote } from '@/api/types';

/** A line while it is being edited: every field a string, as inputs give them. */
interface DraftLine {
  name: string;
  intervention_type_id: string;
  service_category: 'necessity' | 'comfort';
  service_date: string;
  earliest_start: string;
  latest_end: string;
  duration_minutes: string;
  /** The line's own qualifications, or `null` to inherit the catalogue entry. */
  required_certification_codes: string[] | null;
  /** The line's own skills, or `null` to inherit the catalogue entry. */
  required_skill_codes: string[] | null;
}

/**
 * The fields a text input writes.
 *
 * The two requirement lists are edited by their own controls, which hand back
 * an array or `null`. Letting {@link QuoteEditorDialog}'s generic `update` take
 * their keys would let a string be written into a field the server reads as a
 * list of codes.
 */
type DraftTextField = Exclude<
  keyof DraftLine,
  'required_certification_codes' | 'required_skill_codes'
>;

/** What a fresh line starts as: a morning slot, one hour long. */
const NEW_LINE: DraftLine = {
  name: '',
  intervention_type_id: '',
  // Necessity, because most home-care hours are delivered under a care plan.
  // It is a starting point the operator must still look at, not an answer:
  // the field is on screen beside the service, with the rate it implies.
  service_category: 'necessity',
  service_date: '',
  earliest_start: '09:00',
  latest_end: '12:00',
  duration_minutes: '60',
  // Inherit, on both counts. A new line requires whatever its service does
  // until somebody deliberately says otherwise; starting at `[]` would mean
  // "needs nothing", which silently drops the catalogue's own requirement.
  required_certification_codes: null,
  required_skill_codes: null,
};

interface QuoteEditorDialogProps {
  /** The quote to edit, or `null` when the dialog is closed. */
  quote: Quote | null;
  /**
   * Whether to save through the manager route or the self-service one.
   *
   * `manager` may edit any quote in the agency; `own` is narrowed to the
   * caller's own by the server, against the stored author.
   */
  scope: 'manager' | 'own';
  /** Called when the dialog should close. */
  onClose: () => void;
}

/**
 * Rewrite the services on a draft quote, and reprice it.
 *
 * @param props - The quote, the saving scope, and the close handler.
 * @returns The rendered dialog.
 *
 * @remarks
 * **One dialog for both roles.** A manager editing any quote and an assistant
 * editing their own do exactly the same thing to it — the difference is which
 * quotes they can open and which endpoint saves it, not what the form contains.
 * Two dialogs would be two places for the line rules to drift apart.
 *
 * **Prices are not computed here.** The form collects services, dates and
 * durations; the server prices them against the catalog, applying the weekday
 * and holiday surcharges and the VAT rate the service category carries. A
 * total calculated in the browser would be a second pricing implementation,
 * and the one the customer is billed from is the other one.
 *
 * **Only the lines are sent.** The payload carries no customer and no status,
 * so editing cannot reassign the quote or accept it on the customer's behalf.
 *
 * Only a **draft** can be opened. A sent quote must stay what the customer was
 * shown, and one awaiting validation is frozen so a manager rules on the
 * figures they were actually given.
 */
export function QuoteEditorDialog({ quote, scope, onClose }: QuoteEditorDialogProps) {
  const { t, i18n } = useTranslation();
  const { data: types } = useInterventionTypes();
  const { data: rules } = usePricingRules();
  const { data: catalogue } = useCertificationTypes();
  const { data: skillCatalogue } = useSkillTypes();
  const replaceLines = useReplaceQuoteLines(scope);
  const [lines, setLines] = useState<DraftLine[]>([]);

  /**
   * Label the VAT a category implies, using the server's own rate.
   *
   * The percentage is read from the published pricing rules rather than
   * written into a translation string. A rate spelled out in `fr.json` is a
   * second copy of a figure the tax code sets, and the copy on screen would be
   * the one an operator trusted while the invoice used the other.
   */
  const vatHint = (category: 'necessity' | 'comfort'): string => {
    const rate = rules?.vat_rates[category];
    if (rate === undefined) return '';
    return t('quote.vatRateHint', {
      rate: (Number(rate) * 100).toLocaleString(i18n.language, {
        maximumFractionDigits: 1,
      }),
    });
  };

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!quote) return;
    setError(null);
    setLines(
      quote.lines.map((line) => ({
        name: line.name,
        intervention_type_id: line.intervention_type_id,
        service_category: line.service_category,
        service_date: line.service_date,
        earliest_start: line.earliest_start.slice(0, 5),
        latest_end: line.latest_end.slice(0, 5),
        duration_minutes: String(line.duration_minutes),
        required_certification_codes: line.required_certification_codes,
        required_skill_codes: line.required_skill_codes,
      })),
    );
  }, [quote]);

  const update = (index: number, key: DraftTextField, value: string) => {
    setLines(lines.map((line, i) => (i === index ? { ...line, [key]: value } : line)));
  };

  /**
   * Name a line after the catalog entry it sells, unless it has been renamed.
   *
   * The name is what the customer reads on the printed quote, so it stays
   * editable — but an operator picking "Aide à la toilette" should not then
   * have to type it out.
   */
  const chooseType = (index: number, typeId: string) => {
    const entry = (types ?? []).find((candidate) => candidate.id === typeId);
    setLines(
      lines.map((line, i) =>
        i === index
          ? {
              ...line,
              intervention_type_id: typeId,
              name: line.name.trim() ? line.name : (entry?.name ?? ''),
              // The catalogue entry's own category is offered as a suggestion,
              // never imposed: it is what this service usually is, and the
              // operator is the one who knows whether this customer's hours are
              // under a care plan. The field stays editable afterwards.
              service_category: entry?.service_category ?? line.service_category,
              // Both requirement overrides drop back to "inherit". They were an
              // override of the *previous* service's requirement, and carrying
              // them across would silently demand a diploma the new service
              // never asked for — or, worse, keep an empty override and drop the
              // one it does.
              required_certification_codes: null,
              required_skill_codes: null,
            }
          : line,
      ),
    );
  };

  const invalid = lines.some(
    (line) =>
      !line.name.trim() ||
      !line.intervention_type_id ||
      !line.service_date ||
      Number(line.duration_minutes) <= 0,
  );

  const save = () => {
    if (!quote?.id) return;
    setError(null);
    const payload: NewQuoteLine[] = lines.map((line) => ({
      name: line.name.trim(),
      intervention_type_id: line.intervention_type_id,
      service_category: line.service_category,
      service_date: line.service_date,
      earliest_start: `${line.earliest_start}:00`,
      latest_end: `${line.latest_end}:00`,
      duration_minutes: Number(line.duration_minutes),
      required_certification_codes: line.required_certification_codes,
      required_skill_codes: line.required_skill_codes,
    }));
    replaceLines.mutate(
      { quoteId: quote.id, lines: payload },
      {
        onSuccess: onClose,
        onError: (cause) =>
          setError(cause instanceof Error ? cause.message : t('common.error')),
      },
    );
  };

  // The stored totals, not a recomputation. They are what the server priced,
  // and they go stale the moment a line is touched — which the hint says.
  const storedTotal = (quote?.lines ?? []).reduce(
    (running, line) => running + Number(line.total_ttc ?? 0),
    0,
  );
  const dirty =
    quote !== null &&
    (lines.length !== quote.lines.length ||
      lines.some(
        (line, index) =>
          line.name !== quote.lines[index]?.name ||
          line.intervention_type_id !== quote.lines[index]?.intervention_type_id ||
          line.service_category !== quote.lines[index]?.service_category ||
          line.service_date !== quote.lines[index]?.service_date ||
          Number(line.duration_minutes) !== quote.lines[index]?.duration_minutes ||
          // Compared as JSON because the three states — inherit, override to
          // these, override to nothing — are `null`, an array and an empty
          // array. `!==` on two arrays is always true, which would leave the
          // save button lit on a quote nobody had touched.
          JSON.stringify(line.required_certification_codes) !==
            JSON.stringify(quote.lines[index]?.required_certification_codes ?? null) ||
          JSON.stringify(line.required_skill_codes) !==
            JSON.stringify(quote.lines[index]?.required_skill_codes ?? null),
      ));

  return (
    <Dialog
      open={quote !== null}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      data-testid="quote-editor"
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <span>
          {t('quote.edit')} · {quote?.reference}
        </span>
        {quote ? <QuoteStatusChip status={quote.status} /> : null}
      </DialogTitle>

      <DialogContent dividers>
        <Stack spacing={2}>
          {error ? (
            <Alert severity="error" data-testid="quote-editor-error">
              {error}
            </Alert>
          ) : null}

          {lines.length === 0 ? (
            <Alert severity="info" data-testid="quote-editor-empty">
              {t('quote.noLineYet')}
            </Alert>
          ) : null}

          {lines.map((line, index) => (
            <Box key={index} data-testid={`quote-line-${index}`}>
              <Grid container spacing={1.5} alignItems="center">
                <Grid size={{ xs: 12, md: 2 }}>
                  <TextField
                    select
                    label={t('quote.service')}
                    value={line.intervention_type_id}
                    onChange={(event) => chooseType(index, event.target.value)}
                    slotProps={{
                      select: { native: true },
                      inputLabel: { shrink: true },
                      htmlInput: { 'data-testid': `line-type-${index}` },
                    }}
                  >
                    <option value="" />
                    {(types ?? [])
                      .filter((entry) => entry.is_active)
                      .map((entry) => (
                        <option key={entry.id} value={entry.id ?? ''}>
                          {entry.name}
                        </option>
                      ))}
                  </TextField>
                </Grid>
                <Grid size={{ xs: 12, md: 2 }}>
                  <TextField
                    select
                    label={t('quote.vatCategory')}
                    value={line.service_category}
                    onChange={(event) =>
                      update(index, 'service_category', event.target.value)
                    }
                    helperText={vatHint(line.service_category)}
                    slotProps={{
                      select: { native: true },
                      inputLabel: { shrink: true },
                      htmlInput: { 'data-testid': `line-category-${index}` },
                    }}
                  >
                    <option value="necessity">{t('catalog.category_necessity')}</option>
                    <option value="comfort">{t('catalog.category_comfort')}</option>
                  </TextField>
                </Grid>
                <Grid size={{ xs: 12, md: 2 }}>
                  <TextField
                    label={t('quote.lineName')}
                    value={line.name}
                    onChange={(event) => update(index, 'name', event.target.value)}
                    inputProps={{ 'data-testid': `line-name-${index}` }}
                  />
                </Grid>
                <Grid size={{ xs: 6, md: 2 }}>
                  <TextField
                    type="date"
                    label={t('quote.serviceDate')}
                    value={line.service_date}
                    onChange={(event) =>
                      update(index, 'service_date', event.target.value)
                    }
                    InputLabelProps={{ shrink: true }}
                    inputProps={{ 'data-testid': `line-date-${index}` }}
                  />
                </Grid>
                <Grid size={{ xs: 3, md: 1 }}>
                  <TextField
                    type="time"
                    label={t('quote.from')}
                    value={line.earliest_start}
                    onChange={(event) =>
                      update(index, 'earliest_start', event.target.value)
                    }
                    InputLabelProps={{ shrink: true }}
                    inputProps={{ 'data-testid': `line-start-${index}` }}
                  />
                </Grid>
                <Grid size={{ xs: 3, md: 1 }}>
                  <TextField
                    type="time"
                    label={t('quote.to')}
                    value={line.latest_end}
                    onChange={(event) =>
                      update(index, 'latest_end', event.target.value)
                    }
                    InputLabelProps={{ shrink: true }}
                    inputProps={{ 'data-testid': `line-end-${index}` }}
                  />
                </Grid>
                <Grid size={{ xs: 9, md: 1.5 }}>
                  <TextField
                    type="number"
                    label={t('quote.duration')}
                    value={line.duration_minutes}
                    onChange={(event) =>
                      update(index, 'duration_minutes', event.target.value)
                    }
                    inputProps={{
                      min: 15,
                      step: 15,
                      'data-testid': `line-duration-${index}`,
                    }}
                  />
                </Grid>
                <Grid size={{ xs: 3, md: 0.5 }}>
                  <Tooltip title={t('common.remove')}>
                    <IconButton
                      onClick={() => setLines(lines.filter((_l, i) => i !== index))}
                      data-testid={`remove-line-${index}`}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Grid>
                <Grid size={12}>
                  <LineCertifications
                    index={index}
                    value={line.required_certification_codes}
                    inherited={
                      (types ?? []).find(
                        (entry) => entry.id === line.intervention_type_id,
                      )?.required_certification_codes ?? []
                    }
                    catalogue={catalogue ?? []}
                    onChange={(codes) =>
                      setLines(
                        lines.map((entry, position) =>
                          position === index
                            ? { ...entry, required_certification_codes: codes }
                            : entry,
                        ),
                      )
                    }
                  />
                </Grid>
                <Grid size={12}>
                  <LineSkills
                    index={index}
                    value={line.required_skill_codes}
                    inherited={
                      (types ?? []).find(
                        (entry) => entry.id === line.intervention_type_id,
                      )?.required_skill_codes ?? []
                    }
                    catalogue={skillCatalogue ?? []}
                    onChange={(codes) =>
                      setLines(
                        lines.map((entry, position) =>
                          position === index
                            ? { ...entry, required_skill_codes: codes }
                            : entry,
                        ),
                      )
                    }
                  />
                </Grid>
              </Grid>
              <Divider sx={{ mt: 1.5 }} />
            </Box>
          ))}

          <Box>
            <Button
              startIcon={<AddIcon />}
              onClick={() => setLines([...lines, { ...NEW_LINE }])}
              data-testid="add-line"
            >
              {t('quote.addLine')}
            </Button>
          </Box>
        </Stack>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2 }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="caption" color="text.secondary">
            {t('quote.storedTotal')}:{' '}
            {formatMoney(storedTotal.toFixed(2), i18n.language)}
          </Typography>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: 'block' }}
            data-testid="repricing-hint"
          >
            {t('quote.pricedOnSave')}
          </Typography>
        </Box>
        <Button onClick={onClose} data-testid="cancel-quote-edit">
          {t('common.cancel')}
        </Button>
        <Button
          variant="contained"
          onClick={save}
          disabled={invalid || !dirty || replaceLines.isPending}
          data-testid="save-quote-lines"
        >
          {t('common.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
