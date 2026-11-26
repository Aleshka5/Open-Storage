# Frontend

Documents UI for the RAG product: file list, streamed chat, page preview. Served by nginx on port 3000. The browser reaches it through the gateway at `https://rag.filenkov.store`.

How it is built and which calls it makes: [backend contract](../../../docs/rag/frontend/backend-contract.md). Chrome and theme: [design](../../../docs/rag/frontend/design.md). What it must not store: [security](../../../docs/rag/frontend/security.md).

```bash
npm ci
npm test
npm run build
npm run dev
```

`npm run dev` proxies `/api` to `API_PROXY_TARGET` (default `http://127.0.0.1:8080`). The built app does not contain that address.
