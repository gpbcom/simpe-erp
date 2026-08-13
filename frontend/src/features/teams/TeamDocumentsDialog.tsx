import { useRef, useState } from 'react';
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
import Stack from '@mui/material/Stack';
import UploadIcon from '@mui/icons-material/UploadFile';
import { useTeamDocumentConstraints, useTeamDocuments } from '@/api/queries';
import { request, requestBlob } from '@/api/client';
import { saveBlob } from '@/utils/download';
import { useQueryClient } from '@tanstack/react-query';
import { keys } from '@/api/queries';
import type { Team, TeamDocument } from '@/api/types';

/**
 * Format a size in bytes for a person reading a list of files.
 *
 * @param bytes - The stored object's size.
 * @returns A short human-readable size.
 */
function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface TeamDocumentsDialogProps {
  team: Team | null;
  onClose: () => void;
}

/**
 * The files a team shares.
 *
 * @param props - The team and the close handler.
 * @returns The rendered dialog.
 *
 * @remarks
 * **Everybody on the team may add a file, and everybody on it may read one.**
 * That is unusual on this surface — almost every other write here is a
 * manager's — and it is the point: a shared space only one person can fill is a
 * shared space nobody uses.
 *
 * Removing is narrower: whoever added it, the team's manager, or an
 * administrator. Anybody may *add* one, so anybody being able to remove one
 * would make the space a place where work disappears without a name attached.
 * The uploader's name is stored on the record rather than joined at read time,
 * so a file added by somebody who has since left still says who added it.
 *
 * The limits are read from the server **before** the picker opens, so an
 * oversized or unshareable file is refused here rather than after the whole
 * thing has crossed the network. The accepted types are the ones the store can
 * recognise from a file's own leading bytes, which is why `.docx` and `.xlsx`
 * both arrive as `application/zip`.
 */
export function TeamDocumentsDialog({ team, onClose }: TeamDocumentsDialogProps) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const teamId = team?.id ?? '';
  const { data: documents, isLoading } = useTeamDocuments(teamId);
  const { data: constraints } = useTeamDocumentConstraints();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  const refresh = () => {
    void client.invalidateQueries({ queryKey: keys.teamDocuments(teamId) });
  };

  const upload = async (file: File) => {
    setError(null);
    if (constraints && file.size > constraints.max_upload_bytes) {
      setError(
        t('teams.fileTooLarge', { limit: humanSize(constraints.max_upload_bytes) }),
      );
      return;
    }
    const body = new FormData();
    body.append('document', file);
    setBusy(true);
    try {
      await request<TeamDocument>(`/api/v1/teams/${teamId}/documents`, {
        method: 'POST',
        body,
      });
      refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };

  const download = async (document: TeamDocument) => {
    setError(null);
    try {
      const downloaded = await requestBlob(
        `/api/v1/teams/${teamId}/documents/${document.id}`,
      );
      saveBlob(downloaded.blob, downloaded.filename || document.file_name);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  const remove = async (document: TeamDocument) => {
    setError(null);
    try {
      await request<void>(`/api/v1/teams/${teamId}/documents/${document.id}`, {
        method: 'DELETE',
      });
      refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  return (
    <Dialog open={Boolean(team)} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t('teams.documentsOf', { name: team?.name ?? '' })}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? (
            <Alert severity="error" data-testid="team-documents-error">
              {error}
            </Alert>
          ) : null}

          <Button
            variant="contained"
            startIcon={<UploadIcon />}
            disabled={busy}
            onClick={() => picker.current?.click()}
            data-testid="team-document-upload"
          >
            {t('teams.upload')}
          </Button>
          <input
            ref={picker}
            type="file"
            hidden
            accept={constraints?.accepted_content_types.join(',')}
            data-testid="team-document-input"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload(file);
              event.target.value = '';
            }}
          />

          <List dense data-testid="team-documents-list">
            {(documents ?? []).map((document) => (
              <ListItem
                key={document.id}
                data-testid={`team-document-${document.id}`}
                secondaryAction={
                  <Stack direction="row" spacing={1}>
                    <Button
                      size="small"
                      onClick={() => download(document)}
                      data-testid={`team-document-download-${document.id}`}
                    >
                      {t('teams.download')}
                    </Button>
                    <Button
                      size="small"
                      color="error"
                      onClick={() => remove(document)}
                      data-testid={`team-document-remove-${document.id}`}
                    >
                      {t('teams.remove')}
                    </Button>
                  </Stack>
                }
              >
                <ListItemText
                  primary={document.file_name}
                  secondary={`${t('teams.uploadedBy', {
                    name: document.uploaded_by_name,
                  })} · ${humanSize(document.size_bytes)}`}
                />
              </ListItem>
            ))}
          </List>

          {!isLoading && (documents ?? []).length === 0 ? (
            <Alert severity="info" data-testid="team-documents-empty">
              {t('teams.noDocuments')}
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} data-testid="team-documents-close">
          {t('common.close')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
