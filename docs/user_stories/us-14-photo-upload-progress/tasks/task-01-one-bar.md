> **ID:** task-01
> **Status:** TODO
> **Specs:** [US-14](../init.md)

## Overview

The photos page reports one batch meter and sends at most two uploads at a time. Success toasts and per-file upload toasts go away.

## Goals

- One size-weighted bar, capped at 99 until every request in the pick has settled.
- A pool of two. Photos still appear as each `201` arrives. Quota reloads once per successful pick.

## Non-goals

- The file manager’s upload bar and its success toast.
- The upload route’s wait on indexing.

## Definition of Done

- [ ] `usePhotoUpload` no longer toasts progress or success.
- [ ] `PhotoUploadFab` renders one bar for the active pick.
- [ ] A test locks the batch percent and the cap of two in flight.
