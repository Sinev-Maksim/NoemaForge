# CHANGELOG — NoemaForge

Single root changelog with changes grouped by version. Version-specific CHANGELOG files were merged here to avoid duplicate release-history documents.

Consolidated on 2026-05-14 from: CHANGELOG.md, CHANGELOG_0.31.13.alpha.md, CHANGELOG_0.31.12.md, CHANGELOG_0.31.11.md, CHANGELOG_0.31.10.md, CHANGELOG_0.31.09.md, CHANGELOG_0.31.08.md, CHANGELOG_0.31.07.md, CHANGELOG_0.31.06.md, CHANGELOG_0.31.05.md, CHANGELOG_0.31.04.md, CHANGELOG_0.31.03.md, CHANGELOG_0.31.02.md, CHANGELOG_0.31.01.md, CHANGELOG_0.31.0.md, CHANGELOG_0.30.22.md, CHANGELOG_0.30.21.md, CHANGELOG_0.30.20.md, CHANGELOG_0.30.19.md, CHANGELOG_0.30.09.md, CHANGELOG_0.30.05.md, CHANGELOG_0.30.0.md, CHANGELOG_0.29.20.md, CHANGELOG_0.29.19.md, CHANGELOG_0.29.18.md, CHANGELOG_0.29.17.md, CHANGELOG_0.29.16.md, CHANGELOG_0.29.15.md, CHANGELOG_0.29.14.md, CHANGELOG_0.29.13.md.

## Current active summary (CHANGELOG.md)
### 0.31.13.alpha first-start watchdog patch

`0.31.13.alpha` includes `NFG-FIX-0.31.13-firststart-watchdog`, based on the BigBro-BOS hang diagnostic bundle. It adds per-model and total watchdogs, streaming tournament progress artifacts, backend cleanup, fresh firstboot status writes, and a default safety-name filter for unverified/uncensored/aggressive models.

Recommended bounded candidate review:

```bash
sudo noemaforge first-start --normal --dry-run --show-candidates --per-model-timeout 180 --total-timeout 1200
```

Progress while running:

```bash
sudo jq . /var/lib/noemaforge/bootstrap/role-tournament-progress.json
sudo tail -n 50 /var/lib/noemaforge/bootstrap/role-tournament-progress.jsonl
sudo jq . /var/lib/noemaforge/bootstrap/model-run-records.json
```



- Added `NFG-ARCH-0.31.13-kernel-shell-exchange` as a future architecture roadmap package.
- Added consolidated MVP kernel / NoemaShell Lite / RoleFlow / git_exchange Wiki page: `docs/wiki/architecture/consolidated-mvp-kernel-roadmap-0.31.13.alpha.md`.
- Recorded Evolve boundaries: Evolver/Darwin mutates only in lab; Scary gates; Surgeon validates; Admin approves.
- Preserved runtime behavior: documentation/backlog only, no new hard dependencies.

### NoemaForge 0.31.13.alpha changelog

### Docs / roadmap

- Added `NFG-PROP-0.31.13-edge-ml-pack` as a future-version backlog package.
- Added Edge/TinyML/OTA Wiki page: `docs/wiki/edge/edge-tinyml-ota-roadmap-0.31.13.alpha.md`.
- Added package summary: `docs/EDGE_TINYML_OTA_BACKLOG_0.31.13.alpha.md`.
- Updated `docs/ROADMAP.md`, top-level `TODO.md`, `docs/TODO.md`, `noemaforge/TODO.md`, `docs/wiki/README.md`, and `context.md`.
- Kept Edge/TinyML/OTA explicitly experimental and non-blocking for public first-start.

### Runtime

- No runtime hard dependencies added.
- No first-start, Admin GUI, Dev Team, model-selection, or locale gate behavior changed beyond version metadata.


### 0.31.13.alpha

- Added MultiOS runtime host roadmap (`NFG-PROP-0.31.13-multiOS-runtime-pack`) as alpha-prep backlog/wiki content.
- Added Sense/Privacy/Honesty/Critics/Pipeline-RFC roadmap (`NFG-PROP-0.31.13-sense-quality-governance-pack`) as alpha-prep backlog/wiki content.
- Preserved original uploaded source reports in `docs/source_reports/`.
- Updated localized user docs to mention the new backlog tracks without adding runtime hard dependencies.

### 0.31.13.alpha

- Completed the NoemaForge global restart across package paths, commands, docs, policies, environment variables and install/runbook commands.
- Added model health registry, global runtime-failure exclusion, candidate-map filtering and score invalidation for models that fail after partial scoring.
- Added real-run confirmation gate for `--include-unverified`.
- Added effective first-start options artifact.
- Shipped `noemaforge_validation_logger.sh` inside the archive root.

### 0.31.13.alpha — NoemaForge rename + first-start health gate

- Completed the hard NoemaForge rename/restart across the release surface.
- Added failed-model health registry, failure exclusion and candidate invalidation for first-start tournaments.
- Added systemd-rehome first-start option preservation and effective options artifact.
- Added explicit confirmation requirement for real `--include-unverified` first-start.
- Added NoemaForge governance / quality / sensing research pack from deep research report 8 as roadmap/wiki/source-report material.


### 0.31.13.alpha — typed governance research inclusion

- Added `NFG-ARCH-0.31.13-typed-governance-sense-critics-rfc` as alpha-prep roadmap/wiki/source-report content.
- Preserved runtime impact as `none`; no new OpenTelemetry, OPA, C2PA, watermarking, detector, Internet or eval dependencies are enabled.

### NoemaForge 0.31.13.alpha live-fix context

Patched7 incorporates the BigBro-BOS runtime-selection findings: core systemd units are installed by setup, setup markers are created, legacy share migration is handled, NoemaForge runtime sockets are canonical, `gui_rescue` aliases are action aliases, and first-start keeps partial valid model scores instead of invalidating them after per-model budget exhaustion. Runtime infrastructure failures are reported separately from model quality failures.

### NoemaForge 0.31.13.alpha patched10 update
- Fixed runtime-safety false positive: free-form eval answers mentioning non-head GGUF shards are warning-only; structured runtime paths remain blocking.
- Added canonical path helper for legacy `/mnt/brainos-share` -> `/mnt/noemaforge-share`.
- Added full-composite real launch runbook for `sudo noemaforge first-start --full_composite 0`.

### 0.31.13.alpha

- Added first-start TTY/console status monitor with timestamps, stage/model/role/task progress and abort hint.
- Added `noemaforge first-start abort` recovery command.
- Added direct TTY Ctrl+C trap for first-start: stop tournament/backends and restore Debian GUI.
- First-start now requests GUI restoration on completion, error, or interrupt.
- Installer writes NoemaForge share bind mounts with `nofail,x-systemd.automount` to avoid boot-blocking emergency mode.

### 0.31.13.alpha

- Added Admin GUI epoch visualization and model-selection progress panel.
- Added GUI buttons for epoch apply request, continue model selection, Vault re-inventory and workflow stop marker.
- Added bounded improvement depth controls: step count, time budget and until-stop mode.
- Added usecase help cards and help responses for model selection, model evolution, Dev Team and bounded improvement.
- Fixed model-selection dialog state: replying `normal` after a pending mode prompt now creates artifacts instead of asking again.
- Fixed Admin GUI input clearing after send.
- Added grouped/color `noemaforge first-start summary` command.
- Reduced version-audit noise for known large runtime binaries while preserving active backup warnings.


### NoemaForge 0.31.13.alpha alpha

This alpha promotes the stateful GUI shell: persistent Admin conversation history, persona portraits with deterministic fallback avatars, SR/SSR review inbox records, telemetry panels, task governance, inactivity timer, full pipeline dock, epoch/model-selection controls, CPU/GPU device policy staging, and local-first SmartHome backlog architecture.

Important runtime policy: CPU/GPU switching is staged. The selected device policy applies on the next persona/model switch or backend restart; it does not migrate an active model.

Privileged operations such as Vault re-inventory, model-selection continuation and epoch apply are plan/job-first from the GUI. They require explicit operator approval or a terminal sudo command.

## 0.31.13.alpha
- Added stateful GUI conversation history and SR/SSR review records.
- Fixed persona portrait root cause by serving `/ui/...` assets and adding HEAD support.
- Added deterministic per-person fallback SVG avatars.
- Added telemetry surfaces: hardware, runtime and product metrics.
- Added staged CPU/GPU runtime device policy.
- Added task queue/admin surfaces and inactivity policy display.
- Added full pipeline dock with right-click diagram/stats and draft-only new pipeline path.
- Added model-selection continuation job plan and Vault re-inventory privileged fallback plan.
- Added SmartHome local-first privacy backlog pack.

## 0.31.12
### Added

- Admin route/message/pipelines/modify-pipeline control-plane CLI.
- Admin GUI server/API for browser-local operation from greeting to routed action to shutdown.
- Dev Team runtime for dev pipeline launch plus direct `replace`, `write-file` and `set-version` operations under explicit `--apply`.
- Model Evolution runtime with baseline snapshot, mutation plan, scorecard, rollback plan and candidate profile.
- Routeable pipeline/team catalog entries for code, voice, music, photo, video, masks, image analysis, model evolution and release prep.
- Admin GUI endpoints for Admin messages, routed pipeline launch, pipeline overlay modification, Dev Team helpers, model-evolution runs, state inspection and shutdown.
- Regression coverage for Admin routing, media pipeline dispatch, pipeline overlay edits, Dev Team direct edits, model-evolution artifacts and multimodal GGUF shard filtering.

### Changed

- Dashboard is now an Admin GUI control plane rather than a static-only pipeline page.
- `noemaforge gui console start` and `noemaforge gui admin start` start only the local Admin GUI/API; they do not start LLM/media/camera backends.
- Dashboard serving no longer requires writing generated state into the packaged UI directory; it uses `/api/state` plus an operator-writable cache.
- Greeting typo `Првиет!` is explicitly recognized as a GUI/Admin warm-up route.
- Admin code requests now produce both a pipeline run and a Dev Team runtime action.
- Admin model-evolution requests are priority-routed to `model_evolution` even when the text also mentions code review.
- Multimodal Vault scan is shard-aware: non-head split GGUF files are excluded from runtime candidates and reported under `excluded_non_head_shards`.
- Setup/install selftests are kept lightweight and non-hanging; full release evidence is captured through version audit, consistency audit, direct CLI/API smokes and syntax gates.
- Active release metadata/runtime/config versions are aligned to `0.31.12`; historical changelogs remain historical.

### Safety

- No implicit LLM or media backend startup from GUI.
- No silent camera/microphone capture.
- No direct code writes without `--apply`.
- No silent production model mutation; model evolution is measured, artifact-based and rollback-gated.
- Live media generation/training adapters remain explicit/manual until selected for `0.31.13+`.

### Final RC polish

- Added `noemaforge admin modify-pipeline` for reviewed pipeline overlay edits.
- Added GUI affordances/endpoints for routed Admin actions, pipeline actions, direct Dev Team edits and model-evolution runs.
- Added `/api/admin/ask`, `/api/admin/start` and `/api/admin/modify-pipeline` aliases/endpoints around the Admin GUI control plane.
- Fixed final Admin GUI API JSON handling for `dev-team set-version`.
- Verified local GUI lifecycle through dashboard wrapper and direct server: health → `Првиет!` → routed code/dev-team action → shutdown.

## 0.31.11
### Added

- `noemaforge first-run`: one-command first-start audit with internal run directory management.
- `noemaforge version-audit`: release metadata consistency check.
- `noemaforge av-readiness`: read-only audio/video readiness report.
- First-run summary modes: `--summary`, `--failed`, `--full`, `--json`.

### Fixed

- firstboot GGUF discovery now reuses canonical model normalization and rejects non-head split shards before scoring/runtime selection.
- Added missing current-version README target docs for live reboot and user test-case handoff.
- Manual `$RUN` variable is no longer required for first-run logging.
- Prevented `tee "$RUN/..."` from accidentally writing into `/...` when `$RUN` is empty.
- Propagated release version to active runtime constants and top-level JSON catalog version fields.
- Added version consistency checks to package selftest.

### Known limitations

- Audio/video production pipeline is not complete; current release reports this as a warning/readiness finding.
- Historical version strings may remain in fixture descriptions and archived changelogs; `version-audit --strict-all` can enumerate them.

---

### CHANGELOG 0.31.01

### Added

- General NoemaForge pipeline member-cell runtime: `noemaforge member ...`.
- Pipeline-integrated member execution: `noemaforge pipeline member run <run_id> ...`.
- Standalone-or-ensemble member policy for architect, developer, code-analyser/visualiser, QA, tester, integration tester, optimizer, reviewer and archivist.
- Proposal logs, consensus artifacts, unique artifacts and typed next-participant handoff for every member-cell run.
- Artifact consistency gate for outgoing member handoffs.
- Developer auto-test evidence requirement.
- QA misunderstanding-loop detection to avoid endless Dev↔QA loops.
- Code-analyser/visualiser member with Mermaid architecture overview, call graph, bottleneck report, helicopter view and repeated-call highlights.
- First-start UI validation pipeline and operator test case for GUI and woGUI modes.

### Changed

- Updated pipeline catalog to include `dev_pipeline_member_cells` and `first_start_ui_validation`.
- Updated public smoke/testbench to include member-cell checks.
- Updated README/TODO/wiki/research digests to version `0.31.01`.

### Preserved

- Switchable LLM invariant: `max_active_llms=1`.
- No uncontrolled heavy LLM boot autostart.
- GUI mode starts NoemaForge safe-start after GUI; woGUI mode starts safe-start instead of GUI.

## 0.31.10
### NoemaForge 0.31.10 — Multimodal Vault + Persona GUI Preparation

This release moves NoemaForge beyond a GGUF-only text model assumption by adding a
read-only multimodal discovery and planning layer.

### Added

- `noemaforge multimodal scan --json` discovers GGUF and non-GGUF model assets in
  the Vault: safetensors, ckpt, onnx, pt/pth, bin, ggml, tflite and media files.
- `noemaforge multimodal status --json` reports backend prerequisites and discovered
  capabilities.
- `noemaforge multimodal image-metadata IMAGE --json` extracts image/media metadata
  using ffprobe/exiftool/ImageMagick where available.
- `noemaforge multimodal prepare voice_generate|music_generate|photo_generate|video_generate|video_call_masks`
  writes explicit non-autostart pipeline plans under `/var/lib/noemaforge/multimodal`.
- `noemaforge multimodal mask-plan --json` prepares video-call mask/virtual-camera
  requirements without hijacking any camera.
- `noemaforge persona gui-status --json` validates persona portraits and dashboard
  readiness.
- `noemaforge first-run` now includes multimodal scan/status and persona GUI checks.

### Policy

- Non-text media backends are manual or pipeline-explicit only.
- GUI `runtime_only` still starts runtime/ToolProxy only and does not start LLM.
- Heavy LLM and heavy media generation are manual-only.
- Camera/microphone/video-call mask features require explicit operator command.

### Status

This is prelaunch-ready scaffolding: model discovery, metadata extraction,
operator plans, policy enforcement and GUI portrait checks are present. Live
photo/video/music generation still requires installing the chosen backend adapter
and matching model family.

## 0.31.09
### Added

- `noemaforge first-run`: one-command first-start audit with internal run directory management.
- `noemaforge version-audit`: release metadata consistency check.
- `noemaforge av-readiness`: read-only audio/video readiness report.
- First-run summary modes: `--summary`, `--failed`, `--full`, `--json`.

### Fixed

- Manual `$RUN` variable is no longer required for first-run logging.
- Prevented `tee "$RUN/..."` from accidentally writing into `/...` when `$RUN` is empty.
- Propagated release version to active runtime constants and top-level JSON catalog version fields.
- Added version consistency checks to package selftest.

### Known limitations

- Audio/video production pipeline is not complete; current release reports this as a warning/readiness finding.
- Historical version strings may remain in fixture descriptions and archived changelogs; `version-audit --strict-all` can enumerate them.

## 0.31.08
### Fixed

- Added package-level recursion audit for setup/installer/wrapper/systemd call graphs.
- Prevented installer from installing legacy `helpers/noemaforge` as public `noemaforge` command.
- Hardened canonical `NOEMAFORGE_SELF` resolution for systemd-run paths.
- Removed strict NVIDIA/GDM `ExecStartPre` readiness checks from GUI timer drop-in to avoid failed units when GUI is late.
- Added audit checks that GUI autostart service remains static/timer-triggered, not directly wanted by graphical.target.

### Preserved

- Full installer loop fix from 0.31.06.
- Native `gui_start`/`gui-start` command integration from 0.31.07.
- GUI mode default profile `runtime_only`.
- Heavy LLM manual-only invariant.
- ToolProxy SEL preflight and current-day SEL repair.

## 0.31.07
- Added `noemaforge/tools/prep/noemaforge-gui-start.sh`.
- Added native CLI aliases:
  - `noemaforge gui_start`
  - `noemaforge gui-start`
  - `noemaforge gui start`
- Kept `noemaforge gui-rescue` as recovery-only path.
- Removed need for external `noemaforge` wrapper interception.
- Added non-hanging CLI surface selftests to `setup.sh` and installer.
- Installer now deploys standalone `gui-start` / `gui_start` helper aliases.
- Full installer remains non-recursive and delegates to real installer only.

## 0.31.06
- Fixed full-package installer recursion: `setup.sh` no longer loops through `install_noemaforge_0.31.05_mvp.sh`.
- Added real `install_noemaforge_0.31.06_mvp.sh` installer based on the last working full installer flow.
- Made VM mode non-destructive by default; use `--apply-vm` only for intentional VM install.
- Preserved 0.31.05 GUI timer autostart policy: GUI direct service disabled, GUI timer enabled when boot-mode is `gui`.
- Updated full-install verification expectations for `noemaforge version = 0.31.06`.


Additional hardening: added setup recursion guard and selftest check that the installer does not call setup.sh.

## 0.31.05
- Switched GUI autostart from direct `graphical.target` service enablement to delayed timer-driven startup.
- Added `noemaforge-autostart-gui.timer`.
- Updated `noemaforge boot-mode set gui --apply-systemd` to enable the GUI timer and keep the direct service disabled.
- Made GUI readiness skip diagnostic/non-fatal by default, while preserving strict mode via `--strict-gui-wait`.
- Improved `noemaforge boot-mode status` labels to show `gui timer`, `gui service`, and `wogui`.
- Added runtime autostart attempt status under `/var/lib/noemaforge/runtime/autostart-gui-last.json`.

## 0.31.04
### Live reboot stabilization

- Fixed `noemaforge version` to read `/opt/noemaforge/VERSION` first, avoiding stale `0.31.01` fallback.
- Promoted BigBro-BOS live fixes into package code:
  - BootDoctor `td` NameError fix.
  - ToolProxy root preflight via `PermissionsStartOnly=true`.
  - current-day SEL segment repair without recursive mutation of sealed historical logs.
  - GUI helper help surfaces that do not start rescue jobs.
  - `/opt/helpers`, `/opt/systemd`, and `/var/lib/noemaforge/*` installer creation.
- Strengthened GUI runtime policy:
  - GUI mode defaults to `runtime_only`.
  - `runtime_only` enforces no active main backend unless `--preserve-existing-llm` is explicit.
  - woGUI defaults to `bootstrap_cpu_llm`.
  - heavy LLM remains manual-only.
- Added `noemaforge gui-diagnose [--json]` for Secure Boot / MOK / NVIDIA / GDM / ToolProxy diagnostics.
- Added background dashboard commands: `noemaforge dashboard start|stop|status`.
- Added 0.31.04 user test case and live reboot runbook.

## 0.31.03
### Changed
- Split GUI/woGUI autostart from LLM backend policy.
- GUI mode now defaults to `runtime_only`: gateway/runtime/ToolProxy allowed, no automatic LLM backend.
- GUI mode can opt into CPU bootstrap LLM via `sudo noemaforge boot-mode set-profile gui bootstrap_cpu_llm`.
- woGUI mode defaults to `bootstrap_cpu_llm`.
- Heavy LLM autostart is manual-only in all boot modes.
- `safe-start` now accepts `--llm-profile=runtime_only|bootstrap_cpu_llm|heavy_manual`.
- `boot-mode status` is human-readable and shows unit labels plus autostart profiles.
- `small_improvement_packs` are explicitly optional and approval-gated.

### Fixed / promoted from live testing
- BootDoctor report write path fixed.
- ToolProxy root preflight and SEL current-day segment permission repair included.
- GUI helper help behavior fixed so help never launches rescue jobs.
- Installer creates `/opt/helpers`, `/opt/systemd`, and NoemaForge state directories with correct permissions.
- GUI autostart is gated by boot mode, NVIDIA DRM modeset, and `nvidia-smi` readiness.

### Policy
```text
gui mode:
  NoemaForge UI/dashboard/runtime start allowed
  ToolProxy allowed
  CPU bootstrap LLM optional
  heavy LLM disabled -> manual

wogui mode:
  CPU bootstrap LLM allowed
  heavy LLM only explicit/manual
```

## 0.31.02
Incremental fixes discovered during BigBro-BOS live validation:

- fix BootDoctor `td` NameError in report writer;
- fix `noemaforge-sel-fix` `noemaforge_group` command bug;
- repair current-day SEL segment permissions without recursively mutating sealed historical logs;
- ensure ToolProxy SEL preflight runs as root via `PermissionsStartOnly=true`;
- install `/opt/helpers` and `/opt/systemd` compatibility paths;
- handle `gui-rescue --help` before sudo/systemd handoff;
- add NVIDIA/GDM readiness gate and delay for GUI autostart;
- improve human-readable `noemaforge boot-mode show/status`;
- create `/var/lib/noemaforge/*` runtime directories with correct permissions.

## 0.31.01
### Added

- General NoemaForge pipeline member-cell runtime: `noemaforge member ...`.
- Pipeline-integrated member execution: `noemaforge pipeline member run <run_id> ...`.
- Standalone-or-ensemble member policy for architect, developer, code-analyser/visualiser, QA, tester, integration tester, optimizer, reviewer and archivist.
- Proposal logs, consensus artifacts, unique artifacts and typed next-participant handoff for every member-cell run.
- Artifact consistency gate for outgoing member handoffs.
- Developer auto-test evidence requirement.
- QA misunderstanding-loop detection to avoid endless Dev↔QA loops.
- Code-analyser/visualiser member with Mermaid architecture overview, call graph, bottleneck report, helicopter view and repeated-call highlights.
- First-start UI validation pipeline and operator test case for GUI and woGUI modes.

### Changed

- Updated pipeline catalog to include `dev_pipeline_member_cells` and `first_start_ui_validation`.
- Updated public smoke/testbench to include member-cell checks.
- Updated README/TODO/wiki/research digests to version `0.31.01`.

### Preserved

- Switchable LLM invariant: `max_active_llms=1`.
- No uncontrolled heavy LLM boot autostart.
- GUI mode starts NoemaForge safe-start after GUI; woGUI mode starts safe-start instead of GUI.

## 0.31.0
### Added

- `noemaforge qa code team|run|list|show` for code-development QA sub-team orchestration.
- `code_qa_team` and `operator_recovery_team` pipeline teams.
- `code_dev_qa_subteam` and `gui_recovery_compatibility` pipelines.
- `code-qa-team.json` model capability/diversity policy.
- GUI recovery TTY fallback docs and user acceptance test case.
- Compatibility wrappers for `gui-rescue` and `gui-status` that can operate even when the full CLI delegate is absent.
- Help surface cleanup: `noemaforge -h`, `noemaforge --help`, `noemaforge help`, `noemaforge ?` show command guidance; `guide` keeps method-oriented help.

### Changed

- Installer now installs GUI wrappers into both sbin and bin paths for TTY/sudo path compatibility.
- MVP smoke includes code QA sub-team checks.
- Selftest catalog includes code QA and GUI wrapper help cases.
- Wiki/TODO/README updated to current version 0.31.0.

### Invariant retained

- Switchable LLM runtime.
- Maximum one active LLM.
- No uncontrolled heavy LLM autostart.

## 0.30.22
### Added

- `noemaforge/src/selftest_runtime.py` for self-test execution, resource telemetry, baseline comparison and wiki patch generation.
- `noemaforge selftest catalog|run|compare|metrics|wiki-patch`.
- `noemaforge wiki-patch create` alias.
- `noemaforge/configs/selftest-case-catalog.json` with core, pipeline, module-compile and safe suites.
- `noemaforge/configs/module-test-matrix.json` with baseline compile coverage for every Python module under `noemaforge/src`.
- `noemaforge/configs/selftest-telemetry-policy.json` with regression thresholds.
- `selftest_registry.sqlite` schema for test runs, case results, metric samples, regressions and wiki patches.
- New pipelines: `self_improvement_test_matrix`, `resource_regression_guard`, `wiki_incremental_patch_publish`, `module_test_case_factory`, `memory_leak_probe`.
- New wiki/research docs for self-improvement telemetry and incremental wiki patches.

### Changed

- `pipeline validate` and `schema validate` now include self-test catalog checks.
- `mvp-smoke` now verifies self-test telemetry and wiki patch generation offline.
- Pattern catalog now includes NoemaForge self-test telemetry / wiki patch patterns.

### Preserved

- Switchable LLM invariant: max one active LLM.
- Heavy LLM live checks remain explicit; no default LLM autostart is added by self-tests.

## 0.30.21
### P1 runtime-core stabilization

- Added P1 SQLite runtime tables: `stage_states`, `task_contexts`, `approvals`, `llm_leases`.
- Registered typed context sidecars in SQLite when pipeline runs are created.
- Added `noemaforge schema validate` / `noemaforge pipeline schema-validate`.
- Added `noemaforge pipeline event-log` for runtime event inspection.
- Added `noemaforge pipeline lease acquire|status|release|preempt` for single-active-LLM scheduling ownership.
- Added `noemaforge pipeline metrics --format prometheus` while keeping JSON metrics.
- Added `noemaforge pipeline executor-step` as a minimal NoemaForge-native DAG/event stepper.
- Enhanced `context-lint` to validate typed context sidecars and their checksums.
- Expanded MVP smoke from 24 checks in 0.30.20 to 31 checks in 0.30.21.
- Added P1 contracts:
  - `noemaforge/contracts/pipeline_context_packet.schema.json`
  - `noemaforge/contracts/pipeline_runtime_p1_state.schema.json`
  - `noemaforge/contracts/llm_lease.schema.json`
- Added targeted P1 tests: `noemaforge/tests/test_pipeline_p1_03021.py`.

### Runtime invariant

The invariant remains unchanged:

```text
mode=switchable
max_active_llms=1
heavy_llm_autostart=conditional_safe_start_only
```

No parallel heavy model runtime was enabled.

## 0.30.20
P0 stabilization release over 0.30.19.

### Added

- Conditional safe autostart boot modes:
  - `manual`: no runtime autostart;
  - `gui`: gated `safe-start` after display manager / GUI;
  - `wogui`: gated `safe-start` under `multi-user.target` instead of GUI.
- `noemaforge boot-mode show|set|install-units|status`.
- `noemaforge autostart-safe --mode gui|wogui|auto`.
- `degraded_readonly` guard for mutating pipeline commands.
- JSON sidecars and SHA256 files for pipeline context packets.
- BigBro-BOS live validation playbook.

### Fixed

- Removed the dead `if False else` placeholder branch in `pipeline_runtime.py` snapshot artifact collection.
- Updated release metadata/checksum generation for the new version.
- README/version cleanup for 0.30.20.

### Preserved

- Switchable LLM invariant: `max_active_llms=1`.
- Backend manager/modelscan timers remain disabled by default.
- Safe-start remains the only runtime-start path for boot-mode autostart.

## 0.30.19
- Added local reviewed pipeline catalog overlay: `configs/pipelines.local.json`.
- Added pipeline commands: `context-lint`, `compact`, `queue`, `metrics`, `template-append`, `policy`.
- Added dashboard launcher: `noemaforge dashboard path|state|serve`.
- Added `noemaforge persona doctor`.
- Added 10 runnable public/MWP pipeline definitions.
- Added 2 low-hanging fruit collections.
- Expanded MVP smoke from 15 checks to 21 checks.
- Added targeted pytest coverage for the new 0.30.19 surfaces.
- Added 0.30.19 install/uninstall wrappers.
- Preserved switchable-LLM invariant: one active backend maximum, no heavy autostart.

## 0.30.09
### Added

- `noemaforge pipeline readiness --json`
- `noemaforge pipeline gate <run_id> [--strict]`
- `noemaforge pipeline repair <run_id|--all> [--dry-run]`
- `noemaforge pipeline template-import <path> [--family n8n|github_actions|airflow|temporal]`
- `noemaforge persona lineage [persona] --json`
- `noemaforge persona export --out <path>`
- 0.30.09 installer/uninstaller wrappers.
- 0.30.09 pytest coverage for pipeline/persona low-hanging fruit.

### Changed

- Runtime socket counting now reports the real number of backend sockets, allowing doctor/readiness to detect multiple active LLMs.
- Dashboard state includes richer runtime snapshot and release readiness score.
- Persona evolution updates active persona state and portrait when applicable.
- Public smoke now covers 15 checks instead of 10.
- Setup selftest now points to the 0.30.09 installer path.

### Fixed

- Dashboard persona-state path now respects operator-provided/environment state.
- Key state writes use atomic local file replacement to reduce partial-write corruption.
- Persona SVG validation catches broken portrait assets.

### Preserved

- Switchable LLM design.
- `max_active_llms=1` invariant.
- No heavy LLM autostart by default.
- Markdown in-context handoffs: `task_xxx_project_yyy_stage_context.md`.

## 0.30.05
### Added

- Added `noemaforge persona list|active|show|activate|evolve|validate`.
- Added persona codename catalog with 23 roles, including `Бехтерев` for `system.guard/surgeon` and `Гармр` for `system.guard/scary`.
- Added generated SVG self-portraits for every persona and stateful portrait evolution on activation/evolve.
- Added 55 additional pipeline templates, bringing the runtime catalog to 60 pipelines.
- Added 380 workflow/agent-life pattern entries across Creatures-like agent life, Black & White-like training, Petz/Tamagotchi/Sims needs loops, n8n-style automation, Temporal-like durable workflows, Airflow-like DAGs and GitHub Actions-like CI/event workflows.
- Added `noemaforge pipeline patterns` to query the pattern catalog.
- Added two low-hanging-fruit collections: operator polish and pipeline reliability.
- Extended minimal dashboard with dynamic pipeline selection, persona card, pattern count and persona count.

### Changed

- `noemaforge pipeline validate` now checks pipelines, teams, pattern catalog, persona catalog, portraits and low-hanging-fruit references.
- `noemaforge mvp-smoke --json` now validates pattern and persona surfaces in addition to the public MWP lifecycle.
- `setup.sh --selftest` now compiles `persona_runtime.py` and validates persona/pattern catalogs.

### Preserved

- The runtime remains switchable-LLM only: `max_active_llms=1`.
- Heavy LLM backends are not enabled for boot/autostart by this release.
- Pipeline handoff stays markdown in-context: `task_<task_id>_project_<project_id>_<stage>_context.md`.

## 0.30.0
NoemaForge 0.30.0 packages the low-hanging fixes into a public-ready minimum viable / minimum workable release.

### Added

- Public-friendly `noemaforge status --json` and plain status output.
- `noemaforge mvp-smoke --json` to validate the public CLI/pipeline surface without a running LLM.
- `sudo noemaforge forensics` safe support bundle command.
- `docs/MVP_OPERATOR_GUIDE.md` and `docs/PUBLIC_MVP_CHECKLIST_0.30.0.md`.
- Targeted tests for public pipeline lifecycle and status shape.

### Fixed

- Missing common shell library for helper scripts.
- Source-tree CLI root resolution.
- Pipeline option placement UX.
- MVP smoke JSON generation now uses one JSON writer, avoiding truncated output from repeated subprocess calls.

### Preserved invariants

- One active LLM backend by default.
- Heavy GPU LLMs are manual/policy-gated, not boot-time defaults.
- Pipelines pass context through markdown handoff packets, not concurrent LLM teams.
- Vault/model data is not deleted by install/uninstall flows.

## 0.29.20
- Made pipeline global options accepted before or after subcommands.
- Added pipeline artifact registry, `summary`, `next-packet`, and `artifact` commands.
- Preserved existing `approve`, `doctor`, `export`, and dashboard-state flow.
- Added `artifact.count` and next actions to dashboard state.
- Extended task records with `pipeline_id`, `project_id`, and blockers.

## 0.29.19
- Added `noemaforge configs/model-profiles.{json,yaml}`.
- Added `noemaforge profiles list|show|recommend`.
- Added `noemaforge normalize-models` to accept full GGUF files and first split shards only.
- Documented minimal/balanced/writer/research/gpu-heavy profiles with `max_active_llms=1`.
- Added public docs for safe model recommendations by RAM/VRAM tier.

## 0.29.18
- Added root `setup.sh` as a single public entry point.
- Added `install_noemaforge_0.30.0_mvp.sh` and `uninstall_noemaforge_0.30.0_mvp.sh`.
- Restored missing `lib/noemaforge-common.sh` required by recovery helpers.
- Made `noemaforge/bin/noemaforge` resolve `NOEMAFORGE_ROOT`, `/opt/noemaforge`, or unpacked archive paths.
- Added helper fallback for source-tree/dev execution.
- Added `docs/QUICKSTART_VM.md` and `docs/SETUP_MODES.md`.

## 0.29.17
### Added

- `noemaforge pipeline advance` for stage/status updates with event logging and `decisions.md` append.
- `noemaforge pipeline dashboard-state` for exporting live static-GUI state.
- `noemaforge pipeline validate` for checking pipeline catalog/team/switchable-LLM invariants.
- `noemaforge trixie-preflight` read-only preflight for mount, datasets, llama binary/libs and optional runtime sockets.
- `sudo noemaforge firstboot-archive` baseline archiver for accepted degraded firstboot artifacts.
- Documentation:
  - `docs/FIRSTBOOT_QUICKFIXES_0.29.17.md`
  - `docs/PIPELINE_CONSOLE_0.29.17.md`
  - `docs/OPERATOR_PAUSE_GUI_RECOVERY.md`

### Fixed

- `noemaforge-firstboot-smoke.sh` scorecard checks no longer fail spuriously under `set -o pipefail`.
- `firstboot_orchestrator.py` now emits `staffing_state = meets_target | degraded_selected | unstaffed`.
- Firstboot now blocks all-zero selected scorecards before epoch apply/reboot.
- Firstboot now blocks missing mandatory core roles before epoch apply/reboot.
- Degraded-but-viable mandatory core staffing now continues with explicit warning instead of collapsing to `N/A`.

### Improved

- Minimal pipeline GUI can consume generated `dashboard-state.json` instead of only demo state.
- CLI help now exposes `pause`, `trixie-preflight`, `firstboot-archive` and new pipeline commands.
- `docs/TODO.md` updated to reflect completed/partial quickfix items without hiding remaining launcher/evaluation gaps.

### Preserved invariants

- Switchable LLM only: `max_active_llms = 1`.
- No parallel heavy model runtime by default.
- No heavy GPU LLM backend autostart on boot.
- GUI/NVIDIA stability remains higher priority than background LLM automation.

## 0.29.16
### Changed

- Reworked `noemaforge/templates/pipeline-dashboard` into a minimal working admin console.
- Reduced visual noise: one command bar, six KPI cards, lifecycle list, handoff pattern, generated CLI command.
- Connected visible indicators to metrics already present in `configs/metrics-catalog.yaml`:
  - `flow.wip`;
  - `llm.error_rate`;
  - `llm.latency_ms.p95`;
  - `sec.incidents.open`.
- Preserved switchable-LLM invariant: visible `1/1` active LLM display.
- Added `dashboard-state.example.json` for optional static/live state handoff.

### Not changed

- No runtime dependency added.
- No frontend framework added.
- No copied external GUI code.
- No simultaneous LLM/team assumption introduced.

## 0.29.15
### Added

- NoemaForge-native switchable-LLM pipeline scaffold.
- `pipeline_runtime.py` with catalog/run/list/show/snapshot commands.
- JSON runtime configs plus YAML human mirrors.
- Pipeline dashboard static GUI template.
- Wiki and TODO pages for process-centric orchestration.

### Preserved

- BigBro-BOS stability invariant: one active LLM by default.
- Heavy LLMs remain explicit/policy-gated, not always-on.

### Note

Legacy project material was used only as an architectural reference. No legacy source code, prompts or proprietary naming were reused.

## 0.29.14
### Added

- Added 0.29.14 research source folder with marketing, tool-gap, metrics, and updated debug context inputs.
- Added GitHub wiki pages for public launch, tool-gap matrix, evaluation/observability metrics, Trixie recovery invariant, and roadmap/TODO crosswalk.
- Added `docs/public/marketing.md` and public README.
- Added extracted prelaunch tool packs under `prelaunch/tools/source/`.
- Added Debian Trixie and macOS wrapper scripts for manifest downloader and library pipeline review.

### Changed

- Updated wiki index with 0.29.14 additions.
- Preserved 0.29.13 package structure and extended it rather than replacing it.
- Reinforced the operating rule that heavy LLM autostart remains disabled until manager policy is resource-aware.

### Not changed

- No runtime services were enabled.
- No model autostart policy was changed.
- No production installer behavior was modified.

## 0.29.13
### Added

- GitHub wiki-like knowledge base under `docs/wiki/`.
- Consolidated memory/vector architecture notes.
- Consolidated product kernel, shell, role pack, and contribution unit notes.
- Consolidated Evolve Lab roadmap and separation-of-duties model.
- Consolidated evaluation, observability, runtime, safety, UX, and team metrics notes.
- TODO/roadmap/research crosswalk for issue creation.
- `prelaunch/tools` folder with preserved Windows originals and new Trixie/macOS wrappers.

### Preserved

- Full 0.29.11 recovery/stability baseline.
- Original research markdown files under `docs/research_sources/`.
- Original Windows tool packs under `prelaunch/tools/windows_original/`.

### Not changed

- No runtime services are modified by this merge package.
- No installer behavior is automatically changed.
- Heavy model autostart remains discouraged until gated startup is implemented.
