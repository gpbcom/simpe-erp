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
  useAddAgencyMember,
  useAgencyMembers,
  useHcas,
  useRemoveAgencyMember,
  useUsers,
} from '@/api/queries';
import type { Agency, MemberKind, OrganisationMember } from '@/api/types';

interface AgencyMembersDialogProps {
  agency: Agency | null;
  onClose: () => void;
}

/**
 * Who works at one site.
 *
 * @param props - The site and the close handler.
 * @returns The rendered dialog.
 *
 * @remarks
 * **Two kinds of member, and both are needed.** An account is what somebody
 * signs in with. An assistant record is the person the planner schedules. A
 * manager who covers rounds has both and legitimately appears twice — once as
 * each — because the join is polymorphic and carries no foreign key either way.
 *
 * Names are resolved **here**, from the account and workforce lists this screen
 * already holds. The membership itself carries only a kind and an identifier,
 * which is what keeps a roster from becoming a directory: nothing about a
 * person travels with their membership.
 *
 * Somebody already attached elsewhere is **refused rather than moved**. A
 * change of site is a deliberate act with consequences for the teams they are
 * on, and a silent reassignment would make it look like nothing happened.
 */
export function AgencyMembersDialog({ agency, onClose }: AgencyMembersDialogProps) {
  const { t } = useTranslation();
  const agencyId = agency?.id ?? '';
  const { data: members, isLoading } = useAgencyMembers(agencyId);
  const { data: accounts } = useUsers();
  const { data: assistants } = useHcas();
  const addMember = useAddAgencyMember();
  const removeMember = useRemoveAgencyMember();
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
    if (!agencyId || !personId) return;
    setError(null);
    try {
      await addMember.mutateAsync({
        agencyId,
        body: { member_kind: kind, member_id: personId },
      });
      setPersonId('');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  const detach = async (member: OrganisationMember) => {
    if (!agencyId) return;
    setError(null);
    try {
      await removeMember.mutateAsync({ agencyId, member });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  return (
    <Dialog open={Boolean(agency)} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>
        {t('agencies.membersOf', { name: agency?.name ?? '' })}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? (
            <Alert severity="error" data-testid="agency-members-error">
              {error}
            </Alert>
          ) : null}

          <Stack direction="row" spacing={1}>
            <TextField
              select
              label={t('agencies.kind')}
              value={kind}
              onChange={(event) => {
                setKind(event.target.value as MemberKind);
                setPersonId('');
              }}
              slotProps={{ htmlInput: { 'data-testid': 'agency-member-kind' } }}
              sx={{ minWidth: 160 }}
            >
              <MenuItem value="hca">{t('memberKind.hca')}</MenuItem>
              <MenuItem value="user">{t('memberKind.user')}</MenuItem>
            </TextField>
            <TextField
              select
              label={t('agencies.person')}
              value={personId}
              onChange={(event) => setPersonId(event.target.value)}
              slotProps={{ htmlInput: { 'data-testid': 'agency-member-person' } }}
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
              data-testid="agency-member-add"
            >
              {t('agencies.attach')}
            </Button>
          </Stack>

          <List dense data-testid="agency-members-list">
            {(members ?? []).map((member) => (
              <ListItem
                key={`${member.member_kind}:${member.member_id}`}
                data-testid={`agency-member-${member.member_id}`}
                secondaryAction={
                  <Button
                    size="small"
                    color="error"
                    onClick={() => detach(member)}
                    data-testid={`agency-member-remove-${member.member_id}`}
                  >
                    {t('agencies.detach')}
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
            <Alert severity="info" data-testid="agency-members-empty">
              {t('agencies.noMembers')}
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} data-testid="agency-members-close">
          {t('common.close')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
