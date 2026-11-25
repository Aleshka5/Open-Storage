# frontend — Chat and player (US-04)

Vite + React + TypeScript SPA. The visual language is `docs/frontend/design_document.md`
(an **English** interface, **dark** palette); token structure and typography come from
`service-design-language.md` (filenkov).

## Resolving the conflict between standards

`design_document.md` (this product's spec, later/more specific) specifies an
**English** interface and a **dark** theme, while `service-design-language.md` (filenkov's shared
visual contract) fixes "English, light, no dark theme". By order of
authority (AGENTS.md, docs/README.md: the frontend standard is `design_document.md`)
`design_document.md` wins: English strings + dark palette + the
"Audio" title. From `service-design-language.md` we take token names and roles, typography
(Public Sans + Fraunces), square radii, the focus ring and the header behaviour.

## Scripts

- `npm run dev` — Vite with an `/api` proxy to audio-api.
- `npm run build` — tsc + vite build into `dist/`.
- `npm test` — vitest (five mandatory topics: the five-second rule, poll backoff,
  stop on ready, rendering phrases by seq, seeking).
- `npm run lint` — eslint.

## Building into a container

`Dockerfile`: multi-stage node → nginx. Static files in `/usr/share/nginx/html`,
SPA fallback to `index.html`. In `deploy/docker-compose.yml` there is a `frontend` service
on the `auth_network` network (public entry — Caddy → Auth Gateway).

## Invariants (do not break)

- Identity — only `X-Auth-Subject` (a canonical lower-case UUID) from the gateway; `owner_id` is neither stored nor sent.
- Audio — only `/api/recordings/{id}/audio` (Range proxy), no presigned URLs.
- The browser never talks to MinIO/Mongo/Qdrant/RabbitMQ/GPU.
- Phrase text is read-only (`«redacted-vault-secret»-select: text`, no contenteditable/input).
- `prefers-reduced-motion` is respected (instant scrolling, lift without a transition).
- Suggestion `score` is not shown as a percentage (it is a cosine; there is no menu in US-04).

