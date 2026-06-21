# Admin GUI — current state and fixpack

Honest status of the operator GUI. This page is maintained: update it when
fixpack PRs land or a new UAT run changes the verdicts.

## Verdict (0.33.0 fixpack — shipped 2026-06-21)

| Aspect | Result |
|---|---|
| Technical launch, dashboard/API | PASS |
| Operator usability — P0/P1 defects | **PASS** — all P0/P1 items shipped |
| Pipeline launch flow | PASS |
| Progress observability | PASS — inline progress panel (D-007) |
| Model/persona behavior | PASS — persona selector + greeting (U-003, D-009) |
| Artifact delivery into chat | PASS — artifact cards (U-001/U-005) |
| Production readiness (non-engineer operator) | **READY** (P2 polish items remain) |

The control plane underneath was always sound; 0.33.0 closes the presentation
and routing gap. Full UAT report: `docs/uat/UAT-2026-06-10-admin-gui-and-user-experience.md`;
canonical defect IDs: `docs/uat/DEFECT-REGISTER-0.32.2.md`.

## What shipped in 0.33.0

### P0 — trust and feedback loop

| ID | Feature | Where |
|---|---|---|
| D-003 | Dashboard glossary: deterministic answers for known system states (`degraded_selected`, `selected=1`, …) | `admin_gui_server.py` `_glossary_lookup()` |
| D-005 | Pipeline confirm dialog: editable chat-insert instead of browser `prompt()` | `index.html` `#pipeline-confirm`, `app.js` `_confirmPipelineId` |
| D-007 | Pipeline run progress panel: inline chat bubble with stage list, status icons, auto-polling | `app.js` `renderPipelineRunPanel()`, `GET /api/pipeline/run/<id>/status` |
| U-001/U-005 | Artifact result cards rendered inline in chat after every pipeline run | `app.js` `_artifactChatCard()`, `postArtifactsToChat()` |
| U-002 | No silent no-ops: pending spinner shown while request is in-flight; ok=false shows error card | `app.js` `_addPendingBubble()`, `sendAdmin()` wiring |

### P1 — comprehension and persona UX

| ID | Feature | Where |
|---|---|---|
| D-002 | Operator-readable epoch panel: hover tooltips, human staffing labels, non-stale plan state | `app.js` `_STAFFING_LABELS`, `_humanStaffingState()`, `renderEpoch()` |
| D-008 | Iteration controls depth notice: yellow banner + Send-button label update when budget is active | `app.js` `_updateDepthNotice()`, `style.css` `.depth-notice` |
| D-009 | Pipeline persona greeting shows codename at launch | `pipeline_catalog_api.py` `_pipeline_persona()` |
| D-010 | Repeat-launch guard: warning dialog if same pipeline relaunched within 60 s | `app.js` `_launchHistory` Map, `#pipeline-confirm-continue` |
| U-003 | Persona selector in topbar, switch logged to chat, return-to-Admin button after switch | `app.js` `_loadPersonaSelect()`, `switchPersona()`, `_addReturnToAdminLine()`; `POST /api/persona/switch` |

### P2 — presentation polish

| ID | Feature | Where |
|---|---|---|
| D-001/D-004 | Hardware gauges + product metrics: human-readable rows in metrics cards | `app.js` metrics-card rendering |
| D-006 | Pipeline diagram: SVG stage graph rendered in modal instead of raw JSON | `app.js` `showPipelineDiagram()` (DOM SVG via `createElementNS`) |

### Infrastructure bundled with 0.33.0

- Admin GUI server split into per-domain route modules (`admin_gui_routes/`)
- Frontend DOM XSS hardening: all user-content paths use `textContent`/DOM APIs
- UAT one-button runner (`noema uat run`) producing an evidence bundle

## What works (always did, unchanged)

- Localhost dashboard (`noemaforge dashboard start`, default port 8765) with
  chat-first Admin console, persona portraits, pipeline dock, telemetry and
  job panels; no TCP listener until the operator starts it.
- Session/event wiring: `/api/session/current`, `/api/events`, SSE job
  progress stream, conversation restore after refresh, mode persistence.
- Pipeline launches create run directories and artifact metadata
  (`path`, `open_url`, `preview_url`, `download_url`, `open_command`).
- Privileged actions stay plan-first (epoch apply, continue-selection and
  vault re-inventory produce audited `needs_privilege` jobs).

## Known remaining gaps (P2 / post-0.33.0)

- i18n: depth-notice and Send-button label text are English-only; pending
  a locale pass in 0.33.x.
- DOM-behavior tests: GUI tests use source-string assertions; a JS runtime
  in CI (e.g., Node + jsdom) would allow behavior-level coverage.
- ok=true without follow-up message: edge case where backend returns success
  but no follow-up model reply yet — pending UX hardening.

## Direction

The fixpack closes the "non-engineer operator" gap. Next milestones:

- **0.33.1** — full system independence (Linux / macOS / Windows parity for
  paths, service management, sockets, exec/sandbox, GUI launcher).
- **0.33.2** — hybrid LLM usage (provider resolver, redaction-before-egress,
  cost/rate ceilings).
- Desktop app shell decision: [Desktop app shell](../architecture/desktop-app-shell.md).
- Pipeline dashboard detail: [Pipeline dashboard (0.33.0)](pipeline-dashboard-0.33.0.md).
