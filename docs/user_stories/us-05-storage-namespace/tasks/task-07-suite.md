# task-07 Suite from the new location

Story: [US-05](../init.md)

## Outcome

The backend test suite runs from `src/open-storage/app` with the same file list and the same result, with no test importing the legacy checkout.

## Paths

- `src/open-storage/app/tests/`
- `src/open-storage/app/pyproject.toml` (or `pytest.ini`) carrying the test path and `pythonpath`

## Done when

`pytest --collect-only -q | wc -l` equals the legacy count for `backend/tests`; `pytest` passes; `grep -rn "WebStorage" src/open-storage --include='*.py'` finds nothing; the SPA's `npm test` runs from `src/open-storage/spa`.
