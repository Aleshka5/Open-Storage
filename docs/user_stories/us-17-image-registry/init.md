> **ID:** US-17
> **Status:** DONE
> **Specs:** [images.md](../../images.md), [ADR-0010](../../../adrs/10-published-images.md)

## User Story

**As** an operator, **I want** images built and pushed from one machine and started from the registry on another, **so that** the machine that serves traffic does not compile them.

**Acceptance**

- `REGISTRY` comes from the namespace env file. The compose file does not name the host.
- `make release` tags `$REGISTRY/<namespace>/<service>` with the local date `YYYY-MM-DD` and with `latest`, and pushes both.
- `make up` pulls `IMAGE_TAG` or `latest` and does not build.
- `make rebuild` builds from source and does not push.
- Postgres, Keycloak, Qdrant and the other upstream images are not pushed to `REGISTRY`.
