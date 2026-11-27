# Processor

Worker of the `doc.process` queue. Reads the PDF from MinIO, extracts text with PyMuPDF, calls OCR for pages with no text layer, chunks text with the EmbeddingGemma 2 tokenizer, computes embeddings in batches, and writes points to Qdrant.

The algorithm norm was `docs/processing.md`, `docs/messaging.md`, `docs/data-models.md` in the legacy tree; this directory follows them. The namespace entry is [docs/rag/init.md](../../../docs/rag/init.md).

## Run

A process with no HTTP port. Required variables: `MONGODB_URI`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `QDRANT_URL`, `RABBITMQ_URL`, `EMBEDDING_URL`, `OCR_URL`. A missing variable stops the start and logs only its name.

```bash
uv sync --all-groups
uv run python -m processor
```

Image: `Containerfile` (the same text as `Dockerfile`), built with `podman build -f Containerfile`. Dependencies install through `uv` from `uv.lock`. `requirements.txt` exports the same packages; the lock is canonical.

On the consumer channel **prefetch=1**. `PROCESSOR_CONCURRENCY` (default 1) is the number of such channels, not the prefetch size.

## Pipeline

1. A message with an unknown `schema_version` or bad JSON — `nack` without requeue. A foreign `user_id` or `s3_key` — the same, the file status does not change.
2. `ready`, `deleting`, `deleted` — `ack`, no MinIO, no Qdrant.
3. `uploaded`, `error`, `processing` — conditional move to `processing` (`error=null`). A first delivery sets `checkpoint.process_attempts=1`; a redelivery increments it. Above `MAX_PROCESS_ATTEMPTS` (8) — `error=processing_attempts_exceeded` and dead-letter.
4. PyMuPDF opens the PDF. Failure — `error=corrupt_pdf`, the document stays in `files`. `page_count` and `checkpoint.pages_total` are written right after the open.
5. A page already in `file_pages` is neither rendered nor sent to OCR. Otherwise `page.get_text("text")`: longer than `MIN_EXTRACTED_CHARS` — `origin=text`; else PNG at `OCR_RENDER_DPI` and `POST /ocr`. Empty OCR text — `origin=empty`, which is success. `checkpoint.pages_done` moves through `$max` and never shrinks.
6. Chunks are a sliding window of `CHUNK_TOKENS` / `CHUNK_OVERLAP_TOKENS` over tokens from the `tokenizer.json` of `EMBEDDING_MODEL` (GGUF revision `914f7f89142e33e77833254d9c9b90c3cef7303b`). A point stores raw text, without the `title` prefix.
7. Embedding: `POST /embed`, `input_type=document`, `title` — the `file_name` from MongoDB, a batch no larger than `EMBEDDING_BATCH_SIZE` (16). Then upsert into Qdrant, id `uuid5(a5b3c1d2-6e47-5f80-9c11-0d4e8f2a7b65, "{file_id}:{chunk_index}")`, tenant filter `user_id`.
8. When `chunks_done == chunks_total`, the tail `chunk_index >= chunks_total` is deleted. Conditional move `processing → ready`. If the file already left `processing`, no new points are written, the file's points are deleted, and the message is `ack`ed.
9. MinIO, OCR, Embedding, Qdrant or MongoDB failing after short retries — a temporary fault: the status stays `processing`, a pause of `min(60, 2^process_attempts)` seconds, `nack(requeue=true)`. On the 8th failed delivery the same fault is permanent: `embedding_failed`, `index_write_failed` or `storage_read_failed`, then `nack` without requeue, and the broker routes the message to `doc.processing.dead`. It never returns unacknowledged to the working queue.
10. At start and then every `SWEEP_INTERVAL_SECONDS` the sweeper publishes a fresh `doc.process` only for `error=enqueue_failed` older than `UPLOAD_REQUEUE_AFTER_SECONDS`.

The RabbitMQ topology is declared idempotently: `doc_events`, `doc_events_dlq`, queues `doc.processing`, `doc.deletion`, `doc.processing.dead`, `doc.deletion.dead`.

## Tests

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

OCR, Embedding and Qdrant are substituted in tests. Real HTTP clients are checked through `httpx.MockTransport`. No GPU needed.
