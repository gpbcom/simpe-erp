import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Absolute imports from the source root. Relative chains like
    // ../../../shared/api are the first thing to rot when a file moves.
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    host: true,
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        // Split the heavy, rarely-changing libraries out of the app chunk, so
        // a one-line change does not invalidate a megabyte of MUI in every
        // browser's cache.
        manualChunks: {
          mui: ['@mui/material', '@mui/icons-material', '@mui/x-data-grid'],
          calendar: ['@fullcalendar/react', '@fullcalendar/timegrid', '@fullcalendar/daygrid'],
          map: ['leaflet', 'react-leaflet'],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    css: false,
  },
});
