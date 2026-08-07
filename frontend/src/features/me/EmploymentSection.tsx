import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import FormControlLabel from '@mui/material/FormControlLabel';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import DeleteIcon from '@mui/icons-material/Delete';
import LockIcon from '@mui/icons-material/Lock';
import { useCertificationTypes, useUpdateEmployment } from '@/api/queries';
import { AppIcon } from '@/components/icons/AppIcon';
import type { Certification, ContractType, Hca } from '@/api/types';

/** The contract types the agency employs on. */
const CONTRACTS: ContractType[] = ['cdi', 'cdd', 'interim', 'internship'];

interface EmploymentSectionProps {
  /** The record being shown. */
  profile: Hca;
  /**
   * Whether the caller may change these two fields.
   *
   * True only for a manager or an administrator. An assistant sees the same
   * values, locked.
   */
  editable: boolean;
}

/**
 * Contract type and qualifications — the two fields an assistant does not own.
 *
 * @param props - The record, and whether the caller may edit it.
 * @returns The rendered section.
 *
 * @remarks
 * **Both are always visible.** Hiding them would answer "what am I qualified
 * for?" with silence, which is the question an assistant most often opens this
 * page to settle. What changes with the role is whether they can be edited.
 *
 * When they cannot, they render as **locked chips with a tooltip naming who
 * owns them** rather than as disabled inputs. A disabled input says "you cannot
 * type here"; a locked chip says who to ask, which is the difference between a
 * confused assistant and one who knows what to do next.
 *
 * When they can, saving goes through `PATCH /api/v1/hcas/{id}/employment` — the
 * manager-gated route that already exists — rather than through the
 * self-service payload, which deliberately has no such fields. A manager
 * editing their own record passes exactly the check they would for anybody
 * else's.
 */
export function EmploymentSection({ profile, editable }: EmploymentSectionProps) {
  const { t } = useTranslation();
  const update = useUpdateEmployment(profile.id);
  const [contract, setContract] = useState<ContractType>(profile.contract_type);
  const [certifications, setCertifications] = useState<Certification[]>(
    profile.certifications,
  );
  const [added, setAdded] = useState('');
  const [fieldEmployee, setFieldEmployee] = useState(profile.field_employee);
  const { data: catalogue } = useCertificationTypes();

  useEffect(() => {
    setContract(profile.contract_type);
    setCertifications(profile.certifications);
    setFieldEmployee(profile.field_employee);
  }, [profile]);

  // Only what is not already held, so the picker cannot add a duplicate the
  // server would store twice and the planner would read once.
  const available = (catalogue ?? []).filter(
    (entry) => !certifications.some((held) => held.code === entry.code),
  );

  const dirty =
    contract !== profile.contract_type ||
    fieldEmployee !== profile.field_employee ||
    certifications.length !== profile.certifications.length ||
    certifications.some(
      (entry, index) => entry.code !== profile.certifications[index]?.code,
    );

  return (
    <Card data-testid="employment-section">
      <CardContent>
        <Stack spacing={2}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="h3" sx={{ flexGrow: 1 }}>
              {t('hca.employment')}
            </Typography>
            {!editable ? (
              <Tooltip title={t('hca.managedByManager')}>
                <Chip icon={<LockIcon />} label={t('hca.readOnly')} size="small" />
              </Tooltip>
            ) : null}
          </Box>

          {/* Contract type */}
          <Box>
            <Typography variant="caption" color="text.secondary">
              {t('hca.contractType')}
            </Typography>
            {editable ? (
              <TextField
                select
                value={contract}
                onChange={(event) => setContract(event.target.value as ContractType)}
                sx={{ mt: 0.5 }}
                inputProps={{ 'data-testid': 'contract-type-select' }}
              >
                {CONTRACTS.map((option) => (
                  <MenuItem key={option} value={option}>
                    {t(`hca.contract_${option}`)}
                  </MenuItem>
                ))}
              </TextField>
            ) : (
              <Box sx={{ mt: 0.5 }}>
                <Tooltip title={t('hca.managedByManager')}>
                  <Chip
                    icon={<LockIcon />}
                    label={t(`hca.contract_${profile.contract_type}`)}
                    data-testid="contract-type"
                  />
                </Tooltip>
              </Box>
            )}
          </Box>

          {/* On the rounds, or not */}
          <Box>
            <Typography variant="caption" color="text.secondary">
              {t('hcas.fieldEmployee')}
            </Typography>
            {editable ? (
              <Box>
                <FormControlLabel
                  control={
                    <Switch
                      checked={fieldEmployee}
                      onChange={(event) => setFieldEmployee(event.target.checked)}
                      // The same identifier as the locked chip below, on
                      // purpose: one name for "the field employee control",
                      // whichever half of the screen rendered it. A test
                      // tells them apart by looking *inside* — this one
                      // wraps a real checkbox, and a chip does not.
                      data-testid="field-employee"
                    />
                  }
                  label={t(fieldEmployee ? 'common.yes' : 'common.no')}
                />
                <Typography variant="caption" color="text.secondary" display="block">
                  {t('hcas.fieldEmployeeHint')}
                </Typography>
              </Box>
            ) : (
              <Box sx={{ mt: 0.5 }}>
                <Tooltip title={t('hca.managedByManager')}>
                  <Chip
                    icon={<LockIcon />}
                    label={t(
                      profile.field_employee
                        ? 'hcas.fieldEmployee'
                        : 'hcas.notFieldEmployee',
                    )}
                    data-testid="field-employee"
                  />
                </Tooltip>
              </Box>
            )}
          </Box>

          {/* Qualifications */}
          <Box>
            <Typography variant="caption" color="text.secondary">
              {t('hca.certifications')}
            </Typography>
            <Stack spacing={1} sx={{ mt: 0.5 }} data-testid="certifications">
              {certifications.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  {t('hca.noCertification')}
                </Typography>
              ) : (
                certifications.map((certification, index) => (
                  <Box
                    key={`${certification.name}-${index}`}
                    sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
                  >
                    <Tooltip
                      title={editable ? '' : t('hca.managedByManager')}
                      disableHoverListener={editable}
                    >
                      <Chip
                        icon={
                          editable ? <AppIcon name="certification" /> : <LockIcon />
                        }
                        label={certification.name}
                        sx={{ flexGrow: 1, justifyContent: 'flex-start' }}
                      />
                    </Tooltip>
                    {editable ? (
                      <IconButton
                        size="small"
                        onClick={() =>
                          setCertifications(
                            certifications.filter((_e, i) => i !== index),
                          )
                        }
                        data-testid={`remove-own-certification-${index}`}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    ) : null}
                  </Box>
                ))
              )}

              {editable ? (
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <TextField
                    select
                    label={t('hca.addCertification')}
                    value={added}
                    onChange={(event) => setAdded(event.target.value)}
                    sx={{ flexGrow: 1 }}
                    slotProps={{
                      select: { native: true },
                      inputLabel: { shrink: true },
                      htmlInput: { 'data-testid': 'own-new-certification' },
                    }}
                  >
                    <option value="" />
                    {available.map((entry) => (
                      <option key={entry.code} value={entry.code}>
                        {entry.label}
                      </option>
                    ))}
                  </TextField>
                  <Button
                    onClick={() => {
                      const chosen = available.find((entry) => entry.code === added);
                      if (!chosen) return;
                      setCertifications([
                        ...certifications,
                        {
                          name: chosen.label,
                          code: chosen.code,
                          issuer: null,
                          obtained_on: null,
                          expires_on: null,
                        },
                      ]);
                      setAdded('');
                    }}
                    data-testid="own-add-certification"
                  >
                    +
                  </Button>
                </Box>
              ) : null}
            </Stack>
          </Box>

          {editable ? (
            <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Button
                variant="contained"
                disabled={!dirty || update.isPending}
                onClick={() =>
                  update.mutate({
                    contract_type: contract,
                    certifications,
                    field_employee: fieldEmployee,
                  })
                }
                data-testid="save-employment"
              >
                {t('common.save')}
              </Button>
            </Box>
          ) : null}
        </Stack>
      </CardContent>
    </Card>
  );
}
