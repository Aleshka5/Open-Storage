# AGENTS.md

High-level routing. The rules themselves live in the documents below.

Read first
 - constitution.md — development rules that do not depend on a stack.
 - docs/init.md — namespaces and the system map.
 - docs/<namespace>/init.md — how the services inside one namespace interact.
 - docs/<namespace>/<service>/init.md — what that service offers.
 - docs/<namespace>/frontend/ — page design, and the security and backend contracts for that UI.
 - docs/<namespace>/external-contracts/ — contracts with systems outside the namespace.
 - docs/<namespace>/adrs/ — decisions that bind one namespace.
 - adrs/ — decisions that bind the whole system.
 - deploy/<namespace>/ — env example, Makefile, and compose for that namespace.
 - src/<namespace>/<service>/ — service code. tests/ inside the service.
 - scripts/ — checks and setup scripts. Not written yet.

While editing
 - Write in English.
 - Keep the document short. Add another short document instead of extending a long one.
 - Link to the document that owns a fact. Do not copy the fact.
 - Record a decision in an ADR before implementing it.
 - Update the contract in the same change as the behavior it describes.
 - Do not add application code in a documentation-only change.

Current map
 - Namespace auth-gateway is the identity and edge layer. Docs: docs/auth-gateway/. Deploy: deploy/auth-gateway/. Code will live in src/auth-gateway/.
 - auth-gateway is one block. It asks Google for login, asks Keycloak (inside the namespace) for identity, and calls product upstreams as resources: storage, image, rag, audio, llm, observer, meet, switch, litellm.
 - hermes and lite-llm are outside this SSO contract. The proxy forwards them to local ports; hermes keeps a LAN and WireGuard gate.
 - Application code lives in src/auth-gateway/: gateway (Go), idp (realm as code), proxy (Caddyfile), resume-page (SPA). Deploy is deploy/auth-gateway/.
