import { useTranslation } from 'react-i18next';
import Box from '@mui/material/Box';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { SkillType } from '@/api/types';

interface LineSkillsProps {
  /** Which line this belongs to, so the test ids stay distinct. */
  index: number;
  /** The line's own codes, or `null` when it inherits the catalogue entry. */
  value: string[] | null;
  /** What the chosen service requires, shown when the line inherits. */
  inherited: string[];
  /** Every skill the agency recognises. */
  catalogue: SkillType[];
  /** Called with the new value: `null` to inherit, an array to override. */
  onChange: (value: string[] | null) => void;
}

/**
 * The skills one quote line requires.
 *
 * @param props - The line index, its value, the inherited codes, the catalogue
 *   and the change handler.
 * @returns The rendered control.
 *
 * @remarks
 * The twin of {@link LineCertifications}, and a separate control rather than
 * more options in that one. The two requirements are satisfied from different
 * places — a manager records a qualification, an assistant declares a skill —
 * and the planner reports them as different reasons for leaving work unplaced.
 * One merged picker would produce the same plan and a worse diagnosis.
 *
 * **Three states, and the control exists to keep them apart.** `null` means
 * "whatever the service requires". An array means "these instead". And an
 * *empty* array means "this hour needs no skill at all". Collapsing the last
 * into `null` would silently reinstate a requirement the person writing the
 * quote had deliberately removed.
 *
 * A native `multiple` select, not MUI's: MUI renders a hidden input beside a
 * div that neither a keyboard nor the GUI campaign can operate.
 */
export function LineSkills({
  index,
  value,
  inherited,
  catalogue,
  onChange,
}: LineSkillsProps) {
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
            data-testid={`line-skills-inherit-${index}`}
          />
        }
        label={
          <Typography variant="body2">{t('skills.inheritsFromService')}</Typography>
        }
      />

      {inherits ? (
        <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
          {inherited.length === 0 ? (
            <Typography
              variant="caption"
              color="text.secondary"
              data-testid={`line-skills-none-${index}`}
            >
              {t('skills.none')}
            </Typography>
          ) : (
            inherited.map((code) => (
              <Chip
                key={code}
                size="small"
                label={labelOf(code)}
                data-testid={`line-skill-${index}-${code}`}
              />
            ))
          )}
        </Box>
      ) : (
        <TextField
          select
          size="small"
          label={t('skills.requiredBy')}
          value={value}
          onChange={(event) =>
            onChange(
              Array.from(
                (event.target as unknown as HTMLSelectElement).selectedOptions,
                (option) => option.value,
              ),
            )
          }
          helperText={t('skills.requiredHint')}
          slotProps={{
            select: { native: true, multiple: true },
            inputLabel: { shrink: true },
            htmlInput: { 'data-testid': `line-skills-${index}` },
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
