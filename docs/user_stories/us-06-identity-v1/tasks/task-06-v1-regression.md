# task-06 v1-only regression

Story: [US-06](../init.md)

## Outcome

One test sends a request carrying only v1 headers and is sufficient to fail if a legacy header ever becomes load-bearing again.

## Paths

- `src/open-storage/app/tests/test_identity_headers.py` — replaces the legacy header tests

## Done when

A request with only `X-Auth-Subject`, `X-Auth-Email`, `X-Auth-Name`, `X-Auth-Roles` reaches each section and answers as its role allows; a request adding `X-User-Id` and `X-Storage-Role` answers the same, so those names change nothing; a request with only `X-User-Id` and `X-Storage-Role` answers 401; the shared, admin, vault and photos routes each appear in the test.
