# task-04 Verify

Story: [US-08](../init.md)

## Outcome

Every committed row has its object, every object has its row, and the sections list what the old stack listed.

## Paths

- A check script under `scripts/` if the other checks live there
- `docs/open-storage/` — the result

## Done when

For each `file_records` row with `status = 'COMMITTED'`, the object at its key exists and `mc stat` size equals `size_bytes`; the count of found objects equals the committed row count; the operator account's listing of files, photos, shared, resumes and generated returns the same ids and names as the old stack; a private file is readable after unlock; an object with no row and a row with no object are both zero, and each non-zero case is listed.
