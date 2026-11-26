# frontend — backend contract

The UI calls its own origin. Identity on the way in is [identity v1](../../auth-gateway/external-contracts/identity-v1.md). The edge that splits the paths is [rag](../init.md).

| UI | Call |
|---|---|
| File list, upload, delete, preview bytes | `/api/files` and `/api/files/{id}/content` |
| Chats and the answer stream | `/api/chats` |
| Sign in | hub `https://filenkov.store/auth?return_to=` — not this origin |

No `VITE_*` value is read at build time. The dev server proxies `/api` to `API_PROXY_TARGET`, default `http://127.0.0.1:8080`. That variable is not in the bundle.

Routes: `/` and unknown paths go to `/files`. `/files`, `/files/:fileId`, `/chat`, `/chat/:chatId`.

Build: `tsc -b && vite build`. nginx serves `dist` on port 3000 with `try_files` back to `index.html`. `index.html` is `Cache-Control: no-cache`. `/assets/` is immutable.
