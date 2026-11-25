> **ID:** US-18 task-01
> **Status:** DONE
> **Specs:** [ADR-0012](../../../../adrs/12-audio-namespace.md), [repository layout](../../../repository-layout.md), [US-18](../init.md)

## Overview

The tree moves from `../ASR-Service` into `src/audio/`. Nothing about behaviour changes here except the directory. Tests stay inside each service. The old tree stays on disk.

## Goals

- `src/audio/audio-api`, `src/audio/diarizer`, `src/audio/asr-worker` and `src/audio/frontend` hold the code.
- Tests stay at `<service>/tests/`.
- `.venv`, `node_modules`, `dist`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.vite` and `.env` are not copied.
- The old `../ASR-Service` tree is not deleted and not edited.

## Non-goals

- A new compose file. That is [task-02](task-02-compose.md).
- The identity header rename. That is [task-03](task-03-identity.md).
- Copying the old tree's `docs/` verbatim.

## Definition of Done

- [x] The four service directories exist under `src/audio/`.
- [x] A listing of the copy contains no `.venv`, `node_modules`, `dist`, `__pycache__`, `.pytest_cache`, `.ruff_cache` or `.env`. Test runs afterward created gitignored `.venv` directories under the three Python services.
- [x] `../ASR-Service` is still present.
