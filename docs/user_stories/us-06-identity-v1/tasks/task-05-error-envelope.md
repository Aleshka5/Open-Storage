# task-05 Error envelope

Story: [US-06](../init.md)

## Outcome

The app keeps its own envelope for its own errors and passes the gateway's errors through. One envelope per writer, and a proxied error is not rewritten.

## Paths

- `src/open-storage/app/app/presentation/exception_handlers.py`
- `src/open-storage/app/tests/` — the envelope test

## Done when

An app error still answers `{"detail": {"error_code": ..., "message": ...}}` and a test states that shape; a proxy-style request to a route the app does not own answers whatever the gateway sent (`{"error": "..."}`), and the app does not wrap it; the app adds no handler that rewrites a body it did not produce; the story records that the edge owns the edge errors and the app owns its own.
