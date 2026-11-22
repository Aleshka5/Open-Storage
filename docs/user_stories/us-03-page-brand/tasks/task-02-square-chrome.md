> **ID:** task-02
> **Status:** DONE
> **Specs:** [US-03](../init.md), [brand book](../../../brand-book/init.md)

## Overview

Panels, fields, and focus rings on the resume page are square and have no drop shadow. The art lightbox and the owl chat sit on `document.body`. Files: `shell.css`, `chat.css`, `art.css`, `forms.css`, `base.css`, `Art.tsx`, and `OwlChat.tsx` under `src/auth-gateway/resume-page`.

## Goals

- Remove radius and drop shadow from the chat panel, the greeting bubble, art frames, code blocks, the account switch, and focus rings.
- Make `.btn-ghost` border match its fill. Set both faces on the chat field. Use `--accent-text` for a 2px focus ring.
- Mount the art lightbox and the owl chat on `document.body`.

## Non-goals

- The theme control and `theme.css`. Those are [task-01](task-01-theme.md).
- Rounding the owl hit target, the spine dots, or the owl progress ring.
- Changing chat behavior or the owl art.

## Definition of Done

- [x] The listed boxes have square corners, and the two drop shadows are gone.
- [x] `.btn-ghost` border matches its transparent fill. The chat field sets `color: var(--ink)`.
- [x] A 2px focus ring uses `--accent-text`. `--accent` is not used as text.
- [x] The art lightbox and the owl chat are mounted on `document.body`.
