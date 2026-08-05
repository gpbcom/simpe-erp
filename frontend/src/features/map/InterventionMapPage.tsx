import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MapContainer, Marker, TileLayer, Tooltip as LeafletTooltip } from 'react-leaflet';
import L from 'leaflet';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Chip from '@mui/material/Chip';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Stack from '@mui/material/Stack';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { addDays, startOfWeek } from 'date-fns';
import { useAllPlannings, useCustomers, useHcas } from '@/api/queries';
import { INTERVENTION_STATUS_COLOUR } from '@/theme/palette';
import { formatTime, initialsOf, toIsoDate } from '@/utils/format';
import type { Intervention } from '@/api/types';
import 'leaflet/dist/leaflet.css';

/** Where the map opens: central Paris, the agency's own patch. */
const PARIS: [number, number] = [48.8566, 2.3522];

/** The windows a manager can flip between. */
type Window = 'today' | 'week' | 'next7';

/**
 * Turn a photograph into a circular map pin.
 *
 * @param photoUrl - The assistant's portrait, when there is one.
 * @param fallback - Their initials, for when there is not.
 * @param colour - The status ring colour.
 * @returns A Leaflet icon.
 *
 * @remarks
 * `divIcon` rather than an image icon, so the pin can be a styled DOM element:
 * a round portrait, a coloured ring carrying the intervention's status, and a
 * legible initials fallback. An assistant with no photograph must still be a
 * distinguishable pin — the manager's question is "who is where", and a blank
 * circle does not answer it.
 */
function photoPin(photoUrl: string | null, fallback: string, colour: string): L.DivIcon {
  const inner = photoUrl
    ? `<img src="${photoUrl}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:50%" />`
    : `<span style="font:600 12px Inter,sans-serif;color:#fff">${fallback}</span>`;
  return L.divIcon({
    className: '',
    html: `<div style="
        width:38px;height:38px;border-radius:50%;
        border:3px solid ${colour};background:${colour};
        display:grid;place-items:center;overflow:hidden;
        box-shadow:0 2px 6px rgba(0,0,0,.35)
      ">${inner}</div>`,
    iconSize: [38, 38],
    iconAnchor: [19, 19],
  });
}

/**
 * Every planned intervention on a map, one pin per visit.
 *
 * @returns The rendered page.
 */
export function InterventionMapPage() {
  const { t } = useTranslation();
  const [window, setWindow] = useState<Window>('week');

  const { from, to } = useMemo(() => {
    const today = new Date();
    if (window === 'today') return { from: toIsoDate(today), to: toIsoDate(today) };
    if (window === 'next7')
      return { from: toIsoDate(today), to: toIsoDate(addDays(today, 7)) };
    const monday = startOfWeek(today, { weekStartsOn: 1 });
    return { from: toIsoDate(monday), to: toIsoDate(addDays(monday, 6)) };
  }, [window]);

  const { data: plannings } = useAllPlannings(from, to);
  const { data: hcas } = useHcas();
  const { data: customers } = useCustomers();

  const photoFor = (hcaId: string): string | null =>
    (hcas ?? []).find((entry) => entry.id === hcaId)?.photo_url ?? null;

  const customerFor = (customerId: string) =>
    (customers ?? []).find((entry) => entry.id === customerId);

  // Only geocoded visits can be drawn. One without coordinates is not dropped
  // silently — it is counted below the map, because "eleven of twelve visits
  // are shown" is a fact a manager needs, and an invisible twelfth is how
  // somebody gets missed.
  const interventions: Intervention[] = (plannings ?? []).flatMap(
    (planning) => planning.interventions,
  );
  const mappable = interventions.filter(
    (entry) => entry.address.latitude !== null && entry.address.longitude !== null,
  );
  const unmapped = interventions.length - mappable.length;

  return (
    <Stack spacing={2}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Typography variant="h1" sx={{ flexGrow: 1 }}>
          {t('nav.map')}
        </Typography>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={window}
          onChange={(_event, next: Window | null) => next && setWindow(next)}
          data-testid="map-window"
        >
          <ToggleButton value="today" data-testid="map-window-today">
            {t('planning.today')}
          </ToggleButton>
          <ToggleButton value="week" data-testid="map-window-week">
            {t('planning.thisWeek')}
          </ToggleButton>
          <ToggleButton value="next7" data-testid="map-window-next7">
            {t('planning.nextSevenDays')}
          </ToggleButton>
        </ToggleButtonGroup>
        <Chip label={`${mappable.length} / ${interventions.length}`} />
      </Box>

      <Box sx={{ display: 'flex', gap: 2, alignItems: 'stretch' }}>
        <Card sx={{ flexGrow: 1, height: 620, overflow: 'hidden' }} data-testid="map">
          <MapContainer
            center={PARIS}
            zoom={12}
            style={{ height: '100%', width: '100%' }}
            scrollWheelZoom
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {mappable.map((intervention) => {
              const customer = customerFor(intervention.customer_id);
              return (
                <Marker
                  key={intervention.id}
                  position={[
                    intervention.address.latitude as number,
                    intervention.address.longitude as number,
                  ]}
                  icon={photoPin(
                    photoFor(intervention.hca_id),
                    initialsOf(intervention.hca_full_name),
                    INTERVENTION_STATUS_COLOUR[intervention.status],
                  )}
                >
                  <LeafletTooltip direction="top" offset={[0, -20]}>
                    <strong>
                      {customer
                        ? `${customer.first_name} ${customer.last_name}`
                        : intervention.customer_id}
                    </strong>
                    <br />
                    {intervention.address.street}
                    <br />
                    {intervention.address.postal_code} {intervention.address.city}
                    <br />
                    {customer?.phone_number}
                    <br />
                    <em>{intervention.name}</em>
                    <br />
                    {intervention.day} · {formatTime(intervention.start_time)}–
                    {formatTime(intervention.end_time)}
                    <br />
                    {intervention.hca_full_name}
                  </LeafletTooltip>
                </Marker>
              );
            })}
          </MapContainer>
        </Card>

        <Card sx={{ width: 320, height: 620, overflow: 'auto' }}>
          <List dense data-testid="map-list">
            {mappable.map((intervention) => (
              <ListItemButton key={intervention.id}>
                <ListItemText
                  primary={intervention.name}
                  secondary={`${intervention.day} · ${formatTime(
                    intervention.start_time,
                  )} · ${intervention.hca_full_name}`}
                  primaryTypographyProps={{ variant: 'body2' }}
                  secondaryTypographyProps={{ variant: 'caption' }}
                />
              </ListItemButton>
            ))}
          </List>
        </Card>
      </Box>

      {unmapped > 0 ? (
        <Typography variant="caption" color="warning.main" data-testid="unmapped-count">
          {unmapped} intervention(s) sans coordonnées ne sont pas affichées.
        </Typography>
      ) : null}
    </Stack>
  );
}
