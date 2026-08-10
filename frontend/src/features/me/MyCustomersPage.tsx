import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import CardContent from '@mui/material/CardContent';
import Drawer from '@mui/material/Drawer';
import Divider from '@mui/material/Divider';
import Grid from '@mui/material/Grid2';
import InputAdornment from '@mui/material/InputAdornment';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import SearchIcon from '@mui/icons-material/Search';
import { useMyCustomers } from '@/api/queries';
import { AppIcon } from '@/components/icons/AppIcon';
import { CustomerStatusChip } from '@/features/customers/CustomerStatusChip';
import type { Customer } from '@/api/types';

/**
 * The customers an assistant serves, as searchable cards.
 *
 * @returns The rendered page.
 *
 * @remarks
 * Cards rather than a table. This is the one screen an assistant opens on a
 * phone between two visits, and a name, an address and a telephone number in a
 * tappable block beats seven columns they have to scroll sideways through.
 */
export function MyCustomersPage() {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const { data, isLoading } = useMyCustomers(search || undefined);
  const [selected, setSelected] = useState<Customer | null>(null);
  const customers = data ?? [];

  return (
    <Stack spacing={2}>
      <Typography variant="h1">{t('nav.myCustomers')}</Typography>

      <TextField
        placeholder={t('common.search')}
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        sx={{ maxWidth: 420 }}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon fontSize="small" />
            </InputAdornment>
          ),
        }}
        inputProps={{ 'data-testid': 'customer-search' }}
      />

      {isLoading ? (
        <Typography>{t('common.loading')}</Typography>
      ) : customers.length === 0 ? (
        <Card>
          <Box sx={{ p: 6, textAlign: 'center' }} data-testid="customers-empty">
            <Typography color="text.secondary">{t('customer.noneAssigned')}</Typography>
          </Box>
        </Card>
      ) : (
        <Grid container spacing={2} data-testid="customer-cards">
          {customers.map((customer) => (
            <Grid key={customer.id} size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
              <Card sx={{ height: '100%' }}>
                <CardActionArea
                  onClick={() => setSelected(customer)}
                  sx={{ height: '100%' }}
                  data-testid={`customer-card-${customer.id}`}
                >
                  <CardContent>
                    <Stack spacing={1}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <AppIcon name="customer" color="primary" />
                        <Typography variant="h3" sx={{ flexGrow: 1 }}>
                          {customer.first_name} {customer.last_name}
                        </Typography>
                      </Box>
                      <Typography variant="body2" color="text.secondary">
                        {customer.address.street}
                        <br />
                        {customer.address.postal_code} {customer.address.city}
                      </Typography>
                      <Box sx={{ alignSelf: 'flex-start' }}>
                        <CustomerStatusChip
                          status={customer.registration_status}
                          testId={`customer-status-${customer.id}`}
                        />
                      </Box>
                    </Stack>
                  </CardContent>
                </CardActionArea>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      <Drawer
        anchor="right"
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        slotProps={{ paper: { sx: { width: 380, p: 3 } } }}
      >
        {selected ? (
          <Stack spacing={2} data-testid="customer-detail">
            <Typography variant="h2">
              {selected.first_name} {selected.last_name}
            </Typography>
            <Divider />
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('hca.address')}
              </Typography>
              <Typography>
                {selected.address.street}
                <br />
                {selected.address.postal_code} {selected.address.city}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('hca.phone')}
              </Typography>
              <Typography>{selected.phone_number}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                {t('hca.email')}
              </Typography>
              <Typography>{selected.email}</Typography>
            </Box>
          </Stack>
        ) : null}
      </Drawer>
    </Stack>
  );
}
