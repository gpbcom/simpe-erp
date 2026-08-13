import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useAgencies, useMyTeam, useTeamMembers } from '@/api/queries';
import { TeamDocumentsDialog } from './TeamDocumentsDialog';

/**
 * The caller's own team: who is on it, where it works from, what it shares.
 *
 * @returns The rendered page.
 *
 * @remarks
 * **The identifier comes from the credential**, so there is nothing to pass and
 * nothing that could point at somebody else's team. An assistant signing in has
 * no way to know their team's identifier, and a screen holding one it read from
 * elsewhere is a screen that can be aimed at the wrong roster.
 *
 * Membership, not management. A manager who runs two teams is a *member* of
 * one, and it is that one whose roster and shared space are theirs; the teams
 * they run are a different list on a different screen.
 *
 * An account on no team is told so plainly rather than shown an error. It is an
 * ordinary state — somebody newly hired, or an administrator who covers no
 * rounds — and the answer is for somebody to place them, not for the page to
 * look broken.
 */
export function MyTeamPage() {
  const { t } = useTranslation();
  const { data: team, isLoading, isError } = useMyTeam();
  const { data: members } = useTeamMembers(team?.id ?? '');
  const { data: agencies } = useAgencies();
  const [documents, setDocuments] = useState(false);

  const siteName = useMemo(() => {
    if (!team) return '';
    const site = (agencies ?? []).find((agency) => agency.id === team.agency_id);
    return site?.name ?? team.agency_id;
  }, [agencies, team]);

  if (isLoading) {
    return <Typography data-testid="my-team-loading">{t('common.loading')}</Typography>;
  }

  if (isError || !team) {
    return (
      <Alert severity="info" data-testid="my-team-none">
        {t('teams.noTeam')}
      </Alert>
    );
  }

  return (
    <Stack spacing={3}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Typography variant="h1" sx={{ flexGrow: 1 }} data-testid="my-team-name">
          {team.name}
        </Typography>
        <Button
          variant="contained"
          onClick={() => setDocuments(true)}
          data-testid="my-team-documents"
        >
          {t('teams.documents')}
        </Button>
      </Box>

      <Card>
        <CardContent>
          <Stack spacing={1}>
            <Typography variant="body2" color="text.secondary">
              {t('teams.agency')}
            </Typography>
            <Typography data-testid="my-team-agency">{siteName}</Typography>
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h2" sx={{ mb: 1 }}>
            {t('teams.members')}
          </Typography>
          <List dense data-testid="my-team-members">
            {(members ?? []).map((member) => (
              <ListItem
                key={`${member.member_kind}:${member.member_id}`}
                data-testid={`my-team-member-${member.member_id}`}
              >
                <ListItemText
                  primary={member.member_id}
                  secondary={t(`memberKind.${member.member_kind}`)}
                />
              </ListItem>
            ))}
          </List>
        </CardContent>
      </Card>

      <TeamDocumentsDialog
        team={documents ? team : null}
        onClose={() => setDocuments(false)}
      />
    </Stack>
  );
}
