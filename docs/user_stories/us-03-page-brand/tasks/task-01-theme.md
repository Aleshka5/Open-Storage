# task-01 Theme

Story: [US-03](../init.md)

## Outcome

The resume page resolves `light`, `Dark`, and `System` before first paint, and the header can change that choice without a reload.

## Paths

- `src/auth-gateway/resume-page/index.html`
- `src/auth-gateway/resume-page/src/styles/theme.css`
- `src/auth-gateway/resume-page/src/styles/tokens.css`
- `src/auth-gateway/resume-page/src/components/Layout.tsx`

## Done when

- A blocking script in `<head>` runs the brand book’s `readPreference` / `resolve` / `apply` before first paint. The stored value is the preference, under `theme.preference`.
- `theme.css` holds both palettes, the button faces, the banner faces, and the motion tokens. `:root` is the dark palette. `[data-theme="light"]` replaces every color token. `--surface-raised` and `--danger-wash` exist. The error banner uses `--danger-wash`.
- The header right slot has the `Theme` radiogroup from the story. Session controls stay beside it.
- The wordmark destination is `https://filenkov.store`, as an in-app navigation to `/` on that origin.
