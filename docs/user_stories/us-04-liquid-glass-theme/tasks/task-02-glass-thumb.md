> **ID:** task-02
> **Status:** TODO
> **Specs:** [US-04](../init.md), [brand book §1](../../../brand-book/init.md)

## Overview

Replace the solid selected segment with one sliding glass thumb. The radiogroup, the labels, arrow keys, and the 620px rule stay.

## Goals

- One thumb translates with `transform` over `--dur`.
- Glass is `backdrop-filter`. Without it, the thumb is the solid `--ink` face.
- The thumb is the only glass this story leaves on the page.

## Non-goals

- The circle and the rim.
- A second `localStorage` key.

## Definition of Done

- [ ] The thumb slides, and the solid `--ink` face is the fallback.
- [ ] Brand book §1 describes that thumb and that fallback.
