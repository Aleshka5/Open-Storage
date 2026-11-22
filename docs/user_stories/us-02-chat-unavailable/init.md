# US-02 Chat unavailable code

## Story

As a reader of the resume, I want `POST /api/chat` to answer `chat_unavailable` when the owl has no model, so a missing model is one code and not a sentence.

## Status

Done

## Scope

The gateway chat handler and the edge path that calls it. The contract already states the code. This story makes the handler match it.

## Acceptance

- No usable llm client: `503 {"error":"chat_unavailable"}` before any byte of the stream.
- A missing `llm` block and a nil client from `newChat` use that same code.
- A test locks both paths.
- The owner of the code stays the [gateway API contract](../../auth-gateway/gateway/api-contract.md) and [ADR-0009](../../auth-gateway/adrs/9-owl-chat-in-the-gateway.md).

## Out of scope

- The sentence a bad question returns (`question is empty`, and the length limit).
- The line budget.
- Storing chat history.

## Task

1. [One unavailable code](tasks/task-01-unavailable-code.md)
