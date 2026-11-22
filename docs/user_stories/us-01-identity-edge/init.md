# US-01 Identity and edge

## Story

As the operator of `filenkov.store`, I want one authentication and edge layer, so that every SSO host shares a login, a role model, and a single identity contract.

## Status

In progress. The gateway, the realm, the page, the proxy file and the scripts are in the tree; the stand, the consumers and the cutover are not.

## Scope

Namespace `auth-gateway`: proxy, gateway, idp, idp_db, resume-page. One release, one cutover. No migration phase, no parallel run, no compatibility flag, no data import from the old auth or user services, no preserved old UUIDs, no `X-User-Id` or `X-Storage-Role`.

## Acceptance

- `make up` from empty volumes is ready within 90 seconds. `/readyz` is 200.
- `make verify` passes for nine hosts × anonymous, signed-in, and admin.
- Google login is one login for every SSO host. Logout ends the idp session and data bound to `sid`.
- A role granted or removed in `/admin` takes effect within 5 minutes.
- The last admin cannot be removed (`409`). A service admin cannot edit another service (`403`).
- `go test ./...`, `npm test`, and `caddy validate` pass.
- Gateway stays within 4200 lines of Go ([ADR-0005](../../adrs/0007-gateway-line-budget.md)). No Redis, no catalog service, no `X-User-Id`.
- The contracts in `docs/auth-gateway/` match the code.

## Out of scope

- Product application code, except the header rename tracked in task 14.
- A second contract version.
- Hot reload of gateway config.

## Rollback

The previous stack stays stopped, volumes intact, for 7 days. Return is starting that stack and restoring the proxy file from git.

## Before cutover

- New Google OAuth client. Redirect URI only `https://id.filenkov.store/realms/filenkov/broker/google/endpoint`.
- Secrets in `deploy/auth-gateway/.env` (not in git).
- DNS `id.filenkov.store` points at the host.
- Ports 80 and 443 are free at the moment of cutover.

## Tasks

1. [Repository skeleton](tasks/task-01-repository-skeleton.md)
2. [Config validation](tasks/task-02-config-validation.md)
3. [OIDC verifier](tasks/task-03-oidc-verifier.md)
4. [Session cookie](tasks/task-04-session-cookie.md)
5. [Policy](tasks/task-05-policy.md)
6. [Edge proxy](tasks/task-06-edge-proxy.md)
7. [BFF](tasks/task-07-bff.md)
8. [Admin API](tasks/task-08-admin-api.md)
9. [Realm as code](tasks/task-09-realm-as-code.md)
10. [Bootstrap scripts](tasks/task-10-bootstrap-scripts.md)
11. [Resume page](tasks/task-11-resume-page.md)
12. [Proxy](tasks/task-12-proxy.md)
13. [Compose and stand](tasks/task-13-compose-and-stand.md)
14. [Consumers on v1](tasks/task-14-consumers-on-v1.md)
15. [Stand acceptance](tasks/task-15-stand-acceptance.md)
16. [Cutover](tasks/task-16-cutover.md)
17. [Remove the old stack](tasks/task-17-remove-old-stack.md)
18. [Docs match code](tasks/task-18-docs-match-code.md)
