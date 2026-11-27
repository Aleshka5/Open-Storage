## Status

Accepted. Supersedes ADR-0007 (`gateway-line-budget`, 4200 lines), removed from this index.

## Decision

The gateway's Go budget is **5500 lines, tests excluded**, measured over `src/auth-gateway/gateway`.

Measured after the owl chat landed:

| Package | Lines | What it is |
|---|---|---|
| `internal/config` | 809 | the YAML shape, the eleven startup rules, host/route compilation, matching |
| `internal/edge` | 970 | routing, identity, the reverse proxy, probes, the in-process rate limit, the metric registry |
| `internal/adminapi` | 627 | four `/admin` endpoints plus the Keycloak Admin API client |
| `internal/bff` | 510 | login, callback, logout, session, token refresh, idp logout |
| `internal/oidc` | 476 | discovery, JWKS cache, access and id token rules |
| `internal/llm` | 482 | the owl's OpenAI-compatible client, prompt, and node map |
| `internal/session` | 395 | the sealed cookie, the flow cookie, single-flight refresh |
| `cmd/gateway` | 267 | wiring, the chat constructor, shutdown |
| `internal/chat` | 152 | `POST /api/chat` |
| `internal/policy` | 135 | expressions and the blocked rule |
| `internal/tracing` | 105 | OTLP export for the owl |
| `internal/log` | 25 | JSON logger |
| **total** | **4953** | |

## Rejected

Leaving the cap at 4200 and cutting the owl packages back under it. [ADR-0009](9-owl-chat-in-the-gateway.md) put those packages in this process, and the 4200 figure was the measurement from before they existed.

Counting tests, or counting the SPA, to reach a round number.

## Cost

The cap is a ceiling on growth. 5500 is the measurement above plus about 500 lines of headroom, the same margin ADR-0007 kept. A change that pushes past 5500 needs a new ADR. The check stays:

```bash
find src/auth-gateway/gateway -name '*.go' ! -name '*_test.go' | xargs cat | wc -l
```

## Because

ADR-0007 measured 3685 lines and set 4200. The chat, the model client, and tracing are 739 of the lines now present, and the packages that already existed grew while the port settled. 4953 is what the tree measures. The headroom is for the next contract change, not for a second copy of the owl.
