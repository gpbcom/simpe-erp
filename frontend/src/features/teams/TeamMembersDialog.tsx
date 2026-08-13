import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import {
  useAddTeamMember,
  useTeamMembers,
  useHcas,
  useRemoveTeamMember,
  useUsers,
} from '@/api/queries';
import type { MemberKind, OrganisationMember, Team } from '@/api/types';

interface TeamMembersDialogProps {
  team: Team | null;
  onClose: () => void;
}

/**
 * Who is on one team.
 *
 * @param props - The team and the close handler.
 * @returns The rendered dialog.
 *
 * @remarks
 * **One person at a time, not a submitted roster.** This is the one place the
 * "send the whole list" rule is deliberately broken: a person is on exactly one
 * team, so a whole-list submission would silently take people off other teams —
 * and each of those removals changes whose week the next planning run rewrites.
 *
 * Two refusals arrive from the server and are shown verbatim, because both name
 * a different screen to go and fix. Somebody already on a team must be taken off
 * it first; somebody based at another site must be attached to this one's site
 * first — a team is people *at a place*, and the planner measures every round
 * from that place.
 *
 * The team's manager cannot be removed here. Replacing a manager is naming a new
 * one on the team itself, so that the team never briefly has none.
 */
export function TeamMembersDialog({ team, onClose }: TeamMembersDialogProps) {
  const { t } = useTranslation();
  const teamId = team?.id ?? '';
  const { data: members, isLoading } = useTeamMembers(teamId);
  const { data: accounts } = useUsers();
  const { data: assistants } = useHcas();
  const addMember = useAddTeamMember();
  const removeMember = useRemoveTeamMember();
  const [kind, setKind] = useState<MemberKind>('hca');
  const [personId, setPersonId] = useState('');
  const [error, setError] = useState<string | null>(null);

  const names = useMemo(() => {
    const resolved = new Map<string, string>();
    for (const account of accounts ?? []) {
      if (account.id) resolved.set(`user:${account.id}`, account.full_name);
    }
    for (const assistant of assistants ?? []) {
      if (assistant.id) {
        resolved.set(`hca:${assistant.id}`, `${assistant.first_name} ${assistant.last_name}`);
      }
    }
    return resolved;
  }, [accounts, assistants]);

  const choices = useMemo(() => {
    if (kind === 'user') {
      return (accounts ?? [])
        .filter((account) => account.id)
        .map((account) => ({ id: account.id as string, label: account.full_name }));
    }
    return (assistants ?? [])
      .filter((assistant) => assistant.id)
      .map((assistant) => ({
        id: assistant.id as string,
        label: `${assistant.first_name} ${assistant.last_name}`,
      }));
  }, [accounts, assistants, kind]);

  const attach = async () => {
    if (!teamId || !personId) return;
    setError(null);
    try {
      await addMember.mutateAsync({
        teamId,
        body: { member_kind: kind, member_id: personId },
      });
      setPersonId('');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  const detach = async (member: OrganisationMember) => {
    if (!teamId) return;
    setError(null);
    try {
      await removeMember.mutateAsync({ teamId, member });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  return (
    <Dialog open={Boolean(team)} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>
        {t('teams.membersOf', { name: team?.name ?? '' })}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? (
            <Alert severity="error" data-testid="team-members-error">
              {error}
            </Alert>
          ) : null}

          <Stack direction="row" spacing={1}>
            <TextField
              select
              label={t('teams.kind')}
              value={kind}
              onChange={(event) => {
                setKind(event.target.value as MemberKind);
                setPersonId('');
              }}
              slotProps={{ htmlInput: { 'data-testid': 'team-member-kind' } }}
              sx={{ minWidth: 160 }}
            >
              <MenuItem value="hca">{t('memberKind.hca')}</MenuItem>
              <MenuItem value="user">{t('memberKind.user')}</MenuItem>
            </TextField>
            <TextField
              select
              label={t('teams.person')}
              value={personId}
              onChange={(event) => setPersonId(event.target.value)}
              slotProps={{ htmlInput: { 'data-testid': 'team-member-person' } }}
              sx={{ flexGrow: 1 }}
            >
              {choices.map((choice) => (
                <MenuItem key={choice.id} value={choice.id}>
                  {choice.label}
                </MenuItem>
              ))}
            </TextField>
            <Button
              variant="contained"
              onClick={attach}
              disabled={!personId}
              data-testid="team-member-add"
            >
              {t('teams.add')}
            </Button>
          </Stack>

          <List dense data-testid="team-members-list">
            {(members ?? []).map((member) => (
              <ListItem
                key={`${member.member_kind}:${member.member_id}`}
                data-testid={`team-member-${member.member_id}`}
                secondaryAction={
                  <Button
                    size="small"
                    color="error"
                    onClick={() => detach(member)}
                    data-testid={`team-member-remove-${member.member_id}`}
                  >
                    {t('teams.remove')}
                  </Button>
                }
              >
                <ListItemText
                  primary={
                    names.get(`${member.member_kind}:${member.member_id}`) ??
                    member.member_id
                  }
                  secondary={t(`memberKind.${member.member_kind}`)}
                />
              </ListItem>
            ))}
          </List>

          {!isLoading && (members ?? []).length === 0 ? (
            <Alert severity="info" data-testid="team-members-empty">
              {t('teams.noMembers')}
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} data-testid="team-members-close">
          {t('common.close')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
