import { useTranslation } from 'react-i18next';
import Box from '@mui/material/Box';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { CertificationType } from '@/api/types';

interface LineCertificationsProps {
  index: number;
  value: string[] | null;
  inherited: string[];
  catalogue: CertificationType[];
  onChange: (value: string[] | null) => void;
}

/**
 * The qualifications one quote line requires.
 *
 * @param props - The line index, its value, the inherited codes, the catalogue
 *   and the change handler.
 * @returns The rendered control.
 *
 * @remarks
 * **Three states, and the control exists to keep them apart.** `null` means
 * "whatever the service requires"; an array means "these instead"; and an
 * *empty* array means "this hour needs no qualification at all". The last is a
 * real answer — the catalogue's default is occasionally wrong for one customer
 * — and collapsing it into `null` would silently reinstate a requirement the
 * person writing the quote had deliberately removed. So the checkbox and the
 * list are separate controls rather than one list whose emptiness means both.
 *
 * While the line inherits, the inherited codes are shown as chips rather than
 * hidden. "This visit needs DEAES" is something the operator should see before
 * the planner tells them nobody is qualified for it.
 *
 * A native `multiple` select, not MUI's: MUI renders a hidden input beside a
 * div that neither a keyboard nor the GUI campaign can operate.
 */
export function LineCertifications({
  index,
  value,
  inherited,
  catalogue,
  onChange,
}: LineCertificationsProps) {
  const { t } = useTranslation();
  const inherits = value === null;
  const labelOf = (code: string) =>
    catalogue.find((entry) => entry.code === code)?.label ?? code;

  return (
    <Stack spacing={0.5}>
      <FormControlLabel
        control={
          <Checkbox
            size="small"
            checked={inherits}
            onChange={(event) => onChange(event.target.checked ? null : [...inherited])}
            data-testid={`line-certifications-inherit-${index}`}
          />
        }
        label={
          <Typography variant="body2">
            {t('certifications.inheritsFromService')}
          </Typography>
        }
      />

      {inherits ? (
        <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
          {inherited.length === 0 ? (
            <Typography
              variant="caption"
              color="text.secondary"
              data-testid={`line-certifications-none-${index}`}
            >
              {t('certifications.none')}
            </Typography>
          ) : (
            inherited.map((code) => (
              <Chip
                key={code}
                size="small"
                label={labelOf(code)}
                data-testid={`line-certification-${index}-${code}`}
              />
            ))
          )}
        </Box>
      ) : (
        <TextField
          select
          size="small"
          label={t('certifications.requiredBy')}
          value={value}
          onChange={(event) =>
            onChange(
              Array.from(
                (event.target as unknown as HTMLSelectElement).selectedOptions,
                (option) => option.value,
              ),
            )
          }
          helperText={t('certifications.requiredHint')}
          slotProps={{
            select: { native: true, multiple: true },
            inputLabel: { shrink: true },
            htmlInput: { 'data-testid': `line-certifications-${index}` },
          }}
        >
          {catalogue.map((entry) => (
            <option key={entry.code} value={entry.code}>
              {entry.label}
            </option>
          ))}
        </TextField>
      )}
    </Stack>
  );
}
