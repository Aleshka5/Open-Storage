# frontend — design

The documents UI. Stack and routes are [backend-contract.md](backend-contract.md). What the page may know about the caller is [security.md](security.md).

Theme, palettes, type, and chrome follow the [brand book](../../brand-book/init.md). The store is the session cookie in [brand book §1](../../brand-book/init.md) ([ADR-0007](../../../adrs/7-theme-preference-is-a-session-cookie.md)). The header’s `Theme` control changes it without a reload. The thumb is one rounded glass square, [ADR-0006](../../../adrs/6-glass-thumb-is-a-rounded-square.md). Palettes live in `src/styles/theme.css`. A blocking script in `index.html` paints before first load. Scroll hides the header through `public/header.js`.

The header wordmark links to the hub. The current service name is Documents. Files and Chat are this product’s section links. The right slot is the theme control and Sign in. Sign in opens the hub `/auth` page with `return_to` set to the current URL. There is no local sign-in form. This host has no account probe, so the slot does not show a name or Sign out ([security](security.md)).

Skip link, grain, footer, self-hosted fonts, and the diamond tab icon are the shared shell in the [brand book](../../brand-book/init.md). This frontend serves the font files and `/favicon.svg`. The footer names this product Documents.

The product screens are the file list, the chat, and the page preview. Those screens are not part of the shared shell.
