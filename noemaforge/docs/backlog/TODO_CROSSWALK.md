# TODO crosswalk

This crosswalk maps old TODO locations and mixed historical fragments to the normalized 0.32.1 TODO system.

## Path Crosswalk

| Old or requested location | New canonical location | Status | Notes |
|---|---|---|---|
| `noemaforge/TODO.md` | `noemaforge/docs/TODO.md` | migrated | Not recreated as active Markdown because package-root Markdown violates the strict docs placement policy. |
| `docs/TODO.md` | `noemaforge/docs/TODO.md` | migrated | Not recreated as root docs Markdown because active Markdown must stay under approved docs zones. |
| `noemaforge/docs/TODO.md` | `noemaforge/docs/TODO.md` | current | Short active TODO mirror. |
| `noemaforge/docs/backlog/ROADMAP_AND_TODO.md` historical fragments | `noemaforge/docs/backlog/HISTORICAL_TODO_ARCHIVE.md` | migrated | Preserved for lookup without mixing historical work into the active roadmap. |
| `noemaforge/docs/backlog/ROADMAP_AND_TODO.md` active gates | `noemaforge/docs/backlog/CURRENT_0.32.1_TODO.md` | migrated | Detailed active gates and evidence requirements. |
| TODO status audit | `noemaforge/docs/quality/TODO_STATUS_RECONCILIATION_0.32.1.md` | current | Machine-readable reconciliation plus human notes. |

## Status Crosswalk

| Legacy marker | New status | Meaning |
|---|---|---|
| unchecked task requiring target evidence | `target-open` | Requires target-machine evidence before completion. |
| unchecked task blocked by local or target precondition | `blocked` | Cannot proceed until named blocker is resolved. |
| checked contract-only task | `done-contract` | Contract/schema/docs/tests exist and local structure gates pass. |
| checked runtime behavior task | `done-runtime` | Runtime implementation exists and runtime tests pass. |
| future backlog item | `roadmap` | Planned work, not a P0 active gate. |
| stale duplicate or historical fragment | `migrated` or `obsolete` | Retained only in the historical archive or replaced by a current gate. |

## Active Gate Mapping

| Current gate family | Canonical active file | Historical source |
|---|---|---|
| Boot/display/storage safety | `CURRENT_0.32.1_TODO.md` | Target-machine validation fragments from previous roadmap/TODO files. |
| Admin chat/routing | `CURRENT_0.32.1_TODO.md` | Admin GUI and smalltalk routing follow-ups. |
| Stateful GUI jobs | `CURRENT_0.32.1_TODO.md` | Dashboard launcher, job progress and first-start continuity follow-ups. |
| Runtime service safety | `CURRENT_0.32.1_TODO.md` | Gateway, ToolProxy and backend smoke follow-ups. |
| Telemetry/product metrics | `CURRENT_0.32.1_TODO.md` | Product evidence and telemetry backlog. |
| Grounded Admin/docs RAG | `CURRENT_0.32.1_TODO.md` | Docs RAG, grounded Admin and knowledge gap follow-ups. |
| Documentation hygiene | `CURRENT_0.32.1_TODO.md` | Strict Markdown and status-label cleanup work. |

