> **ID:** US-14
> **Status:** TODO
> **Specs:** [photos API](../../open-storage/app/api-contract.md), [spa](../../open-storage/spa/init.md)

## Overview

On `/photos`, picking many pictures starts one `POST /api/photos/upload` per file at the same time. Each file has its own meter. A file over 5 MiB also toasts `Uploading … N%`, then `Saving …`. Every success toasts `File uploaded`. The grid inserts the photo and refetches quota on each `201`.

The phone sits on that wait. A batch shares one radio, so a single photo’s meter climbs only as far as its own bytes are accepted and often rests near a third until the others move. The handler stores the original, commits, then awaits the immediate index notify before the `201`. While that notify or an S3 write runs, the server is not reading the other bodies.

Preview generation is already a background task. [API contract](../../open-storage/app/api-contract.md) still says the upload “make its JPEG preview”; the handler returns a `PhotoItem` whose preview may not exist yet. `GET …/preview` serves the original when the preview file is missing. This story does not change that.

Tasks: [one bar](tasks/task-01-one-bar.md), [return after store](tasks/task-02-return-after-store.md).

## Locked decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | One batch meter on the photos page, weighted by file size. It stays at most 99 while any selected photo has not returned. No per-photo row, no upload toast, no success toast. A failed photo still toasts the API error. | A toast per photo. A toast when the batch finishes. Keeping the per-file dock. |
| D2 | At most two photo uploads in flight. Further files wait. Each `201` still inserts that photo. Quota is read once, after the batch, and only if one photo was stored. | `Promise.all` over the whole pick. One upload at a time. |
| D3 | `POST /api/photos/upload` answers after the original is stored and the request transaction is committed. The index notify is not on that wait. The queue row from the upload remains. Preview generation stays off the response. | Awaiting RAG before the `201`. Generating the JPEG preview before the `201`. |

## Goals

- A large pick from a phone moves one bar and does not toast each photo.
- Two uploads overlap; the rest do not start until a slot is free.
- The `201` does not wait on indexing.

## Non-goals

- File, shared, zip, and private uploads, and their toasts.
- Photo delete, and the index notify on delete.
- Preview size, format, or when the JPEG is written.
- A new upload URL or a multipart batch endpoint.

## User Story

**As** a person adding many photos from a phone, I want one progress bar and a response as soon as each original is stored, so the pick does not sit still and I am not told about every photo.

**Acceptance**

- Selecting several images shows one progress bar for the batch and no per-photo meters.
- No toast says a photo is uploading, saving, or uploaded. A rejected photo still shows its error toast.
- While any photo in the pick is in flight, the bar’s value is under 100. It leaves when the pick has settled.
- At most two `POST /api/photos/upload` calls run at once. A stored photo appears in the grid when its `201` arrives. Quota reloads once per pick that stored something.
- The upload `201` is sent without waiting for the index notify. A slow or failed notify does not change the status code. The photo remains queued for indexing.

## Definition of Done

- [ ] `npm test` and `npm run build` pass in `src/open-storage/spa`.
- [ ] An app test locks that a blocking index notify does not delay `POST /api/photos/upload`.
- [ ] [API contract](../../open-storage/app/api-contract.md) says the upload `201` follows the stored original, and that preview and index notify are not on that wait. [spa/init.md](../../open-storage/spa/init.md) names the one bar in the `/photos` row and does not restate the rules above.
