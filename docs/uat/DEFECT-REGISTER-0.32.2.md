# Defect register — 0.32.2 target-host UAT

Canonical tracker for everything found during the 2026-06-08/10 target-host
UAT campaign. Full observed/expected/acceptance detail lives in the per-run
reports (linked); this file owns IDs, severity, status and fix targeting.

Update rule: change `Status` here when a fix merges (link the PR); never reuse
IDs. New UAT runs append new IDs.

_2026-07-25 sync: 14 of 15 fixpack items (D-001…D-010, U-001/U-002/U-003/U-005)
were already merged on `release/0.33.0-dev` (PRs #126-#136, 2026-06-20/21) but
this register was never updated to match — corrected below. U-004 (AAT
all-pipeline test/demo mode), the remaining item, is implemented same-day —
see its row below._

## Summary

| ID | Title | Severity | Area | Status | Fix target |
|---|---|---|---|---|---|
| D-001 | Hardware card renders raw JSON instead of bars/gauges | Medium | Admin GUI / dashboard | Fixed | [PR #127](https://github.com/Sinev-Maksim/NoemaForge/pull/127) |
| D-002 | Epoch/model selection section not operator-readable; stale "Latest plan" | High | Admin GUI / epoch panel | Fixed | [PR #133](https://github.com/Sinev-Maksim/NoemaForge/pull/133) |
| D-003 | Admin hallucinates on known system states (`degraded_selected`) | High | Admin routing / chat | Fixed | [PR #130](https://github.com/Sinev-Maksim/NoemaForge/pull/130) |
| D-004 | Product metrics card shows raw JSON | Medium | Admin GUI / metrics | Fixed | [PR #127](https://github.com/Sinev-Maksim/NoemaForge/pull/127) |
| D-005 | Pipeline confirm OK does not transfer command to chat | High | Admin GUI / pipeline dock | Fixed | [PR #126](https://github.com/Sinev-Maksim/NoemaForge/pull/126) |
| D-006 | Pipeline diagram rendered as JSON/Mermaid source | Medium | Admin GUI / visualization | Fixed | [PR #135](https://github.com/Sinev-Maksim/NoemaForge/pull/135) |
| D-007 | Pipeline execution progress not visible | High | Admin GUI / jobs | Fixed | [PR #131](https://github.com/Sinev-Maksim/NoemaForge/pull/131) |
| D-008 | Iteration controls unclear / no visible effect | Medium | Admin GUI / chat controls | Fixed | [PR #134](https://github.com/Sinev-Maksim/NoemaForge/pull/134) |
| D-009 | Generative pipelines don't switch/greet persona | Medium | Persona routing | Fixed | [PR #128](https://github.com/Sinev-Maksim/NoemaForge/pull/128) |
| D-010 | Repeated pipeline launch lacks idempotency guard | Low | Pipeline launch | Fixed | [PR #128](https://github.com/Sinev-Maksim/NoemaForge/pull/128) |
| U-001 | Generative pipelines must return artifacts into chat | High | Pipeline UX / artifacts | Fixed | [PR #129](https://github.com/Sinev-Maksim/NoemaForge/pull/129) |
| U-002 | Every user command must produce a visible response | Critical | Chat / routing | Fixed | [PR #132](https://github.com/Sinev-Maksim/NoemaForge/pull/132) |
| U-003 | Personas identical; no selector; no return-to-admin | High | Persona UX | Fixed | [PR #136](https://github.com/Sinev-Maksim/NoemaForge/pull/136) |
| U-004 | Pipeline test/demo mode for AAT (all pipelines, one control) | High | Acceptance testing | Fixed | [PR #327](https://github.com/Sinev-Maksim/NoemaForge/pull/327) |
| U-005 | Artifact metadata in API not surfaced as chat cards | High | Chat artifact delivery | Fixed | [PR #129](https://github.com/Sinev-Maksim/NoemaForge/pull/129) |
| S-001 | Smoke chat requires literal "OK" → healthy tiny model reported `degraded` | Medium | Ops tooling / smoke | Mitigated on host, fix upstream | 0.33.x ops |
| R-001 | `noemaforge-llm-backends-manager.service` failed once during composite window | Medium | Runtime / systemd | Open (reset-failed applied, no root cause) | 0.33.x runtime |
| O-001 | Model-selection key-scan summary JSON full of nulls | Low | UAT/ops tooling | Fixed (was a session-local ad-hoc scan, not a committed script; normalized-verdict extraction already exists — see `noemaforge/docs/TODO.md` O-001/O-002 note) | [PR #337](https://github.com/Sinev-Maksim/NoemaForge/pull/337) |
| O-002 | UAT helper quoting bugs (`●` unit query, literal `{` dir) | Low | UAT/ops tooling | Fixed (unit-name parsing bug: `noemaforge_status.py`/`bootdoctor.py` missing `--plain`; the literal-brace dir was session-local, no repo script found) | [PR #337](https://github.com/Sinev-Maksim/NoemaForge/pull/337) |
| O-003 | Admin GUI has no TCP listener by default | Info | Admin GUI / docs | By design — document operator start path | docs |

Severity scale: Critical (blocks core use) > High (blocks production
readiness) > Medium (major friction) > Low (polish) > Info.

## Sources

- D-001…D-010: [UAT-2026-06-10-admin-gui-and-user-experience.md](UAT-2026-06-10-admin-gui-and-user-experience.md)
  (raw: `admin-gui-uat-after-composite-20260610-174328/notes/04-admin-gui-defects-observed.md`).
- U-001…U-005: same report
  (raw: `notes/05-user-uat-requirements-and-defects.md`).
- S-001: [UAT-2026-06-10-gh-main-clean-install.md](UAT-2026-06-10-gh-main-clean-install.md)
  (raw: `uat-gh-main-20260610-162206/05-smoke.json`, `05-liveness-result.txt`).
- R-001, O-001, O-002: [UAT-2026-06-10-first-start-full-composite.md](UAT-2026-06-10-first-start-full-composite.md)
  (raw: `first-start-composite-uat-20260610-163249/after/07d,07g,07j`).
- O-003: [UAT-2026-06-10-admin-gui-and-user-experience.md](UAT-2026-06-10-admin-gui-and-user-experience.md)
  (raw: `admin-panel-uat-20260610-162643/notes/actions.md`).

## Acceptance criteria quick reference

The compact "done means" line per defect; full criteria in the reports.

- **D-001** — RAM/Swap bars in GiB + percent; raw JSON only under Details.
- **D-002** — operator understands model/epoch state without reading JSON;
  tooltips for every state term; latest plan matches the applied run;
  consistent progress numbers; full model names on hover.
- **D-003** — known dashboard terms get deterministic glossary answers,
  grounded in current firstboot state, concise, in the user's language.
- **D-004** — no raw JSON in default metrics view; grouped labeled rows;
  failed tasks summarized with details link.
- **D-005** — OK inserts the request into chat input + visible confirmation;
  Cancel is a no-op; optional explicit Run control.
- **D-006** — pipeline modal renders a stage graph; readable fallback on
  render failure; source behind debug.
- **D-007** — per-run progress panel: current stage highlighted, completed
  marked, errors with stage + message, run id links to artifacts/logs.
- **D-008** — iteration mode visibly attaches to the next message (button
  label + "next message runs N steps" notice + progress), or controls are
  disabled with a warning.
- **D-009** — every pipeline declares a default persona; switch is shown in
  chat; persona greets and proposes next steps.
- **D-010** — repeat launch within a short interval prompts
  new-run/continue/cancel; existing runs visible.
- **U-001** — every finished run delivers an artifact card or readable
  failure into chat; paths clickable/copyable.
- **U-002** — no silent no-ops: each message gets at least one visible
  response; async shows run id + status progression.
- **U-003** — explicit persona selector; observably different persona
  behavior; switch logged; completion offers return-to-admin.
- **U-004** — one control runs all pipelines in safe test mode with built-in
  small prompts; summary table (pipeline/case/status/artifact/error/duration/
  persona) exported as an AAT report; failures don't stop the batch.
- **U-005** — chat renders the artifact metadata the API already returns
  (open/preview/download/open_command) as result cards.
- **S-001** — shipped smoke treats health-ok + non-empty reply as live;
  literal-OK stays as an optional strict mode; no `degraded` verdict for a
  responding model.
- **R-001** — root cause for the backends-manager failure identified; unit
  hardened or failure path made non-occurring; regression check added.
- **O-001** — key-scan summary extracts real values or is dropped in favor of
  the normalized-verdict extraction.
- **O-002** — UAT helper scripts quote unit names/paths correctly; no stray
  literal-brace directories.
- **O-003** — operator docs state the default no-TCP posture and the explicit
  localhost dashboard start command.
