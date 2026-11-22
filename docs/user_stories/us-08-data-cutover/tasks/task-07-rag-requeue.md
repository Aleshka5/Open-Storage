# task-07 Re-queue RAG

Story: [US-08](../init.md)

## Outcome

The `file_index_links` rows are re-queued against the new location and search answers again — proven by a query, not assumed from a queue count.

## Paths

- `open-storage-postgres` — `file_index_links`
- `src/open-storage/app/app/infrastructure/database/repositories/file_index_link_repo.py` — the due-queue predicate
- `RAG_ENABLED`, `RAG_BACKFILL_ENABLED`, `RAG_BASE_URL` in `deploy/open-storage/.env`

## Done when

The due-queue predicate is read and its exclusions named (`state IN (…)`, `section != PRIVATE`, `next_attempt_at`), because an exclusion here is what empties a page; `RAG_BASE_URL` points at the reachable edge; `file_index_links` rows are reset to the due state in a way that keeps `rag_file_id` consistent with the RAG side; `RAG_ENABLED=true` only after the queue drains; a photo search and a file search each return results for a known gap, and a section with no rows is distinguished from a section whose rows were filtered out.
