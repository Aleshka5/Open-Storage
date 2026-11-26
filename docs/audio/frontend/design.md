# audio frontend — design

The Audio page. Served by nginx in `audio_network`, reached only through the gateway. The namespace map is [audio](../init.md).

Stack: Vite, React 18, TypeScript, react-router 6, CSS variables. One route, `/`, renders the recording workspace. Theme, palettes, type, and the header thumb follow the [brand book](../../brand-book/init.md). The store is the session cookie in [brand book §1](../../brand-book/init.md) ([ADR-0007](../../../adrs/7-theme-preference-is-a-session-cookie.md)). The thumb is one rounded glass square, [ADR-0006](../../../adrs/6-glass-thumb-is-a-rounded-square.md).

The header is the product header: wordmark to `https://filenkov.store`, the current service name `Audio`, the theme control, and sign-in state. The workspace under it — recordings, chat, player, microphone — is this product. Fonts and the diamond tab icon are served by this frontend.

`npm run dev` proxies `/api` to `API_PROXY_TARGET` (default `http://localhost:8000`). That name is not read by the bundle.
