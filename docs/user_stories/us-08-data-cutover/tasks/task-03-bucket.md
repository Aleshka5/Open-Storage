# task-03 Copy the bucket

Story: [US-08](../init.md)

## Outcome

The `storage` bucket exists in the namespace's MinIO with the same keys and the same object count.

## Paths

- Source: `http://minio:9000` bucket `storage`, host data `/media/aleksey/HardDisk/minio/storage`
- Target: `open-storage-minio` bucket `storage`

## Done when

`mc mirror` runs source to target with `--preserve`; `mc ls --recursive --summarize` on both sides reports the same object count and the same total bytes; the prefixes `users/`, `shared/`, `files/` and `_meta/` exist on the target; the copy is from the source endpoint, not from the host directory, so MinIO's `xl.meta` layout is not carried by hand.
