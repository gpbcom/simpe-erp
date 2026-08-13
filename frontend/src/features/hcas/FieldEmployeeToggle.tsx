import { useTranslation } from 'react-i18next';
import FormControlLabel from '@mui/material/FormControlLabel';
import Switch from '@mui/material/Switch';
import Tooltip from '@mui/material/Tooltip';
import { useUpdateEmployment } from '@/api/queries';
import type { Hca } from '@/api/types';

interface FieldEmployeeToggleProps {
  hca: Hca;
}

/**
 * Whether one assistant goes out on the rounds, changed where it is read.
 *
 * @param props - The row this cell belongs to.
 * @returns The rendered cell.
 *
 * @remarks
 * A component per row rather than a `renderCell` closure, because each row
 * needs its own mutation and a hook cannot be called inside a callback. The
 * cost is one query subscription per visible row, which the grid already pays
 * for its own state.
 *
 * **The label stays.** A bare switch answers "can I change this?" but not
 * "what is it?" at a glance, and this column is read far more often than it is
 * written — a manager scans it down twelve rows to see who is out this week.
 * It is also what the GUI campaign reads the cell by.
 *
 * The whole employment payload is sent, not just the flag, because the route
 * replaces all three fields. Sending the row's current contract and
 * qualifications back unchanged is what stops a toggle here from clearing
 * them — the same reason the account page sends the language back on every
 * save.
 *
 * No optimistic update: the switch follows the server's answer, so a refused
 * or failed change never leaves the grid claiming something the planner will
 * disagree with. The mutation invalidates `['planning']` as well as the
 * workforce, since who may be scheduled has just changed.
 */
export function FieldEmployeeToggle({ hca }: FieldEmployeeToggleProps) {
  const { t } = useTranslation();
  const update = useUpdateEmployment(hca.id);

  return (
    <Tooltip title={t('hcas.fieldEmployeeHint')}>
      <FormControlLabel
        sx={{ mr: 0 }}
        data-testid={`field-employee-${hca.id}`}
        control={
          <Switch
            size="small"
            checked={hca.field_employee}
            disabled={update.isPending}
            onChange={(event) =>
              update.mutate({
                contract_type: hca.contract_type,
                certifications: hca.certifications,
                field_employee: event.target.checked,
              })
            }
          />
        }
        label={t(hca.field_employee ? 'common.yes' : 'hcas.notFieldEmployee')}
      />
    </Tooltip>
  );
}
