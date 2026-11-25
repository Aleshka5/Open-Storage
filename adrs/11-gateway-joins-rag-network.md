# ADR-0011 The gateway joins rag_network, and rag_edge is removed

## Status

Accepted

## Decision

The gateway reaches the RAG product on `rag_network`, the network [ADR-0009](9-rag-namespace.md) names as created by the `rag` namespace. `deploy/auth-gateway/docker-compose.yaml` declares `rag_network` `external: true` in place of `rag_edge`, and the gateway joins only it. The legacy network `rag_edge`, created by the old `RAG-Chat` compose, is removed together with the `rag-chat_*` containers.

The host row in `src/auth-gateway/gateway/config.yaml` does not change: `rag.filenkov.store`, upstream `rag-edge:8080`, `policy: "service(rag, family, admin)"`, `/health` public. Who passes is decided by the realm role `svc:rag:{admin,family,blocked}`, granted through `/admin`, not by a per-host allow-list.

## Rejected

Keeping `rag_edge` and renaming the network the `rag` namespace creates, which makes a decision we recorded follow the compose of a stack we are retiring. An extra network attached for the transition, which is attack surface the gateway does not need and a second live name for one meaning ([ADR-0001](1-one-contract-version.md)). A per-host role list in the gateway config, which puts identity data outside the idp ([ADR-0002](2-roles-in-the-token.md)).

## Cost

The gateway container is recreated and every product behind it is unreachable for the length of one `make up`. Until the `rag` stack's images are published and pulled, `rag.filenkov.store` answers `502 bad_gateway` — a correct answer for a host whose upstream does not exist yet, and the reason this ADR lands with the stack rather than before it.

## Risk

Two networks named for one product exist in the interval, and a stand that joins `rag_edge` by mistake would still resolve a legacy `rag-edge` container if one were ever started again. The removal of `rag_edge` and the `rag-chat_*` containers is part of the same change, so the interval ends with the cutover commit, not with a later cleanup.
