# UAT 2026-06-10 — Admin GUI (operator) and user-facing experience

Verdicts:

- Admin GUI (operator): **PASS_WITH_MAJOR_UI_AND_ROUTING_DEFECTS**
- User-facing pipelines/personas: **PASS_WITH_MAJOR_USER_UX_AND_ROUTING_DEFECTS**
- Production readiness for non-engineer operators: **NOT READY**

The GUI is technically alive and useful as a diagnostic shell — every defect
below has a working backend underneath it — but it is not yet usable as a
clear operator-facing product. The fix scope is named
**`admin-gui-prod-readiness-fixpack`** (see [docs/ROADMAP.md](../ROADMAP.md)).

## Scope

Live operator UAT of the Admin GUI immediately after the successful composite
first-start, followed by user-facing UAT of pipeline launches, artifact
delivery and persona behavior. Defect IDs below are canonical — status is
tracked in [DEFECT-REGISTER-0.32.2.md](DEFECT-REGISTER-0.32.2.md).

## Environment and baseline

`00-baseline-after-composite.log` (17:43): version 0.32.2; firstboot
`applied_no_reboot`, `selection_mode=full_composite`, `composite_top_n=3`,
`applied_epoch_id=00005`, `staffing_state=degraded_selected`; 4 services
active + modelscan timer; 0 failed units; smoke `degraded` only due to S-001.
Dashboard started locally (`01-dashboard-start.log`, `02-dashboard-status.log`);
note the Admin GUI does not listen on TCP by default (observation O-003 —
by design, localhost dashboard is started explicitly by the operator).

## Verdict matrix (operator UAT)

| Aspect | Result |
|---|---|
| Technical launch | PASS |
| Dashboard / API availability | PARTIAL PASS |
| Operator usability | FAIL — major UX defects |
| Pipeline launch flow | PARTIAL PASS |
| Progress observability | FAIL |
| Model/persona behavior | FAIL — needs routing fix |
| Production readiness | NOT READY |

## Operator defects (D-series)

### D-001 — Hardware card renders raw JSON (Medium)

Memory/swap shown as raw JSON-ish values wasting the card space. Expected:
RAM/Swap bars or gauges in human units (GiB), usage percent, raw JSON only
behind a Details/Debug expander.

### D-002 — Epoch/model selection section not understandable (High)

Labels are too terse ("Current main", "Staffing", "Latest plan");
`degraded_selected · selected=1` and `0/123 tested · failed=12 · left=123`
are unexplained and internally inconsistent; "Latest plan: normal" looks
stale after a real `full_composite` run; long model names truncate without
tooltips. Expected: operator-readable labels, tooltips with the glossary
meaning (e.g. `degraded_selected` = mandatory roles staffed, some below
target thresholds), full names on hover, latest plan reflecting the actually
applied state, consistent progress numbers.

### D-003 — Admin answers wrong for known system states (High)

Asked in Russian what `degraded_selected · selected=1` means, the Admin
persona hallucinated about selecting files like `degraded_selected.txt`.
Expected: deterministic glossary answers for known dashboard states (grounded
in current firstboot state, concise, in the user's language) — never
free-form model improvisation for state labels.

### D-004 — Product metrics card not readable (Medium)

Raw JSON fragment instead of labeled rows (selected model, selection status,
score, pass rate, JSON parse rate, quality score, avg latency, failed tasks).
Expected: grouped human-readable metrics, raw JSON only in debug view.

### D-005 — Pipeline confirm OK does not transfer command to chat (High)

Clicking a pipeline card opens a browser prompt; OK closes it without putting
the generated request into the chat — operationally identical to Cancel.
Expected: OK inserts the editable request into the chat input (with visible
confirmation), Cancel only closes.

### D-006 — Pipeline diagram shown as JSON/Mermaid source (Medium)

The diagram modal shows Mermaid syntax inside JSON instead of rendering a
graph. Expected: rendered diagram, readable fallback + error if rendering
fails, raw source behind debug.

### D-007 — Pipeline execution progress invisible (High)

After launch the UI shows only a run id. Expected MVP: a textual progress
panel per run — current stage highlighted, completed stages marked, errors
with stage name + short message, waiting-for-operator states, run id linking
to artifacts/logs.

### D-008 — Iteration controls unclear and apparently inert (Medium)

Setting `steps=20` did not visibly change behavior; the "until stop" /
steps/minutes controls do not say what they apply to. Expected: controls
visibly attach to the next message/job (send button label changes, iteration
progress shown), or are disabled with a warning where unsupported.

### D-009 — Generative pipelines do not switch/greet persona (Medium)

Launching `book`/`music`-class pipelines does not clearly switch persona; the
target persona never greets or explains next steps (only `persona_evolution`
partially does). Expected: each pipeline declares a default persona; launch
shows the switch in chat; the persona greets and offers next actions.

### D-010 — Repeated pipeline launch lacks idempotency guard (Low)

`persona_evolution` launched twice produced multiple run ids with no
"start new / continue existing / cancel" prompt. Expected: short-interval
repeat launch asks, and existing runs are visible in the progress area.

## User-facing defects and requirements (U-series)

Observed UI state: Admin chat open, active persona displayed as `Video Team`,
persona switching visible in the header but with no behavioral difference and
no return-to-admin flow.

### U-001 — Generative pipelines must return artifacts into chat (High)

Pipeline launch reports a run id, but outputs never come back to the chat.
Expected: on finish, chat receives an artifact card/link (open/download/copy);
on failure, a readable error with log location. No filesystem digging for
normal use.

### U-002 — Every user command must produce a model response (Critical)

Some actions trigger state changes or run ids with no visible reply. Expected:
every message gets at least acknowledgment; async work shows accepted →
running → status → result/failure. Silent no-op is unacceptable.

### U-003 — Personas feel identical; no selector or return-to-admin (High)

Personas switch visually but answer identically; no explicit persona selector;
no way back to Admin after a task. Expected: distinct prompts/tone/scope per
persona, explicit selector, switch logged in chat, completion offers
stay/return-to-admin/switch.

### U-004 — Pipeline test/demo mode for AAT (High, feature)

One control that runs every available pipeline in safe test mode with small
built-in prompts (book outline, 4-line song concept, 10-second storyboard,
5-node knowledge graph, memory-digestion summary, …) and produces a summary
table (pipeline, case, status, artifact, error, duration, persona) exportable
as an AAT report. Failures must not stop the batch by default. This is the
target-host extension of the CI AAT suite (`AAT_SUITE.md`).

### U-005 — Artifacts exist in API/filesystem but are not surfaced (High)

Run directories exist under `/var/lib/noemaforge/pipelines/runs` and API
responses already carry artifact metadata (`path`, `open_url`, `preview_url`,
`download_url`, `open_command`) for persona_evolution, evolution, book,
release_prep, agent_life_lab, drive_calibration, memory_digestion,
dream_cycle, video_generation runs — but the chat renders no artifact cards.
The gap is UI rendering/delivery, not the backend. Evidence:
`api/04-defect-state-*.json`, `api/05-current-*.json`,
`snapshots/05–08`, `artifacts/generated-artifacts-index.md`.

## Blocking themes (rolled up)

1. Wrong/hallucinated Admin answers for known system states (D-003).
2. No readable model/epoch status (D-002).
3. No visible pipeline progress (D-007) and no artifact delivery to chat
   (U-001/U-005).
4. Confirmation dialog drops the command (D-005); commands can vanish
   silently (U-002).
5. Raw JSON where cards/diagrams are expected (D-001/D-004/D-006).
6. Personas not differentiated, no selector/return flow, no greeting
   (D-009/U-003).
7. Iteration controls unclear (D-008); repeat-launch unguarded (D-010).
8. No all-pipeline AAT/demo mode (U-004).

## Verdict

**PASS_WITH_MAJOR_UI_AND_ROUTING_DEFECTS** (operator) /
**PASS_WITH_MAJOR_USER_UX_AND_ROUTING_DEFECTS** (user-facing).
The control plane works; the presentation and routing layer must be fixed
before the GUI can face non-engineer operators. All items feed
`admin-gui-prod-readiness-fixpack` (P0/P1/P2 split in
[`noemaforge/docs/TODO.md`](../../noemaforge/docs/TODO.md)).

## Evidence

Freeze directory: `admin-gui-uat-after-composite-20260610-174328/`
(`00–02` logs, `99-admin-gui-uat-report.md`,
`notes/04-admin-gui-defects-observed.md`,
`notes/05-user-uat-requirements-and-defects.md`, `api/*`, `snapshots/*`,
`artifacts/generated-artifacts-index.md`) and
`admin-panel-uat-20260610-162643/` (endpoint discovery, `notes/actions.md`).
