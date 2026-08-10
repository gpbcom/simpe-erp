import { useTranslation } from 'react-i18next';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Chip from '@mui/material/Chip';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMarkAllRead, useNotifications } from '@/api/queries';
import { EntityFilterBar } from '@/components/filters/EntityFilterBar';
import type { FilterDetail, FilterTab } from '@/components/filters/EntityFilterBar';
import { useEntityFilter } from '@/components/filters/entityFilter';
import type { EntityFilterSpec } from '@/components/filters/entityFilter';
import { NOTIFICATION_KIND_COLOUR } from '@/theme/palette';
import { formatDateTime } from '@/utils/format';

/** Which of the notification filter's fields are text, flags and closed lists. */
const NOTIFICATION_FILTER_SPEC: EntityFilterSpec = {
  textFields: ['search'],
  flagFields: ['is_read'],
  enumFields: {
    kind: [
      'quote-submitted',
      'quote-validated',
      'quote-refused',
      'planning-completed',
      'skill-added',
    ],
  },
};

/** The kinds, as tabs, in the order the work they describe happens. */
const NOTIFICATION_TABS: FilterTab[] = [
  { key: 'all', label: 'notification.filter_all' },
  {
    key: 'quote-submitted',
    value: 'quote-submitted',
    label: 'notification.filter_quote-submitted',
  },
  {
    key: 'quote-validated',
    value: 'quote-validated',
    label: 'notification.filter_quote-validated',
  },
  {
    key: 'quote-refused',
    value: 'quote-refused',
    label: 'notification.filter_quote-refused',
  },
  {
    key: 'planning-completed',
    value: 'planning-completed',
    label: 'notification.filter_planning-completed',
  },
  {
    key: 'skill-added',
    value: 'skill-added',
    label: 'notification.filter_skill-added',
  },
];

/** What is folded away behind "more filters". */
const NOTIFICATION_DETAILS: FilterDetail[] = [
  {
    field: 'is_read',
    label: 'notification.filterRead',
    kind: 'flag',
    options: [
      { value: 'true', label: 'notification.filterReadYes' },
      { value: 'false', label: 'notification.filterReadNo' },
    ],
  },
];

/**
 * The full notification centre.
 *
 * @returns The rendered page.
 */
export function NotificationsPage() {
  const { t, i18n } = useTranslation();
  const notificationFilter = useEntityFilter(NOTIFICATION_FILTER_SPEC);
  const { data, isLoading } = useNotifications(notificationFilter.filter);
  const markAllRead = useMarkAllRead();
  const notifications = data ?? [];
  const unread = notifications.filter((entry) => !entry.is_read).length;

  return (
    <Stack spacing={2}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Typography variant="h1" sx={{ flexGrow: 1 }}>
          {t('notification.title')}
        </Typography>
        {unread > 0 ? (
          <Chip
            label={t('notification.unread', { count: unread })}
            color="secondary"
            data-testid="unread-chip"
          />
        ) : null}
        <Button
          variant="outlined"
          onClick={() => markAllRead.mutate()}
          disabled={unread === 0}
          data-testid="page-mark-all-read"
        >
          {t('notification.markAllRead')}
        </Button>
      </Box>

      <EntityFilterBar
        state={notificationFilter}
        testId="notification"
        searchLabel="notification.searchFilter"
        tabField="kind"
        tabs={NOTIFICATION_TABS}
        details={NOTIFICATION_DETAILS}
      />

      <Card>
        {isLoading ? (
          <Box sx={{ p: 3 }}>
            <Typography variant="body2">{t('common.loading')}</Typography>
          </Box>
        ) : notifications.length === 0 ? (
          <Box sx={{ p: 6, textAlign: 'center' }} data-testid="notifications-empty">
            <Typography color="text.secondary">{t('notification.empty')}</Typography>
          </Box>
        ) : (
          <List disablePadding data-testid="notifications-page-list">
            {notifications.map((notification) => (
              <ListItem
                key={notification.id}
                divider
                sx={{
                  borderLeft: 4,
                  borderColor: NOTIFICATION_KIND_COLOUR[notification.kind],
                  bgcolor: notification.is_read ? 'transparent' : 'action.hover',
                }}
              >
                <ListItemText
                  primary={notification.title}
                  secondary={notification.body}
                  primaryTypographyProps={{
                    fontWeight: notification.is_read ? 400 : 600,
                  }}
                />
                <Typography variant="caption" color="text.secondary">
                  {formatDateTime(notification.created_at, i18n.language)}
                </Typography>
              </ListItem>
            ))}
          </List>
        )}
      </Card>
    </Stack>
  );
}
