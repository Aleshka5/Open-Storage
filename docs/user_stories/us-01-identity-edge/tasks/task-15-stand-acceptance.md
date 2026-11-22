# task-15 Stand acceptance

Story: [US-01](../init.md)

## Outcome

The stand matches the contracts before cutover. Run `scripts/verify-edge.sh` and the checks below.

## Done when

- A guest on `https://storage.filenkov.store/` gets `302`. `GET /api/files` gets `401`.
- Login through `/auth/login` sets cookies. `GET /auth/session` returns the profile.
- `return_to=https://evil.example.com/` does not leave the allowlist.
- `stranger` gets `403` and `family` gets `200` on `image.filenkov.store`.
- Removing the last admin returns `409`.
- A WebSocket (Grafana Live, Jitsi signaling) and an SSE chat stay up longer than 5 minutes.
- All nine hosts return the expected code for anonymous, signed-in, and admin.
- `403` is JSON, not HTML.
- Gateway logs contain no tokens.
