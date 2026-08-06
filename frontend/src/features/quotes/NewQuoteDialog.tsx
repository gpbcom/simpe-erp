import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import DeleteIcon from '@mui/icons-material/Delete';
import { ApiError } from '@/api/client';
import { useCreateQuote, useCustomers, useInterventionTypes } from '@/api/queries';
import type { NewQuoteLine } from '@/api/types';

interface NewQuoteDialogProps {
  /** Whether the dialog is on screen. */
  open: boolean;
  /** Close it. */
  onClose: () => void;
}

/**
 * Build one empty line, dated a fortnight out.
 *
 * @returns A line with sensible defaults.
 *
 * @remarks
 * Defaults so the common case is one click: an hour of care, in the morning,
 * far enough ahead that the planner has somewhere to put it. A blank row would
 * make every quote five fields of typing before it says anything.
 */
function emptyLine(): NewQuoteLine {
  const day = new Date();
  day.setDate(day.getDate() + 14);
  return {
    name: '',
    intervention_type_id: '',
    // Necessity: most home-care hours are delivered under a care plan. A
    // starting point the operator must still look at, not an answer — the
    // field sits beside the service with the VAT rate it implies.
    service_category: 'necessity',
    service_date: day.toISOString().slice(0, 10),
    earliest_start: '09:00:00',
    latest_end: '12:00:00',
    duration_minutes: 60,
  };
}

/**
 * Write a new quote.
 *
 * @param props - Whether it is open, and how to close it.
 * @returns The rendered dialog.
 *
 * @remarks
 * **No amounts anywhere.** The server prices every line against the catalogue
 * when it stores the quote, and showing a total computed here would be a second
 * answer that disagrees with the stored one the first time a rate changes.
 *
 * Choosing a service fills the line's name from the catalogue entry. The name
 * is what the customer reads on the document, so it starts as the service's own
 * and stays editable for the visit that needs a word of explanation.
 */
export function NewQuoteDialog({ open, onClose }: NewQuoteDialogProps) {
  const { t } = useTranslation();
  const { data: customers } = useCustomers();
  const { data: types } = useInterventionTypes();
  const create = useCreateQuote();

  const [reference, setReference] = useState('');
  const [customerId, setCustomerId] = useState('');
  const [lines, setLines] = useState<NewQuoteLine[]>([emptyLine()]);
  const [error, setError] = useState<string | null>(null);

  const setLine = (index: number, changes: Partial<NewQuoteLine>) => {
    setLines((current) =>
      current.map((line, position) =>
        position === index ? { ...line, ...changes } : line,
      ),
    );
  };

  const chooseType = (index: number, typeId: string) => {
    const chosen = (types ?? []).find((entry) => entry.id === typeId);
    setLine(index, {
      intervention_type_id: typeId,
      // Only when the operator has not written their own: retyping over
      // somebody's wording every time they fix the service is worse than a
      // blank field.
      name: lines[index]?.name ? lines[index].name : (chosen?.name ?? ''),
      // The catalogue entry's category is a suggestion, not a rule. It is what
      // this service usually is; whether *this customer's* hours fall under a
      // care plan is something only the person writing the quote knows, and
      // they can still change it.
      service_category:
        chosen?.service_category ?? lines[index]?.service_category ?? 'necessity',
    });
  };

  const submit = async () => {
    setError(null);
    try {
      await create.mutateAsync({ reference, customer_id: customerId, lines });
      setReference('');
      setCustomerId('');
      setLines([emptyLine()]);
      onClose();
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 422
          ? t('quote.createInvalid')
          : t('common.error'),
      );
    }
  };

  const complete =
    reference.trim() !== '' &&
    customerId !== '' &&
    lines.length > 0 &&
    lines.every((line) => line.intervention_type_id !== '' && line.name.trim() !== '');

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{t('quote.newTitle')}</DialogTitle>
      <DialogContent data-testid="new-quote-dialog">
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? (
            <Alert severity="error" data-testid="new-quote-error">
              {error}
            </Alert>
          ) : null}

          <Stack direction="row" spacing={2}>
            <TextField
              label={t('quote.reference')}
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              required
              sx={{ flex: 1 }}
              inputProps={{ 'data-testid': 'new-quote-reference' }}
            />
            <TextField
              select
              label={t('quote.customer')}
              value={customerId}
              onChange={(event) => setCustomerId(event.target.value)}
              required
              sx={{ flex: 2 }}
              slotProps={{
                select: { native: true },
                inputLabel: { shrink: true },
                htmlInput: { 'data-testid': 'new-quote-customer' },
              }}
            >
              <option value="" />
              {(customers ?? []).map((customer) => (
                <option key={customer.id} value={customer.id ?? ''}>
                  {customer.first_name} {customer.last_name}
                </option>
              ))}
            </TextField>
          </Stack>

          <Divider />

          {lines.map((line, index) => (
            <Stack
              key={index}
              direction="row"
              spacing={1}
              alignItems="center"
              data-testid={`new-quote-line-${index}`}
            >
              <TextField
                select
                label={t('quote.service')}
                value={line.intervention_type_id}
                onChange={(event) => chooseType(index, event.target.value)}
                sx={{ flex: 2 }}
                slotProps={{
                  select: { native: true },
                  inputLabel: { shrink: true },
                  htmlInput: { 'data-testid': `new-quote-type-${index}` },
                }}
              >
                <option value="" />
                {(types ?? []).map((type) => (
                  <option key={type.id} value={type.id ?? ''}>
                    {type.name}
                  </option>
                ))}
              </TextField>
              <TextField
                select
                label={t('quote.vatCategory')}
                value={line.service_category}
                onChange={(event) =>
                  setLine(index, {
                    service_category: event.target.value as 'necessity' | 'comfort',
                  })
                }
                sx={{ flex: 1.5 }}
                helperText={t(`quote.vatFor_${line.service_category}`)}
                slotProps={{
                  select: { native: true },
                  inputLabel: { shrink: true },
                  htmlInput: { 'data-testid': `new-quote-category-${index}` },
                }}
              >
                <option value="necessity">{t('catalog.category_necessity')}</option>
                <option value="comfort">{t('catalog.category_comfort')}</option>
              </TextField>
              <TextField
                label={t('quote.lineName')}
                value={line.name}
                onChange={(event) => setLine(index, { name: event.target.value })}
                sx={{ flex: 2 }}
                inputProps={{ 'data-testid': `new-quote-name-${index}` }}
              />
              <TextField
                type="date"
                label={t('quote.day')}
                value={line.service_date}
                onChange={(event) =>
                  setLine(index, { service_date: event.target.value })
                }
                slotProps={{ inputLabel: { shrink: true } }}
                inputProps={{ 'data-testid': `new-quote-date-${index}` }}
              />
              <TextField
                type="number"
                label={t('quote.minutes')}
                value={line.duration_minutes}
                onChange={(event) =>
                  setLine(index, { duration_minutes: Number(event.target.value) })
                }
                sx={{ width: 110 }}
                inputProps={{
                  'data-testid': `new-quote-minutes-${index}`,
                  min: 15,
                  step: 15,
                }}
              />
              <IconButton
                onClick={() =>
                  setLines((current) =>
                    current.filter((_, position) => position !== index),
                  )
                }
                // The last line is not removable: a quote with no lines is not
                // a quote, and the server refuses it.
                disabled={lines.length === 1}
                data-testid={`new-quote-remove-${index}`}
              >
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Stack>
          ))}

          <Button
            onClick={() => setLines((current) => [...current, emptyLine()])}
            data-testid="new-quote-add-line"
          >
            {t('quote.addLine')}
          </Button>

          <Typography variant="body2" color="text.secondary">
            {t('quote.pricedOnSave')}
          </Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} data-testid="new-quote-cancel">
          {t('common.cancel')}
        </Button>
        <Button
          variant="contained"
          onClick={submit}
          disabled={!complete || create.isPending}
          data-testid="new-quote-submit"
        >
          {t('quote.create')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
