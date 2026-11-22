# task-08 Decommission

Story: [US-08](../init.md)

## Outcome

The old stack and the old repository are retired, after a review point, with the dump and the bucket copy still on disk.

## Paths

- `~/projects/WebStorage` — the legacy repository
- `Auth-Service/deploy/Caddyfile.filenkov` — the storage site block, already removed in [task-06](task-06-switch.md)
- `~/backups/storage-cutover/`

## Done when

The rollback window has passed and nobody has asked for it; the old stack's containers are removed and its volumes are deleted only after the dump and the bucket copy are verified readable; the legacy repository is archived or removed, with a pointer to this repository in its README; the shared `common_network` `storage` database and bucket are dropped only after the same check, and `mlflow` and the other buckets are untouched.
