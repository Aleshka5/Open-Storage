## Status

Superseded by [ADR-0009](0009-owl-chat-in-the-gateway.md).

## Decision

The resume page ships without the owl chat. `POST /api/chat` stays in `config.yaml` as a `public` route that proxies to LiteLLM with `X-Api-Key` injected, so the endpoint exists; no page calls it.

The old stack's chat pipeline — a hand-written prompt, `nodes.json` generated from the node folders, inline `<think>` stripping, and OTLP tracing to MLflow — does not port.

## Rejected

A chat handler inside the gateway. The behaviour is about 350 lines plus a prompt asset, against a 2,000-line budget that is already at its limit ([ADR-0005](0005-port-from-auth-service.md)).

Rewriting the SPA client against LiteLLM's OpenAI stream shape now. That changes `chat.ts`, the answer renderer and the node-link resolver in the same release that changes the whole identity layer.

## Cost

Readers lose the owl until US-02. The route stays warm, so the return is a page change plus the handler, not a new contract.

## Because

The owl answers questions about the resume, not about identity. It is the only feature of the old page that does not have to move for the cutover to be correct, and it is the largest block of code that would compete with the identity rewrite for room in the gateway.
