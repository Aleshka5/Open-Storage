Shared visual contract for every page.
The interface language is English. Corners are square. A service page has no drop shadow.

---

## 1. Theme

Every page offers **light**, **Dark**, and **System**.

| Choice | Resolves to |
|---|---|
| Light | The light palette below. Ignores the OS. |
| Dark | The dark palette below. Ignores the OS. |
| System | light when `prefers-color-scheme: light` matches. Dark otherwise, including `no-preference`. Keeps listening to that query. |

Store the choice in `localStorage` under `theme.preference`. Allowed values are `light`, `dark`, and `system`. Persist the choice, never the resolved theme. A missing key, an unreadable store, or any other string falls back to `dark`. A private-mode storage failure is silent.

The resolved theme is `light` or `dark` only. Set it on the document element before first paint:

```html
<html lang="en" data-theme="dark" style="color-scheme: dark">
```

`color-scheme` is `light` when the resolved theme is light, and `dark` when it is dark. Put the same value in `<meta name="color-scheme">`.

Changing the theme does not reload the page. The key is a UI preference. It is not a credential. The page never stores a session in `localStorage`.

The control sits in the header’s right slot. It is a segmented group of three radios, `role="radiogroup"`, accessible name `Theme`. Labels are `light`, `Dark`, and `System`. Each segment is at least `2.25rem` tall, square, with no shadow. Selection is one thumb. It translates with `transform` over `--dur`. Its fill is `--paper-raised` at 55% opacity, with `backdrop-filter: blur(14px) saturate(1.7)`, a 1px translucent edge, and a 1px inset top hairline. `will-change: transform` applies only while that thumb moves. An unselected segment is transparent, its label is `--ink`, and its hover fill is `--chip`. Without `backdrop-filter`, the thumb’s fill is `--ink` and its label is `--paper`. Arrow keys move inside the group. At 620px the wordmark hides and this control stays.

Both palettes use the same token names. light copper text is `#8f4128`. Dark copper text is `#e0a181`. Do not mix them.

```js
var KEY = 'theme.preference'

function readPreference() {
  try {
    var stored = localStorage.getItem(KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  } catch (e) {}
  return 'dark'
}

function resolve(preference) {
  if (preference === 'light' || preference === 'dark') return preference
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

function apply(preference) {
  var theme = resolve(preference)
  var root = document.documentElement
  root.dataset.theme = theme
  root.style.colorScheme = theme === 'light' ? 'light' : 'dark'
  var meta = document.querySelector('meta[name="color-scheme"]')
  if (meta) meta.content = root.style.colorScheme
}
```

Run `apply(readPreference())` in a blocking script in `<head>`, before first paint. When the stored value is `system`, subscribe to `prefers-color-scheme` and call `apply` again. On change, write `theme.preference` and call `apply`.

---

## 2. Color

`--accent` is a mark, a bar, a selection, or a stroke of at least 3px. Copper text and a text-sized icon use `--accent-text`. Selection is `--accent` behind `--paper` text.

### light

| Token | Hex | Use |
|---|---|---|
| `--paper` | `#f4efe6` | Page background |
| `--paper-raised` | `#fffdf8` | Panels, tables, menus |
| `--surface-raised` | `#f7e7d8` | The one active raised surface |
| `--ink` | `#1a1612` | Body text. Primary button fill |
| `--ink-muted` | `#5c5348` | Secondary text |
| `--rule` | `#d9d1c3` | Hairlines, field borders |
| `--rule-strong` | `#b9ae9c` | A rule that must stay visible |
| `--accent` | `#b85c38` | Marks, bars, selection. Never text |
| `--accent-text` | `#8f4128` | Copper text, text-sized icons |
| `--chip` | `#e6ddd0` | Tags, ghost hover, neutral notices |
| `--danger` | `#8c2f24` | Errors, destructive actions |
| `--danger-wash` | `#f4e4dc` | Error notice background |

### Dark

| Token | Hex | Use |
|---|---|---|
| `--paper` | `#1c1b19` | Page background |
| `--paper-raised` | `#2a2824` | Panels, tables, menus |
| `--surface-raised` | `#33312c` | The one active raised surface |
| `--ink` | `#f4efe6` | Body text. Primary button fill |
| `--ink-muted` | `#a8a096` | Secondary text |
| `--rule` | `#45423c` | Hairlines, field borders |
| `--rule-strong` | `#6b655c` | A rule that must stay visible |
| `--accent` | `#c9794f` | Marks, bars, selection. Never text |
| `--accent-text` | `#e0a181` | Copper text, text-sized icons |
| `--chip` | `#33302a` | Tags, ghost hover, neutral notices |
| `--danger` | `#ff9a8a` | Errors, destructive actions |
| `--danger-wash` | `#3a2522` | Error notice background |

Put both blocks in one `theme.css`. `:root` carries the Dark tokens, so a missing `data-theme` still paints dark. `[data-theme="light"]` replaces every token.

### Buttons

`button`, `input`, `select`, and `textarea` set both `background` and `color`. A control that sets only one face is a bug. Disabled is `opacity: 0.55` and `cursor: not-allowed`. A primary action outside a table is at least 44×44px (`min-height: 2.75rem`). Header segments use `min-height: 2.25rem`.

| Class | Fill | Label | Hover |
|---|---|---|---|
| `.btn` | `--ink` | `--paper` | Fill `--accent-text`, label `--paper` |
| `.btn-ghost` | transparent | `--ink` | Fill `--chip`, label `--ink` |
| `.btn-danger` | transparent | `--danger`, border `--danger` | Fill `--danger`, label `--paper` |
| `.btn-small` | same role, shorter | header only | same role |

Border of `.btn` matches its fill. Hover and fill changes use `--dur-fast`.

### Notices

| Kind | Surface | Text | Border |
|---|---|---|---|
| Neutral banner | `--chip` | `--ink` | `--rule` |
| Error banner | `--danger-wash` | `--danger` | `--danger` |
| Failed view | page | `--danger` | 2px `--danger` on the left, plus one recovery button |
| Blocked status | — | `--danger`, weight 600 | a `<select>` with the status also takes a `--danger` border |

```html
<div class="banner">A neutral notice.</div>
<div class="banner error">Could not save the change.</div>
```

A toast uses those same two banners. It is `position: fixed`, square, with no shadow. Two toasts stack with `--s2` (`0.5rem`) between them. A toast stays clear of the primary control on that screen.

### Fields and rows

A field’s fill is `--paper`, its text is `--ink`, and its border is `1px solid var(--rule)`. A menu row is transparent with `--ink` text, and its hover fill is `--chip`. A raised panel is `--paper-raised` with a 1px `--rule`.

---

## 3. Motion

| Token | Value | Use |
|---|---|---|
| `--dur-fast` | `140ms` | Hover, small fades, the choice bar |
| `--dur` | `240ms` | Header, a view entering |
| `--dur-theme` | `700ms` | The theme circle |
| `--ease` | `cubic-bezier(0.2, 0, 0, 1)` | Every duration |

`prefers-reduced-motion: reduce` sets `--dur-fast`, `--dur`, and `--dur-theme` to `1ms`, disables the view entrance, skips the theme circle, draws no rim, and makes `scrollTo` use `behavior: 'auto'`.

| What moves | How |
|---|---|
| A view entering | Opacity `0 → 1` and `translateY(8px → 0)` over `--dur`, on `.view-in` only. Never on the X axis |
| Header show and hide | `translateY` and height, over `--dur` |
| Wordmark and service list in the condensed header | Opacity over `--dur-fast` |
| A choice row | A 2px `--accent` bar on the left, `scaleY(0 → 1)` from the top, over `--dur-fast` |
| A button | Background color over `--dur-fast` |
| A flipped theme | One circle from the control’s border box. `clip-path: circle()` on `::view-transition-new(root)` over `--dur-theme` with `--ease`. The new theme is inside. The old theme stays outside until the circle covers the viewport. No circle when the choice does not change the resolved theme, when the OS changes under System, under reduced motion, or without `startViewTransition` |
| The circle’s edge | A 36px band. Displacement is radial, at most 12px, from one SVG `feDisplacementMap` on that band only. Saturate 1.7 and a 1px specular hairline. The disk interior is not filtered. The filter is removed when the circle ends |
| Anything else | Still |

Mount a confirm dialog, a lightbox, or any other viewport layer on `document.body`. `.view-in` uses a transform, and a `position: fixed` child inside it centers on the view instead of the screen.

---

## 4. Common files

Serve these from the service itself. The page makes no request to a font CDN.

| Path | File |
|---|---|
| `/favicon.svg` | Diamond mark, below |
| `/fonts/fraunces-latin.woff2` | Fraunces roman, Latin |
| `/fonts/fraunces-latin-ext.woff2` | Fraunces roman, Latin extended |
| `/fonts/public-sans-latin.woff2` | Public Sans roman, Latin |
| `/fonts/public-sans-italic-latin.woff2` | Public Sans italic, Latin |
| `/fonts/public-sans-latin-ext.woff2` | Public Sans roman, Latin extended |
| `/fonts/public-sans-italic-latin-ext.woff2` | Public Sans italic, Latin extended |
| `theme.css` | Both palettes, button faces, banners, motion tokens |

`font-display` is `swap`. Family names stay `Fraunces` and `Public Sans`. Preload the two Latin files:

```html
<link rel="preload" as="font" type="font/woff2" href="/fonts/fraunces-latin.woff2" crossorigin />
<link rel="preload" as="font" type="font/woff2" href="/fonts/public-sans-latin.woff2" crossorigin />
```

Take the files from `@fontsource-variable/fraunces` and `@fontsource-variable/public-sans`, latin and latin-ext. If subsetting is impractical, one roman Fraunces file and one roman plus one italic Public Sans file are enough. Preload the files that cover Latin.

### Favicon

`/favicon.svg`. The hub may keep its own owl tab icon. Every other service uses this diamond.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" fill="#f4efe6"/>
  <path d="M16 3 L29 16 L16 29 L3 16 Z" fill="none" stroke="#1a1612" stroke-width="1.75"/>
  <circle cx="16" cy="16" r="3.2" fill="#b85c38"/>
</svg>
```

### Header mark

26×26. The stroke uses `currentColor`. The dot uses `--accent`, so it follows the theme. Link the wordmark to `https://filenkov.store`.

```svg
<svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
  <path d="M16 3 L29 16 L16 29 L3 16 Z" fill="none" stroke="currentColor" stroke-width="1.75"/>
  <circle cx="16" cy="16" r="3.2" fill="var(--accent)"/>
</svg>
```

### Grain

One layer on `body::before`: fixed, viewport-sized, `pointer-events: none`, `z-index: 0`, opacity `0.025`. It does not repaint on scroll. The page shell is `z-index: 1`.

```css
background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='120' height='120' filter='url(%23n)'/%3E%3C/svg%3E");
```

---

## 5. Check

1. `data-theme` is `light` or `dark` before first paint, and `color-scheme` matches it.
2. `theme.preference` is `light`, `dark`, or `system`. Anything else behaves as `dark`.
3. Buttons, fields, banners, and toasts use the tokens above and set both faces.
4. `--accent` is never text. Copper text is `--accent-text` from the active palette.
5. Motion uses `--dur-fast`, `--dur`, `--dur-theme`, and `--ease`. Reduced motion collapses the durations.
6. The tab icon and the header mark are the diamond in this file. Fonts are the self-hosted files.
