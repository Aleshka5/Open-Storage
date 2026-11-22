## Status

Superseded by [ADR-0010](10-gateway-line-budget.md). The measurement below is the one this decision was accepted on.

## Decision

The gateway's Go budget is **4200 lines, tests excluded**, measured over `src/auth-gateway/gateway`. It replaces the 2000-line figure in the namespace README.

Measured at the end of the port:

| Package | Lines | What it is |
|---|---|---|
| `internal/config` | 726 | the YAML shape, the eight startup rules, host/route compilation, matching |
| `internal/edge` | 851 | routing, identity, the reverse proxy, probes, the in-process rate limit, the metric registry |
| `internal/adminapi` | 594 | four `/admin` endpoints plus the Keycloak Admin API client |
| `internal/bff` | 481 | login, callback, logout, session, token refresh, idp logout |
| `internal/oidc` | 405 | discovery, JWKS cache, access and id token rules |
| `internal/session` | 338 | the sealed cookie, the flow cookie, single-flight refresh |
| `internal/policy` | 135 | expressions and the blocked rule |
| `cmd/gateway` | 130 | wiring and shutdown |
| `internal/log` | 25 | JSON logger |
| **total** | **3685** | |

## Rejected

Cutting to 2000 by dropping contract surface: `/admin` (594), the metric registry (185), the per-flow cookies (338), or the eight startup rules. Each of those is a row in a contract, so the cut would be a specification change wearing a budget's clothes.

Counting tests, or counting the SPA, to reach a round number. Both are lies about what the cap measures.

## Cost

The cap is now a ceiling on growth, not a target: any change that pushes past 4200 needs a new ADR with the measured reason, and the check stays mechanical:

```bash
find src/auth-gateway/gateway -name '*.go' ! -name '*_test.go' | xargs cat | wc -l
```

## Because

The 2000-line figure was written before the design had a BFF, an admin client, a JWKS cache and a metric registry in one process — those are four of the six contracts, and they are 2,400 lines before any glue. The figure was a guess about a gateway that only proxied. 4200 is the measurement of the gateway the contracts actually describe, with about 500 lines of headroom for the next contract change.
