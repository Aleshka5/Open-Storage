# ADR-0006 The theme control's geometry has one owner per frame

## Status

Accepted. It settles what [ADR-0004](4-liquid-glass-theme-control.md) item 4 left implicit, after [US-10](../docs/user_stories/us-10-liquid-glass-theme-control/init.md) shipped a blob that mounted but did not move.

## Decision

1. One owner. The blob's position, size and radius are written by one frame loop and by nothing else. No CSS `transition`, no `@keyframes` and no React state may write those five values: a loop and a transition writing the same property is the bug that made the blob stand still while the state machine said `open`.
2. The loop reads the layout, then writes. Each frame it measures the trigger's box, the panel's box and the rows, computes one geometry, and paints. It measures nothing inside the paint.
3. The blob lives in one fixed viewport layer portalled to the body, so no ancestor's stacking context, `overflow` or containing block decides where it is. The panel is in the same layer for the same reason.
4. The pointer is read from one `pointermove` listener on the document, bound on every render, and the row under the pointer is derived from the pointer's coordinate against the row boxes. Per-element enter events are not trusted: a global move reports none.
5. The spring is the only damping. A settle ends the loop; a closed popover requests no frame. Reduced motion places the geometry without a loop.
6. The geometry is a pure function with a test per rule. A rule that no test can reach is not a rule.

## Rejected

- A CSS transition on `left`/`top`/`width`/`height` with React state for the pointer. State flushes once per render, so the blob lags a frame and then a burst, and a transition on layout properties fights the loop.
- A per-row `:hover` fill. It cannot morph: the selection would jump between two boxes instead of one body travelling.
- An event per row (`pointerenter` on each row). A pointer that moves fast skips rows, and a global move fires none.
- A blob inside the header's subtree. The header's stacking context, its `overflow` and its fixed position are the header's business, not the blob's.

## Cost

One listener and one loop, both released with the popover. The blob is not part of the trigger's subtree, so it cannot be styled by the trigger's selectors and is themed by tokens only.

## Risk

A loop that forgets to stop burns a core. The settle rule and the dispose path are locked by tests, and the closed state is verified to request no frame, not assumed to.
