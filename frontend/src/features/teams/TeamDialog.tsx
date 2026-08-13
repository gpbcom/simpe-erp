import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import {
  useAgencies,
  useCreateTeam,
  useDeleteTeam,
  useUpdateTeam,
  useUsers,
} from '@/api/queries';
import type { Team, TeamBody } from '@/api/types';

const EMPTY: TeamBody = { name: '', agency_id: '', manager_user_id: '' };

interface TeamDialogProps {
  team: Team | null;
  creating: boolean;
  onClose: () => void;
}

/**
 * Form a team, or change its name, site or manager.
 *
 * @param props - The team, the mode and the close handler.
 * @returns The rendered dialog.
 *
 * @remarks
 * **Exactly one manager, and the field is required.** "One manager" is a
 * cardinality no checkbox on a roster can hold — a flag can be set on nobody or
 * on five — so it is a field on the team itself. The server then checks that
 * the named account may actually run one, which is a question about that
 * account's role and site rather than about this form.
 *
 * **No member list here.** A person is on exactly one team, so adding somebody
 * takes them off another — a consequence worth a deliberate call rather than a
 * side effect of pressing Save. The manager alone is enrolled by the creating
 * call, so a roster never has to explain why the person in charge is missing
 * from it.
 *
 * Moving a team to another site changes where its work comes from: every
 * distance a quote is attributed by is measured from the site. It is offered
 * because a branch that relocates is ordinary, but the members do not follow
 * automatically and the server re-checks the manager against the new site.
 */
export function TeamDialog({ team, creating, onClose }: TeamDialogProps) {
  const { t } = useTranslation();
  const { data: agencies } = useAgencies();
  const { data: accounts } = useUsers();
  const [form, setForm] = useState<TeamBody>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const createTeam = useCreateTeam();
  const updateTeam = useUpdateTeam();
  const deleteTeam = useDeleteTeam();
  const open = Boolean(team) || creating;

  useEffect(() => {
    setError(null);
    setForm(
      team
        ? {
            name: team.name,
            agency_id: team.agency_id,
            manager_user_id: team.manager_user_id,
          }
        : EMPTY,
    );
  }, [team, creating]);

  // Only a manager or an administrator may run a team. Offering an assistant
  // here would produce a refusal the form could have avoided asking for.
  const managers = (accounts ?? []).filter(
    (account) => account.role === 'manager' || account.role === 'admin',
  );

  const submit = async () => {
    setError(null);
    const body: TeamBody = {
      name: form.name.trim(),
      agency_id: form.agency_id,
      manager_user_id: form.manager_user_id,
    };
    try {
      if (team?.id) {
        await updateTeam.mutateAsync({ id: team.id, body });
      } else {
        await createTeam.mutateAsync(body);
      }
      onClose();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  const remove = async () => {
    if (!team?.id) return;
    setError(null);
    try {
      await deleteTeam.mutateAsync(team.id);
      onClose();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t(team ? 'teams.edit' : 'teams.create')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? (
            <Alert severity="error" data-testid="team-dialog-error">
              {error}
            </Alert>
          ) : null}
          <TextField
            label={t('teams.name')}
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            slotProps={{ htmlInput: { 'data-testid': 'team-name' } }}
            fullWidth
          />
          <TextField
            select
            label={t('teams.agency')}
            value={form.agency_id}
            onChange={(event) => setForm({ ...form, agency_id: event.target.value })}
            slotProps={{ htmlInput: { 'data-testid': 'team-agency' } }}
            fullWidth
          >
            {(agencies ?? []).map((agency) => (
              <MenuItem key={agency.id} value={agency.id ?? ''}>
                {agency.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label={t('teams.manager')}
            value={form.manager_user_id}
            onChange={(event) =>
              setForm({ ...form, manager_user_id: event.target.value })
            }
            slotProps={{ htmlInput: { 'data-testid': 'team-manager' } }}
            fullWidth
          >
            {managers.map((account) => (
              <MenuItem key={account.id} value={account.id ?? ''}>
                {account.full_name}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
      </DialogContent>
      <DialogActions>
        {team?.id ? (
          <Button color="error" onClick={remove} data-testid="delete-team">
            {t('teams.delete')}
          </Button>
        ) : null}
        <Button onClick={onClose} data-testid="team-cancel">
          {t('common.cancel')}
        </Button>
        <Button
          variant="contained"
          onClick={submit}
          disabled={!form.name.trim() || !form.agency_id || !form.manager_user_id}
          data-testid="team-save"
        >
          {t('common.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
