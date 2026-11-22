# task-05 Quotas

Story: [US-08](../init.md)

## Outcome

`user_quota_usage` reflects committed bytes in the new database, not cached numbers carried from the old one.

## Paths

- `open-storage-postgres`
- `POST /api/admin/maintenance/…` — the reconcile route in the legacy app's admin router

## Done when

The reconcile pass runs and its report is recorded (`checked`, `fixed`); after it, `total_bytes` equals the sum of committed `size_bytes` per user for every user; `private_bytes` and `photos_bytes` are consistent with their sections; a user's upload of a small file after the cutover shows in `total_bytes`.
