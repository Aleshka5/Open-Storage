# resume-page

The `filenkov.store` showcase: a static tree of resume nodes, plus `/auth` and
`/admin`. Served by nginx as `resume:80`; the gateway is its only entrance.

Contracts:

- [frontend design](../../../docs/auth-gateway/frontend/design.md)
- [frontend security](../../../docs/auth-gateway/frontend/security.md)
- [backend contract](../../../docs/auth-gateway/frontend/backend-contract.md)

## Identity

One `GET /auth/session` per page load. `401` is a guest — there is no refresh
call and no retry loop; the gateway owns the cookies. Sign-in is a navigation to
`/auth/login?return_to=<path>`; sign-out is `POST /auth/logout` with an
`X-Requested-With` header.

## Tree

A node is a folder under `src/resume/nodes`; the folder path is the URL.
`registry.ts` discovers them with `import.meta.glob`, and `registry.test.ts`
fails the build when a pair, parent, segment, order, teaser or root breaks.

## Commands

```sh
npm install
npm test            # vitest
npm run build       # tsc -b && vite build; fails above 95 KB gzip initial JS
npm run dev         # proxies /auth, /admin, /api to 127.0.0.1:8080
```

## Out of scope

The owl chat (gateway ADR-0009). `POST /api/chat` exists on the gateway; no page calls
it.
