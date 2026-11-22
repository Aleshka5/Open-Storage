# task-01 One unavailable code

Story: [US-02](../init.md)

## Status

Done

## Outcome

`POST /api/chat` answers `503 {"error":"chat_unavailable"}` when the owl cannot run.

## Paths

- `src/auth-gateway/gateway/cmd/gateway/chat.go`
- `src/auth-gateway/gateway/internal/chat/chat.go`
- `src/auth-gateway/gateway/internal/edge/edge.go`

## Done when

- A nil llm client and a missing `llm` block both write `chat_unavailable` and no stream.
- `go test` covers both.
- The handler no longer writes `chat is not configured`.
