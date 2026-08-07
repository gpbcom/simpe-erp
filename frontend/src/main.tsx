import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import { App } from './App';
import { loadRuntimeConfig } from './api/client';
import './i18n';

const client = new QueryClient({
  defaultOptions: {
    queries: {
      // A quote list a manager looked at ten seconds ago is still the quote
      // list; refetching on every tab focus makes an ERP feel like it is
      // fighting the operator.
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

// Awaited before the first render, so no request can be made against the
// origin the bundle was *built* for rather than the one it is *deployed* to.
// It is a single same-origin fetch of a file nginx already has open; the cost
// is invisible beside loading the bundle itself.
void loadRuntimeConfig().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </StrictMode>,
  );
});
