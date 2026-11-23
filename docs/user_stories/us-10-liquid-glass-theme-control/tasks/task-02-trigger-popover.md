> **ID:** task-02
> **Status:** DONE
> **Specs:** [US-10](../init.md), [ADR-0004](../../../../adrs/4-liquid-glass-theme-control.md)

## Overview

`src/components/ThemeControl.tsx` becomes a trigger and a popover. The reveal, the persistence and the `Header` props stay as they are.

## Goals

- A `button` trigger with `aria-haspopup="dialog"`, `aria-expanded`, and a tooltip `Theme`.
- A popover of three rows, each a `radio`, in a `radiogroup` named `Theme`, with the icons of [ADR-0004](../../../../adrs/4-liquid-glass-theme-control.md).
- The pointer state machine: 120ms intent, 400ms grace, `Escape`, outside press, `Tab` out.
- Keyboard: arrows, `Home`/`End`, `Enter`, `Space`.
- The same `onChange(value, origin, group)` the header already passes.

## Non-goals

- The blob: that is [task-03](task-03-blob.md).
- A change to `themeReveal.ts`, `theme.ts`, or the header.

## Definition of Done

- [x] The control is one file for the component and one for its stylesheet, replacing the segmented markup and the segmented CSS.
- [x] The state machine is a tested module, not handlers spread over JSX.
- [x] `Header` compiles without a change to its props.
