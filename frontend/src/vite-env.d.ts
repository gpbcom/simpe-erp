/// <reference types="vite/client" />

/** The build-time variables Vite inlines. */
interface ImportMetaEnv {
  /** Where the browser reaches the API. */
  readonly VITE_API_BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module '*.svg' {
  const source: string;
  export default source;
}
