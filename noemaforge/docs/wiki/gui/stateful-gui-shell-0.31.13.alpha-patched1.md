# NoemaForge 0.32.1 — Stateful GUI Shell

> **Status: historical snapshot (0.31.13.alpha-patched1 era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

## Purpose
The alpha GUI shell persists chat history, restores state after refresh, shows persona portraits, tasks, jobs, pipeline catalog, telemetry, epoch state, and SR/SSR-ready backend message records.

## Inputs
- `/api/gui/state`
- `/api/conversation/*`
- `/api/tasks`
- `/api/jobs`
- `/api/pipelines/catalog`
- `/api/telemetry/status`

## Outputs
- Local browser UI.
- Persistent conversation records under `/var/lib/noemaforge/gui/`.
- SR/SSR inbox entries under `/var/lib/noemaforge/review/`.

## Safety
No hidden privileged action is run from page load. Epoch switch, Vault re-inventory and model-selection continuation are plan/job-first.

## Tests
- Reload GUI and confirm chat history persists.
- Check persona portrait loads from `/ui/personas/...`.
- Check right-click pipeline menu shows diagram/stats.
