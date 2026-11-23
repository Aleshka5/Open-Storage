# spa — init

The front end of the storage product. A React single-page app that talks to one origin — its own — and holds no session of its own. What it shows is in the screens below; how it is built and served is here. Identity is the gateway's; the API is [app](../app/init.md).

## Stack

| Item | Value | Source |
|---|---|---|
| Framework | React 18.3, TypeScript 5.7 | `frontend/package.json` |
| Build | Vite 6 (dev server), `tsc && vite build` (prod) | `frontend/vite.config.ts` |
| Routing | `react-router-dom` 6, `createBrowserRouter` | `frontend/src/router.tsx` |
| State | `zustand` 5, two stores: `auth`, `quota` | `frontend/src/store/` |
| HTTP | `axios` 1.7, one instance, `withCredentials: true` | `frontend/src/services/api.ts` |
| Style | Tailwind 3.4 plus a CSS token layer | `frontend/tailwind.config.js`, `src/styles/` |
| Icons, toasts | `lucide-react`, `react-hot-toast` | `package.json` |
| i18n | `i18next` / `react-i18next`, locales `en`, `ru` | `frontend/src/locales/` |
| Archives | `jszip` (folder download and ZIP upload on the client side) | `package.json` |

## Screens

Routes in `src/router.tsx`. Every page lives inside `ProtectedRoute`, which renders the access error when the session probe found no user.

| Route | Page | Shows | Role gate |
|---|---|---|---|
| `/` | `RootRedirect` | `/files`, or the "open this site through the hub" error | — |
| `/auth` | `RootRedirect` | Same. There is no local sign-in page. | — |
| `/files` | `FilesPage` | File manager on `/api/files` | any user |
| `/photos` | `PhotosPage` | Infinite grid, lightbox, upload, multi-delete, description search | any user |
| `/generated`, `/generated/:id` | `GeneratedImagesPage`, `GeneratedImagePage` | Image-generation history: list, one run, delete | any user; the sidebar item is hidden for `BLOCKED` |
| `/private` | `PrivatePage` | Passphrase unlock, then the encrypted file manager | any user |
| `/keys` | `KeysRegistryPage` | Key/value registry inside the vault; every add or delete writes immediately | any user |
| `/resumes`, `/resumes/:country`, `/resumes/:country/:company`, `/resumes/:country/:company/:vacancy` | `ResumesPage` and three detail pages | Country → company → vacancy tree, vacancy metadata, file manager rooted at the vacancy | `ResumesGuard`: FAMILY, ADMIN |
| `/vacancies` | `AllVacanciesPage` | Flat cross-tree vacancy table with a status filter | FAMILY, ADMIN |
| `/shared` | `SharedPage` | File manager on `/api/shared` | FAMILY, ADMIN (nav); STRANGER is refused by the API |
| `/admin` | `AdminPage` | Users with quotas, block, delete; bucket cards | ADMIN (nav); the API enforces |

One shared component, `FileManager` (`src/components/FileManager/`), renders Files, Shared, Private and the resumes file tree; it takes `mode` (`plain` | `encrypted`), `apiPrefix`, an optional `basePath` and `hiddenNames`.

**The sidebar is the only role gate in the app, and it has no route for a non-family user.** A signed-in `STRANGER` can still reach `/resumes`, `/vacancies` and `/shared` by URL; the API refuses with `403`, which the page renders as an access error.

## Session and identity

Theme and chrome follow the [brand book](../../brand-book/init.md). `theme.preference` on this origin is `light`, `dark`, or `system`. A missing, unreadable, or unknown value paints dark. The header’s `Theme` control changes it without a reload. Palettes live in `src/styles/theme.css`.

The control’s face is the glass icon trigger and popover slider of [ADR-0004](../../../adrs/4-liquid-glass-theme-control.md); the resume page keeps its segmented control. The brand book keeps the key, the fallback, the palettes, and the circle.

The SPA never sees a token.

1. `AppRouter` calls `useAuthStore.fetchMe()` once: `GET /api/auth/me` with credentials.
2. `200` → the user (`user_id`, `email`, `role`) is in the store; the router renders.
3. `401` → the "open this site through the hub" screen. No redirect, no form.
4. `503` or `USER_SERVICE_UNAVAILABLE` → an error screen with `Reload`.
5. Any `401 PRIVATE_SESSION_EXPIRED` from the API raises the window event `homecloud:private-session-expired`, which reopens the unlock modal. It never logs the product session out.

There is no logout, no OAuth start and no token storage in the client: all three belong to the gateway. The cookie is HttpOnly, so JavaScript cannot read it and nothing in `src/` does.

## API base

`baseURL: import.meta.env.VITE_API_BASE_URL ?? ""` — the default is the empty string, so every call is a relative path on the page's own origin (`/api/...`). In development the Vite dev server proxies `/api` to `API_PROXY_TARGET` (default `http://localhost:8000`, `vite.config.ts`). `VITE_API_BASE_URL` is the only build-time variable the client reads.

## Build and serve

| Stage | What happens |
|---|---|
| `frontend/` | `npm run build` → `dist/`. `frontend/Dockerfile` and `nginx.conf` exist but are not the production path. |
| Image | The `app` image is a multi-stage build: `node:20-alpine` builds `frontend/`, and the result is copied into the Python image at `/opt/spa` (`backend/Dockerfile`; decision D5 in [US-05](../../user_stories/us-05-storage-namespace/init.md)). |
| Runtime | FastAPI serves it: `GET /` returns `/opt/spa/index.html` with `Cache-Control: no-cache`, `/assets/*` is a static mount, and every other `GET` path falls back to `index.html` (or to a real file inside that directory). When the directory is missing, `GET /` answers `{"status":"ok","version":"1.0"}` instead. |
| Edge | One upstream for the origin, `app:8000`. There is no second web server to route to. |

`SPA_STATIC_DIR` (default `/opt/spa`) names the directory.

## Properties to keep

- One origin, one upstream: a page and its API never split across hosts, because the session cookie is the only credential the browser holds.
- No secret and no token in the bundle. Every `VITE_*` value is public.
- The role the UI uses comes from `GET /api/auth/me`; the UI never derives a role from anything else, and hiding a nav item is never the enforcement.
