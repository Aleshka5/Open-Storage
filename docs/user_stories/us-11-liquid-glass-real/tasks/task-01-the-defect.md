> **ID:** task-01
> **Status:** TODO
> **Specs:** [US-11](../init.md), [ADR-0006](../../../../adrs/6-one-owner-per-frame.md)

## Overview

The blob of [US-10](../../us-10-liquid-glass-theme-control/init.md) mounts and takes a shape, but it does not travel with the pointer: `ThemeControl.css` transitions `left`/`top`/`width`/`height` on the bubble while `themeBlob.ts` writes the same properties from a frame loop, and the pointer state is read through a listener bound to the render that opened. This task removes both writers of the same value before any new effect is added.

## Goals

- Delete every CSS `transition` and `@keyframes` that writes a blob or bubble geometry value; keep transitions on colour only.
- Bind one `pointermove` listener per render and derive the row from the pointer's coordinate.
- Assert the closed state requests no animation frame.

## Non-goals

- Any pixel of new material. That is [task-02](task-02-material.md) and [task-03](task-03-refraction.md).
- A geometry change.

## Definition of Done

- [ ] `grep -n 'transition' ThemeControl.css` shows no geometry property, and a test fails if one returns.
- [ ] With the popover open, a pointer moved across three rows moves the blob each time; measured on the running page.
- [ ] With the popover closed, a 2s window records zero `requestAnimationFrame` calls from the control.
