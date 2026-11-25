> **ID:** US-16 task-01
> **Status:** DONE
> **Specs:** [ADR-0009](../../../../adrs/9-rag-namespace.md), [repository layout](../../../repository-layout.md), [US-16](../init.md)

## Overview

The tree moves from `~/projects/RAG-Chat` into `src/rag/` and `deploy/rag/`, with the layout [repository-layout.md](../../../repository-layout.md) prescribes. Nothing about behaviour changes here; this task only puts the files where they belong and keeps the build artifacts out of git.

## Goals

- `src/rag/{rag-edge,file-collector,processor,deletion-worker,chat,frontend,embedding,ocr}` and `packages/rag-common` (as `src/rag/common`, or the import path the old tree uses) hold the code.
- `deploy/rag/{.env.example,Makefile,docker-compose.yaml}` exists.
- `frontend/node_modules`, `services/*/.venv`, `services/*/.pytest_cache`, `services/*/.ruff_cache`, `services/*/src/*.egg-info` and `frontend/dist` are not tracked.
- Tests move with the service they belong to, into `<service>/tests/`.

## Non-goals

- Changing a header, an endpoint, a compose service or a dependency. That is [task-02](task-02-compose.md) and [task-03](task-03-identity.md).
- Porting the old tree's `docs/` verbatim. The facts that still hold are linked from [rag/init.md](../../../rag/init.md); the rest is rewritten in English.

## Definition of Done

- [ ] `git ls-files src/rag deploy/rag | grep -Ec 'node_modules|\.venv|\.pytest_cache|\.ruff_cache|/dist/'` is `0`.
- [ ] Every service's tests are collectable at the new path: `uv run pytest -q` in the one package that the layout keeps as an `uv` workspace, or per service if they stay separate.
- [ ] `packages/rag-common` is either moved to `src/rag/common` with its imports updated in one change, or its continued path is recorded as a mismatch in [rag/init.md](../../../rag/init.md). One of the two is true and the docs say which.
- [ ] The old repository is still present and untouched; nothing is deleted until [task-02](task-02-compose.md) and [task-03](task-03-identity.md) pass.
