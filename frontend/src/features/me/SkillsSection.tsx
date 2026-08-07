import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import DeleteIcon from '@mui/icons-material/Delete';
import { useDeclareMySkill, useSkillTypes, useWithdrawMySkill } from '@/api/queries';
import { AppIcon } from '@/components/icons/AppIcon';
import type { Hca } from '@/api/types';

interface SkillsSectionProps {
  /** The record being shown. */
  profile: Hca;
}

/**
 * The skills an assistant declares about themselves.
 *
 * @param props - The record.
 * @returns The rendered section.
 *
 * @remarks
 * **The one planner-visible thing on this page its owner may write**, and the
 * reason it sits beside {@link EmploymentSection} rather than inside it. What
 * somebody was *awarded* is a manager's record — an assistant who could grant
 * themselves a diploma could be routed to work they are not trained for. What
 * they *can do* is their own: an assistant unable to say they speak Portuguese
 * is one the agency does not know it has.
 *
 * **A declaration takes effect at once, and says so.** There is no approval
 * step; every manager and administrator is notified instead, and any of them
 * can withdraw it. The alert says that plainly, because a control that silently
 * widens what you may be sent to is one people use nervously — and the answer
 * to "will somebody check this?" is yes, afterwards.
 *
 * The catalogue is a native select of what the agency recognises. A skill with
 * no code matches nothing, so this offers only coded ones: a free-text skill
 * would be a record nobody could require, which is a worse outcome than being
 * asked to have the catalogue extended.
 */
export function SkillsSection({ profile }: SkillsSectionProps) {
  const { t } = useTranslation();
  const { data: catalogue } = useSkillTypes();
  const declare = useDeclareMySkill();
  const withdraw = useWithdrawMySkill();
  const [chosen, setChosen] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Only what the assistant has not already declared. Offering a skill twice
  // invites a duplicate row that satisfies exactly the same requirement.
  const available = (catalogue ?? []).filter(
    (entry) => !profile.skills.some((declared) => declared.code === entry.code),
  );

  const onError = (cause: unknown) =>
    setError(cause instanceof Error ? cause.message : t('common.error'));

  const add = () => {
    const entry = available.find((candidate) => candidate.code === chosen);
    if (!entry) return;
    setError(null);
    declare.mutate(
      {
        name: entry.label,
        code: entry.code,
        issuer: null,
        obtained_on: null,
        expires_on: null,
      },
      { onSuccess: () => setChosen(''), onError },
    );
  };

  return (
    <Card variant="outlined" data-testid="my-skills">
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h2">{t('skills.mine')}</Typography>

          <Alert severity="info" data-testid="my-skills-explained">
            {t('skills.mineExplained')}
          </Alert>

          {error ? (
            <Alert severity="error" data-testid="my-skills-error">
              {error}
            </Alert>
          ) : null}

          <Stack spacing={1}>
            {profile.skills.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {t('skills.noneDeclared')}
              </Typography>
            ) : (
              profile.skills.map((skill) => (
                <Box
                  key={skill.id ?? skill.name}
                  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
                >
                  <Chip
                    icon={<AppIcon name="skill" />}
                    label={skill.name}
                    data-testid={`my-skill-${skill.code ?? skill.name}`}
                  />
                  <Box sx={{ flexGrow: 1 }} />
                  <Tooltip title={t('skills.withdraw')}>
                    <span>
                      <IconButton
                        size="small"
                        disabled={!skill.id || withdraw.isPending}
                        onClick={() => {
                          if (!skill.id) return;
                          setError(null);
                          withdraw.mutate(skill.id, { onError });
                        }}
                        data-testid={`withdraw-my-skill-${skill.code ?? skill.name}`}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                </Box>
              ))
            )}
          </Stack>

          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
            <TextField
              select
              size="small"
              label={t('skills.declare')}
              value={chosen}
              onChange={(event) => setChosen(event.target.value)}
              sx={{ minWidth: 260 }}
              slotProps={{
                select: { native: true },
                inputLabel: { shrink: true },
                htmlInput: { 'data-testid': 'my-new-skill' },
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
              variant="outlined"
              onClick={add}
              disabled={chosen === '' || declare.isPending}
              data-testid="declare-my-skill"
            >
              {t('common.add')}
            </Button>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}
