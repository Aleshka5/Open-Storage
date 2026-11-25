# rag

Documents in, answers out, with citations. Upload a PDF, DOCX, XLSX or an image; the stack extracts text, OCRs a scan, chunks, embeds and indexes; a question returns a streamed answer with the pages it came from.

Bring up [common](../common/README.md) first. Then copy [deploy/rag/.env.example](../../deploy/rag/.env.example) to `.env` beside it, fill the empty variables, and from `deploy/rag/` run `make doctor` and `make up`. `make up` pulls the published images. `make release` builds and pushes them. The procedure is [images.md](../images.md). The browser reaches the product at `https://rag.filenkov.store`, through the gateway; no container publishes a host port.

The stack is nine containers: `rag-rag-edge`, `rag-file-collector`, `rag-processor`, `rag-deletion-worker`, `rag-chat`, `rag-frontend`, `rag-embedding`, `rag-ocr`, `rag-qdrant`. MinIO, RabbitMQ and Mongo are the [common](../common/README.md) services on `common_network`.

How the pieces fit is [init.md](init.md). The move in from the old `RAG-Chat` repository is [US-16](../user_stories/us-16-rag-namespace/init.md); the decision is [ADR-0009](../../adrs/9-rag-namespace.md).
