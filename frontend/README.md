# SimpleERP — front-end

React 19 + TypeScript (strict) + MUI v6, built by Vite.

```sh
npm ci
npm run dev        # http://localhost:5173
npm run build
npm run lint && npm run typecheck && npm run test
```

`VITE_API_BASE_URL` points at the API. Vite inlines it at **build** time, so
setting it on a running container does nothing — in production it is a Docker
build argument, and nginx proxies `/api` so the app is same-origin.

```
src/
  api/          typed client, query hooks, SSE
  assets/brand/ hand-authored SVG logo
  components/   the shell and the icon set
  features/     one directory per area
  i18n/         fr (default) and en
  store/        the session — the only client state outside TanStack Query
  theme/        palette and MUI theme
  utils/        money, dates, initials
```

Server state belongs to TanStack Query and nowhere else. Every element the GUI
campaign touches carries a `data-testid`.

→ [docs/07](../docs/07-frontend.md)
