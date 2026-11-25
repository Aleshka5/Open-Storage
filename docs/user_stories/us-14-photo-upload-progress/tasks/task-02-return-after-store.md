> **ID:** task-02
> **Status:** TODO
> **Specs:** [US-14](../init.md), [photos API](../../../open-storage/app/api-contract.md)

## Overview

`POST /api/photos/upload` currently awaits the immediate index notify after commit. That wait ends. The queue row stays.

## Goals

- The `201` follows the committed original.
- Index notify still runs and still must not fail the upload. It does not hold the response.

## Non-goals

- Delete, file upload, and zip upload.
- Writing the JPEG preview inside the request.

## Definition of Done

- [ ] A blocking notify does not delay the upload response. The status stays `201`.
- [ ] The photos row in the API contract matches D3.
