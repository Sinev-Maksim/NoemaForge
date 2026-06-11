# Admin GUI — current state and fixpack

Honest status of the operator GUI after the 2026-06-10 live UAT on the
production target host. This page is maintained: update it when fixpack PRs
land or a new UAT run changes the verdicts.

## Verdict (2026-06-10 UAT)

| Aspect | Result |
|---|---|
| Technical launch, dashboard/API | PASS / PARTIAL PASS |
| Operator usability | FAIL — major UX defects |
| Pipeline launch flow | PARTIAL PASS |
| Progress observability | FAIL |
| Model/persona behavior | FAIL — needs routing fix |
| Production readiness (non-engineer operator) | **NOT READY** |

The control plane underneath is sound — every defect has a working backend
under it (the API already returns artifact metadata, jobs run, state
persists). The gap is presentation and routing. Full reports:
`docs/uat/UAT-2026-06-10-admin-gui-and-user-experience.md`; canonical defect
IDs: `docs/uat/DEFECT-REGISTER-0.32.2.md` (project root).

## What works today

- Localhost dashboard (`noemaforge dashboard start`, default port 8765) with
  chat-first Admin console, persona portraits, pipeline dock, telemetry and
  job panels; no TCP listener until the operator starts it.
- Session/event wiring: `/api/session/current`, `/api/events`, SSE job
  progress stream, conversation restore after refresh, mode persistence.
- Pipeline launches create run directories and artifact metadata
  (`path`, `open_url`, `preview_url`, `download_url`, `open_command`).
- Privileged actions stay plan-first (epoch apply, continue-selection and
  vault re-inventory produce audited `needs_privilege` jobs).

## What blocks production (fixpack P0)

- **D-003** Admin hallucinates on known system states
  (`degraded_selected · selected=1` must get a deterministic glossary answer).
- **D-005** Pipeline confirm OK does not transfer the command into chat.
- **D-007** No visible per-run pipeline progress.
- **U-001/U-005** Artifacts never come back into chat as cards, although the
  API metadata exists.
- **U-002** Some commands produce no visible response at all (silent no-op).

P1 follows with comprehension and persona UX (readable epoch panel D-002,
distinct personas + selector + return-to-admin U-003, pipeline persona
greeting D-009, iteration controls D-008); P2 is presentation polish
(hardware gauges D-001, metrics card D-004, rendered diagrams D-006,
repeat-launch guard D-010).

## Direction

- The fixpack is the first slice of the "hardening for non-engineer
  operators" track — done means: install, start, run a pipeline and receive
  the result entirely through the GUI, no JSON reading, no filesystem digging.
- The server side (`noemaforge/src/admin_gui_server.py`, ~2.2k lines, ~119
  endpoint references) gets split into route modules before it grows further;
  the frontend (`noemaforge/templates/pipeline-dashboard/app.js`) gains a
  small card/progress component set.
- The GUI becomes a windowed app via the lightweight shell decision:
  [Desktop app shell](../architecture/desktop-app-shell.md).
