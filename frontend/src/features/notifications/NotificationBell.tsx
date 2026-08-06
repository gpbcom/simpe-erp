import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import Badge from '@mui/material/Badge';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Popover from '@mui/material/Popover';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { openNotificationStream, request } from '@/api/client';
import { keys, useMarkAllRead, useNotifications, useUnreadCount } from '@/api/queries';
import { AppIcon } from '@/components/icons/AppIcon';
import { NOTIFICATION_KIND_COLOUR } from '@/theme/palette';
import { formatDateTime } from '@/utils/format';
import { useSession } from '@/store/session';
import type { Notification } from '@/api/types';

/**
 * The bell in the app bar, and the list behind it.
 *
 * @returns The rendered bell.
 *
 * @remarks
 * The badge is driven by the **event stream**, and by nothing else. A frame
 * carries no data — it says only that something changed — so both the list and
 * the badge are refetched rather than patched: one source of truth beats two
 * that can disagree.
 *
 * That is also what makes a dropped frame cost latency rather than a lost
 * notification. The row is written to the database before anything is pushed,
 * and the stream reports `ready` on every reconnect, so a stream that died over
 * lunch catches up the moment it comes back — as does a reader who signed out
 * and signed back in, because this component refetches when it mounts.
 */
export function NotificationBell() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const user = useSession((state) => state.user);
  const [anchor, setAnchor] = useState<null | HTMLElement>(null);
  const { data: unread } = useUnreadCount();
  const { data: notifications } = useNotifications();
  const markAllRead = useMarkAllRead();

  useEffect(() => {
    if (!user) return undefined;
    return openNotificationStream(() => {
      void client.invalidateQueries({ queryKey: keys.notifications });
      void client.invalidateQueries({ queryKey: keys.unreadCount });
    });
  }, [client, user]);

  const open = (notification: Notification) => {
    setAnchor(null);
    if (notification.id) {
      void request(`/api/v1/notifications/${notification.id}/read`, {
        method: 'POST',
      }).then(() => {
        void client.invalidateQueries({ queryKey: keys.notifications });
        void client.invalidateQueries({ queryKey: keys.unreadCount });
      });
    }
    navigate(notification.quote_id ? '/quotes' : '/notifications');
  };

  const count = unread?.unread ?? 0;

  return (
    <>
      <Tooltip title={t('notification.title')}>
        <IconButton
          size="small"
          onClick={(event) => setAnchor(event.currentTarget)}
          data-testid="notification-bell"
        >
          <Badge
            badgeContent={count}
            color="secondary"
            data-testid="notification-badge"
          >
            <AppIcon name="notification" fontSize="small" />
          </Badge>
        </IconButton>
      </Tooltip>

      <Popover
        open={Boolean(anchor)}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { width: 380, maxHeight: 480 } } }}
      >
        <Box sx={{ px: 2, py: 1.5, display: 'flex', alignItems: 'center' }}>
          <Typography variant="subtitle2" sx={{ flexGrow: 1 }}>
            {t('notification.title')}
          </Typography>
          <Button
            size="small"
            onClick={() => markAllRead.mutate()}
            disabled={count === 0}
            data-testid="mark-all-read"
          >
            {t('notification.markAllRead')}
          </Button>
        </Box>
        <Divider />
        <List dense disablePadding data-testid="notification-list">
          {(notifications ?? []).length === 0 ? (
            <Box sx={{ p: 3, textAlign: 'center' }}>
              <Typography variant="body2" color="text.secondary">
                {t('notification.empty')}
              </Typography>
            </Box>
          ) : (
            (notifications ?? []).map((notification) => (
              <ListItemButton
                key={notification.id}
                onClick={() => open(notification)}
                sx={{
                  borderLeft: 3,
                  borderColor: NOTIFICATION_KIND_COLOUR[notification.kind],
                  bgcolor: notification.is_read ? 'transparent' : 'action.hover',
                }}
              >
                <ListItemText
                  primary={notification.title}
                  secondary={`${notification.body ?? ''} · ${formatDateTime(
                    notification.created_at,
                    i18n.language,
                  )}`}
                  primaryTypographyProps={{
                    fontWeight: notification.is_read ? 400 : 600,
                    variant: 'body2',
                  }}
                  secondaryTypographyProps={{ variant: 'caption' }}
                />
              </ListItemButton>
            ))
          )}
        </List>
      </Popover>
    </>
  );
}
