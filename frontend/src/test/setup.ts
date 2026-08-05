import '@testing-library/jest-dom/vitest';

// jsdom implements neither, and MUI's responsive helpers and the DataGrid both
// reach for them on mount — without these every component test fails in the
// same uninformative way.
window.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
})) as typeof window.matchMedia;

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
