# TODO

## Active follow-ups

- Verify final archive on the target machine after upload.
- Replace placeholder release dates in `history/CHANGELOG.md` when authoritative Git tags or GitHub releases exist.
- Keep future Markdown documentation in the approved folders only.
- Keep changelog material in `history/CHANGELOG.md` instead of creating parallel release-note files.
- Live NVIDIA/GDM/LLM validation is still open and target-machine-only; `target-live-validation-readiness-core` now records it as `blocked_until_target_machine_evidence` and validates the command/evidence manifest locally without running live service commands.
- Full CPU/GPU canonical model evaluation is still open and target-machine-only; `canonical-model-eval-matrix-readiness-core` now records it as `blocked_until_canonical_model_matrix_evidence` and validates the model inventory, CPU/GPU scorecard, role coverage, eval-suite, health-filter and archive manifest locally without running target evaluations.
- Clean install validation with `/mnt/noemaforge-share` is still open and target-machine-only; `clean-install-share-readiness-core` now records it as `blocked_until_target_clean_install_evidence` and validates the dry-run, host install, canonical share, previous-install detachment, preflight, emergency-mode and archive evidence manifest locally without running installer commands.
- Patched10 full-composite validation is still open and target-machine-only; `full-composite-target-run-readiness-core` now records it as `blocked_until_target_full_composite_evidence` and validates the install baseline, preflight, `--full_composite 0` command plan, transcript, summary artifacts, display recovery and archive evidence manifest locally without running first-start commands.
- Patched10 full-composite SSH validation is still open and target-machine-only; `full-composite-ssh-readiness-core` now records it as `blocked_until_target_ssh_evidence` and validates SSH service/listener, known-host access, SSH-observed run transcript, abort/display recovery and redacted archive evidence locally without opening SSH sessions.
- `/run/nologin` recovery confirmation is still open and target-machine-only; `nologin-recovery-readiness-core` now records it as `blocked_until_target_nologin_recovery_evidence` and validates pre/post nologin probes, abort cleanup, display recovery and archive evidence locally without running recovery commands.
- Emergency GUI recovery validation on Debian Trixie GDM is still open and target-machine-only; `emergency-gui-recovery-readiness-core` now records it as `blocked_until_target_emergency_gui_recovery_evidence` and validates display-manager/GDM baseline, operator-approved `pause --wait` and `gui-rescue --wait`, display-manager alias, post-rescue `/run/nologin` guard and archive evidence locally without running systemd or recovery commands.
- Share automount reboot confirmation is still open and target-machine-only; `share-automount-reboot-readiness-core` now records it as `blocked_until_target_share_reboot_evidence` and validates nofail/automount baseline, operator-approved reboot, post-reboot emergency/rescue guard, share access and archive evidence locally without rebooting or mounting.
- Post-reboot validation and log archive as wiki patch is still open and target-machine-only; `post-reboot-validation-archive-readiness-core` now records it as `blocked_until_target_post_reboot_archive_evidence` and validates post-reboot baseline, service health, live smoke transcripts, forensics/journal archives and wiki patch manifest evidence locally without running target validation commands.
- Post-reboot health for `noemaforge-llama@main`, gateway and ToolProxy is still open and target-machine-only; `post-reboot-service-health-readiness-core` now records it as `blocked_until_target_post_reboot_service_health_evidence` and validates boot baseline, gateway service, operator-approved manual main-backend start/stop, ToolProxy service, socket/API smoke and archive evidence locally without running systemd, socket or LLM commands.
- Composite post-reboot GPU/GDM/gateway/ToolProxy validation is still open and target-machine-only; `post-reboot-gpu-gdm-gateway-toolproxy-readiness-core` now records it as `blocked_until_target_post_reboot_gpu_gdm_gateway_toolproxy_evidence` and validates boot baseline, operator approval, GPU/GDM state, gateway and ToolProxy service state, socket smoke evidence, archive hash and redaction review locally without running systemd, NVIDIA, gateway, ToolProxy, LLM or archive commands.
- Systemd/GDM/NVIDIA validation is still open and target-machine-only; `systemd-gdm-nvidia-live-validation-readiness-core` now records it as `blocked_until_target_systemd_gdm_nvidia_live_validation_evidence` and validates boot/systemd baseline, operator approval, display-manager/GDM state, NVIDIA driver/device signal, secure-boot/kernel log evidence, post-reboot recovery guards and archive evidence locally without running systemd, GDM, NVIDIA, journal or archive commands.
- Live ToolProxy capability issue/verify smoke is still open and target-machine-only; `toolproxy-capability-live-smoke-readiness-core` now records it as `blocked_until_target_toolproxy_capability_live_smoke_evidence` and validates ToolProxy baseline, operator approval, live issue, live verify, token redaction/revocation and archive evidence locally without running ToolProxy commands.
- Live ToolProxy socket plus `llm.chat` smoke is still open and target-machine-only; `toolproxy-live-llm-smoke-readiness-core` now records it as `blocked_until_target_toolproxy_live_llm_smoke_evidence` and validates ToolProxy socket baseline, operator approval, `llm.chat` capability binding, live LLM smoke output, token revocation and archive evidence locally without running ToolProxy, socket or LLM commands.
- Live gateway plus `noemaforge-llama@main` smoke is still open and target-machine-only; `gateway-main-live-smoke-readiness-core` now records it as `blocked_until_target_gateway_main_live_smoke_evidence` and validates service baseline, operator approval, manual main-backend start, gateway socket/status, smoke/chat transcript and stop/archive evidence locally without running systemd, gateway, socket or LLM commands.
- Debian Trixie preflight JSON capture is still open and target-machine-only; `trixie-preflight-target-readiness-core` now records it as `blocked_until_target_trixie_preflight_evidence` and validates operator-approved read-only preflight JSON, Debian/kernel baseline, dependency surface, runtime socket snapshot and archive evidence locally without running sudo, preflight, systemd or socket commands.
- Post-failure forensics bundle capture is still open and target-machine-only; `failure-forensics-bundle-readiness-core` now records it as `blocked_until_target_failure_forensics_bundle_evidence` and validates failure context, operator-approved forensics transcripts, bundle integrity, redaction review, runtime log coverage and inspection follow-up locally without running sudo, forensics, journal, systemd or upload commands.
- Target-hardware GUI recovery path confirmation is still open and target-machine-only; `target-gui-recovery-path-readiness-core` now records it as `blocked_until_target_gui_recovery_path_evidence` and validates display baseline, operator-approved pause and GUI rescue transcripts, post-rescue display and `/run/nologin` state, archive evidence and inspection follow-up locally without running sudo, recovery, systemd or archive commands.
- Final live-media backend adapters remain open until explicit backend selection; `media-backend-selection-readiness-core` now records this as `blocked_until_explicit_media_backend_selection` and validates required VLM, STT, TTS, music, image, video and segmentation/mask slots, operator selection records, privacy gates, telemetry/selftest evidence and target smoke artifact hashes locally without starting media backends.
- Live testbench suite execution is still open and target-machine-only; `live-testbench-suite-readiness-core` now records it as `blocked_until_target_live_testbench_suite_evidence` and validates target baseline, operator approval, live-suite catalog, `--include-live` command transcript, resource telemetry artifacts, baseline comparison, wiki patch manifest and archive hash locally without running testbench, live suites, GPU probes or wiki patch commands.
- Final Admin GUI scenario replay is still open and target-machine-only; `final-gui-scenario-replay-readiness-core` now records it as `blocked_until_target_final_gui_scenario_replay_evidence` and validates the required `polished_admin_gui_guided_scenario`, target baseline, operator approval, Admin greeting transcript, routed pipeline launch, Dev Team action, model-evolution action, full transcript, artifact hashes, redaction record, archive hash and version-bump guard locally without running the GUI, browser, pipelines, Dev Team or model-evolution commands.
- [x] Knowledge purpose boundary: Every knowledge realm/project has a typed purpose artifact with mission, scope boundaries, out-of-scope topics, expected source quality and update policy; ingest, lint and review must reference it before adding or approving knowledge. Closed by `knowledge-purpose-artifacts-core`
- [x] Knowledge graph lint boundary: Graph maintenance detects orphan concepts, unsupported claims, stale passages, unresolved conflicts and weak realm bridges, then surfaces explicit Administrator/Surgeon maintenance work for pre-start or scheduled maintenance loops. Closed by `knowledge-graph-lint-core`
- [x] Knowledge core relations boundary: Canonical knowledge relations are frozen as typed links among Source, Passage, Claim, Entity, Concept, Conflict, Trail, TaskContext, Decision and Artifact; publication gates for Passage, Claim, Conflict and Concept must emit auto_publish, review or quarantine decisions before retrieval can treat objects as published. Closed by `knowledge-core-relations-gates-core`
- [x] Role corpus binding boundary: Role evaluation keeps role-scoped JSONL suites, binds roles to real seed/external corpora when available, and marks missing required corpora as N/A instead of silently faking coverage. Closed by `role-corpus-binding-core`
- [x] Hypergraph error improvement boundary: Error learning stores error_events, corrections and regression_cases, separates source defects from labeling/chunking/extraction/linking defects, reuses approved corrections for retraining and evaluation, and records the model, run and profile that produced each error. Closed by `hypergraph-error-improvement-core`
- [x] Setup default path boundary: The blessed onboarding path is release unpack or git clone, then root ./setup.sh in VM mode first, then host install only by explicit operator choice; Windows helpers are optional side tools and are never required for the canonical path. Closed by `setup-default-path-core`
- [x] Setup front door boundary: Root setup.sh is the single setup front door, supports vm/host/docker-dev plus install-root/data-root/model-profile/with-share/offline-after-setup flags, and emits bootstrap/firstboot progress phases so newcomers do not discover helper scripts manually. Closed by `setup-front-door-core`
- [x] Firstboot progress boundary: Firstboot progress is a human-readable CLI/TUI surface over JSON status/events, shows seed_copy/host_preflight/vault_scan/inbox_normalize/candidate_staging/role_staffing/epoch_apply/reboot_pending phases, and ends with next actions so the operator always knows the current step. Closed by `firstboot-progress-view-core`
- [x] Model profile boundary: New users choose a minimal/balanced/writer/research/gpu-heavy profile; each profile declares model hints, role staging targets, resource floors and a no-auto-download staging manifest so setup and firstboot avoid manual model-file curation. Closed by `model-profile-selection-core`
- Added an executable Model Switch Policy contract with QA and performance tests for role to preferred-local, approved-remote, fallback and `N/A` decisions. Closed by `model-switch-policy-core`.
- [x] Add performance metrics: latency, memory, operation count, artifact size. Closed by `pipeline-performance-metrics-core`: the executable contract validates stage latency, memory, operation count, artifact size and status-count summaries with QA and performance tests.
- [x] Cross-platform prep boundary: tools/prep/*.py is the source of truth for Vault scan, inbox processing, metadata export and firstboot staging; Windows PowerShell/CMD and Linux/macOS shell scripts are thin wrappers over noemaforge_prep_core.py, so prep can run without a Windows host. Closed by `cross-platform-prep-core`
- [x] Setup mode boundary: Linux host mode uses native services and local paths, macOS dev mode is non-privileged validation and light workflows, VM mode is the recommended no-risk onboarding path, and docker-dev is development/test only, not the full production NoemaForge path. Closed by `setup-mode-matrix-core`
- [x] Onboarding ladder boundary: README.md is the 5-minute overview, docs/QUICKSTART_VM.md is the first-success VM path, docs/SETUP_MODES.md explains host/VM/docker-dev/macOS-dev differences, and docs/PRODUCTION_INSTALL_TRIXIE.md is only entered after quickstart validation; primary docs do not lead with Windows lab workflow. Closed by `onboarding-ladder-core`

## 0.32.2 hardening — completed in release/0.32.2-hardening

- [x] Added file-backed JobManager (noemaforge/src/job_manager.py): queued/running/done/failed/cancel_requested/cancelled states, idempotency keys, durable JSONL job log.
- [x] Added ProcessGroupRunner (noemaforge/src/process_group_runner.py): subprocess isolation with cancel support.
- [x] Wired JobManager into AdminGuiServer: `/api/jobs`, `/api/jobs/cancel`, `/api/jobs/stream` SSE.
- [x] Added direct GUI-action routing in AdminGuiServer: vault-reinventory, model-selection-continue, epoch-apply as plan-only privileged jobs.
- [x] Added startup preflight module (noemaforge/src/startup_preflight.py).
- [x] Wired PreflightSuite into AdminGuiServer as a non-fatal gate.
- [x] Added model-evolution chat routing.
- [x] Added ConfigValidator JSON/YAML parse gate (noemaforge/src/config_validator.py).
- [x] Wire SessionStore and EventLog into AdminGuiServer: `session_current()`, `events_list()`, `session_set_mode()` — GET /api/session/current, GET /api/events, POST /api/session/mode.
- [x] Frontend session restore on page load (startup polls /api/session/current, falls back to dashboard state).
- [x] Frontend event polling with deduplication by index (`pollEvents()` every 10 s).
- [x] Frontend mode persistence via POST /api/session/mode after model-selection pick.
- [x] P1 fix: return-in-finally at noemaforge_core.py:2118 removed (was silently suppressing exceptions).
- [x] Stale version metadata bumped to 0.32.2: release.json, docs/release.json, noemaforge.runtime.yaml, quantization-policy.yaml (3 copies), model_capabilities.py heuristic tag.
- [x] 244 stale alpha/0.29.x files removed from git tree (moved to trash/).
- [x] Docs versions bumped: noemaforge/docs/README.md, noemaforge/docs/Manifest.md → 0.32.2.

## 0.32.2 Cursor Brief — remaining open items

Items below are DoD requirements from the Cursor Implementation Briefs (Days 1–5) not yet closed.

### Day 1 — repository hygiene (partial — needs Linux / BigBro-BOS for shell validation)

- [ ] Run `find . -name '*.sh' -type f -exec bash -n {} \;` on BigBro-BOS to verify all shell scripts pass syntax check.
- [ ] Run `noemaforge/tools/prep/noemaforge-version-audit.sh --root . --expected 0.32.2 --strict-all` on BigBro-BOS.
- [x] Check `noemaforge/configs/llm-backends-policy.yaml` and `noemaforge/configs/role-catalog.yaml` for stale version strings (0.31.13.alpha, 0.29.10, 0.29.11) and update if found. — Both files clean, no stale strings (2026-05-28).
- [x] Audit `noemaforge/src/dataset_inventory.py` and `noemaforge/src/vault_reorg.py` for any hardcoded RUNTIME_VERSION assignments outside `noemaforge_version.py`. — Both clean (2026-05-28).
- [x] Verify `.gitignore` has `__pycache__/` and `*.pyc` exclusions (and add them if missing). — Created full `.gitignore` (2026-05-28).

### Day 3 — frontend UX (partial — needs live GUI on BigBro-BOS)

- [x] Add explicit mode confirmation message in chat after user picks a model-selection mode: "Mode selected: normal / full / full_composite N". — Implemented in app.js sendAdmin() (2026-05-28).
- [ ] Verify user message is appended exactly once and not duplicated after page refresh (needs manual smoke on live GUI).
- [ ] Manual smoke: `noemaforge dashboard start`, open `http://127.0.0.1:8765/`, send a message, refresh page, verify messages and selected mode both survive.

### Day 4 — duplicate-safe jobs (partial — needs BigBro-BOS smoke)

- [x] Cancel marker wired in `job_cancel()`: status set to `cancel_requested`; `.cancel` sentinel file written to `jobs_dir` for subprocess polling (2026-05-28). Remaining: long-running runtime scripts (`noemaforge first-start`) must read the sentinel file — needs BigBro-BOS.
- [ ] Manual smoke (BigBro-BOS): send two identical `/api/model-selection/continue` requests back-to-back and confirm the same `job_id` is returned both times.
- [ ] Manual smoke (BigBro-BOS): click Vault re-inventory twice rapidly and confirm one job, not two.

### Day 5 — release validation (BigBro-BOS required)

- [ ] Run full test suite on BigBro-BOS: `python -m unittest discover noemaforge/tests/` and record pass/fail counts.
- [ ] Regenerate SHA256SUMS after all branches are merged to `release/0.32.2-hardening`: `bash noemaforge/bootstrap/make-checksums.sh`.
- [ ] Create clean release archive: `tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' -czf noemaforge-0.32.2.tar.gz noemaforge/ && sha256sum noemaforge-0.32.2.tar.gz > noemaforge-0.32.2.tar.gz.sha256`.
- [ ] Target-machine validation checklist (all on BigBro-BOS):
  - Admin GUI stays alive during first-start `--dry-run --keep-display`.
  - Admin chat responds to smalltalk/help without launching a pipeline.
  - Mode switch persists and is visible after browser refresh.
  - Continue model selection: two clicks return the same job_id.
  - Vault re-inventory: two clicks return the same job_id.
  - Page refresh restores message history and active job state.
  - Job stop/cancel leaves no stale active jobs.
  - Gateway, ToolProxy and main llama backend smoke pass or return clear blocked status.
- [ ] Issue explicit GO/NO-GO merge decision in `noemaforge/docs/release/RELEASE_VALIDATION_CHECKLIST_0.32.2.md` after all above targets pass.

## Started in this workspace

- [x] Edge/TinyML/OTA pack: MQTT/serial, TinyML validation, gateway inference, rules, manifest signing and OTA rollback. Closed by `edge-tinyml-ota-pack-core`: component contracts are now checked together as an offline aggregate contract across Sense, TinyML, gateway inference, edge rules, OTA rollback and reference targets.
- [x] Strict Markdown placement cleanup. Closed by `docs-hygiene-prelaunch`: legacy root and top-level Markdown is either migrated into canonical `noemaforge/docs` content or quarantined under project trash, while the executable docs hygiene gate now enforces the strict active-tree layout.
- [x] Git exchange pack: quarantine-first RolePack, RoleFlow, EvalPack and KnowledgeGraphPack import/export. Closed by `git-exchange-quarantine-core`: exchange imports are manifest-backed quarantine drafts with Scary/Surgeon/Admin review gates, explicit import/export action allowlists and lab-only ModelDeltaPack handling.
- [x] Pipeline editor pack: drag-and-drop edit, clone as new pipeline class, Scary/Architecture/Admin review. Closed by `pipeline-editor-pack-core`: the editor pack is a draft-only offline contract that normalizes drag-and-drop events, clones pipelines as new classes and requires Scary/Architecture/Admin review before activation.
- [x] Extend bounded-improvement depth to real multi-step Dev Team loops with checkpoint/stop handling. Closed by `dev-bounded-loop-core`: bounded Dev Team loops now write plan/checkpoint artifacts, enforce step/time budgets, honor stop requests and never auto-apply changes.
- Added an executable production-AI lifecycle contract in `noemaforge/src/production_ai_contracts.py`.
- Added a seed Unified Registry in `noemaforge/configs/unified-registry.json` covering model, prompt, retriever, reranker, tool-policy, pipeline, persona, task, epoch and eval-pack entries.
- Added an executable Unified Registry validation runtime for local refs, eval-pack links and required-kind coverage.
- Added schema and unittest coverage for registry normalization, EvaluationGate decisions, safe rollout transitions and ReleaseEvidence artifacts.
- Added an executable EvaluationGate validation runtime across code, prompt, model, RAG, pipeline and router domains.
- Wired trace IDs into Admin GUI messages/jobs, model-selection artifacts and pipeline run manifests.
- Added an executable trace coverage validator for Admin GUI messages/jobs, Admin runtime, pipeline/model-selection, epoch apply, ToolProxy and telemetry surfaces.
- Wired `brainctl prestart apply-epoch` to emit `<candidate_epoch_dir>/release_evidence.json` before promotion.
- Added `abstention-policy.json` plus deterministic route/ask/defer/block decisions for Admin routing.
- Added an executable AbstentionPolicy validation runtime for thresholds, action map and route/ask/defer/block scenarios.
- Added an executable Intent Router Eval Pack with per-route and per-abstention-action metrics.
- Added executable Model/Prompt/Pipeline/Epoch/Tool Policy Card contracts generated from Unified Registry entries and ReleaseEvidence.
- Added an executable data-centric error loop artifact that classifies failures and emits regression, eval-pack, task, fix and review records.
- Added generic registry promotion evidence for prompt/routing changes: EvaluationGate + RolloutDecision + ReleaseEvidence before status updates.
- Added an executable RAG eval seed for retrieval hit rate, citation coverage, groundedness and answer helpfulness.
- Added a deterministic docs RAG runtime seed for docs/wiki indexing, lexical retrieval, heuristic reranking and cited grounded answers.
- Added an executable trajectory eval seed for bounded agent loops, artifacts, safety flags and safe final states.
- Added an executable MCP adapter registry validator for zero-trust, deny-by-default adapter exposure.
- Added a stdlib fallback loader for the local MCP adapter catalog so MCP smoke tests do not require PyYAML.
- Added an executable A2A interoperability registry validator for optional, reviewed, disabled-by-default peer envelopes.
- Added an executable GraphRAG experiment pack behind the classic RAG EvaluationGate baseline.
- Added an executable Graph Projection Views contract with QA and performance tests for wiki/operator/task/conflict projections derived from graph state. Graph projection boundary: Wiki-like pages are projections derived from graph state: every projection carries source graph refs, graph digest, generated_at, projection type, and a not-source-of-truth notice so human-readable pages never become the canonical knowledge store. Closed by `graph-projection-views-core`.
- Added an executable Graph Patch Provenance contract with QA and performance tests for source graph refs, graph digests, trace IDs, operation provenance, review decisions and rollback plans. Closed by `graph-patch-provenance-core`.
- [x] Add artifact registry table for outputs/reviews/graph patches. Closed by `artifact-registry-table-core`: the executable table contract validates output, review and graph patch artifact rows with SHA256 evidence, relative paths, trace IDs, producer metadata, review state and graph patch references.
- [x] Wire pipeline CLI into installed `/usr/local/bin/noemaforge` during installer/apply step. Closed by `pipeline-cli-install-wiring-core`: the offline contract validates the promoted installer symlink to `/opt/noemaforge/bin/noemaforge`, setup CLI selftest coverage, canonical self-guarding and the installed pipeline command surface.
- [x] Add safe worktree creation for `evolution` pipeline. Closed by `safe-worktree-evolution-core`: worktree creation is evolution-only, plan-only by default, branch-namespaced, destination-confined to the run worktrees directory and guarded by explicit `--apply` before local git execution.
- [x] Add ToolProxy policy binding per pipeline stage. Closed by `pipeline-toolproxy-stage-binding-core`: generated pipeline packets and run manifests now include stage-scoped ToolProxy capability-token bindings with explicit allowed actions, default-denied network access, approval for mutating actions and sandbox flags for `exec.run`.
- [x] Add stage validators and smoke tests. Closed by `pipeline-stage-validator-smoke-core`: `noemaforge pipeline stage-validate` now checks typed sidecars, checksums, output quality, contract-matching artifacts and ToolProxy bindings, while `stage-smoke` proves the validator on a temporary offline run.
- [x] Add active-file readability to release hygiene. Closed by `docs-hygiene-prelaunch`: `docs_hygiene_runtime.py` now fails active files that appear in directory listings but cannot be stat/read-opened, and the duplicate unreadable Windows-original manifest downloader pack is quarantined under project trash while the canonical `prelaunch/tools/source` copy remains active.
- [x] Add YAML inventory readability fallback gate. Closed by `yaml-inventory-readability-core`: active `.yaml` and `.yml` files are inventoried with a stdlib-only readability and YAML-lite syntax guard for UTF-8 decoding, tab indentation and flow bracket balance when full PyYAML validation is unavailable.
- [x] Add manifest/checksum trash exclusion gate. Closed by `manifest-checksum-exclusion-core`: release manifests and SHA256 lists now have an executable validator that excludes project trash and generated caches, checks active-file counts, verifies manifest hash sidecars and catches hash mismatches.
- [x] Add canonical release-history filename guard. Closed by `release-artifact-name-guard-core`: `history/CHANGELOG.md` remains the only release-history target while parallel release-note, extra changelog, verification-report and raw research/source report filenames are rejected in the active tree.
- Added an executable PEFT/LoRA lab readiness validator with training and production weight mutation disabled.
- Added an executable docs hygiene gate with QA and performance tests for approved Markdown folders, canonical changelog refs and checked production-AI TODO items.
- Added an executable CI model gates pack with QA and performance tests for latency, memory, golden replay, schema compatibility and signature evidence.
- Added an executable signed model manifest contract with QA and performance tests for sha256, signature, resource budgets and independent QA blocking.
- Added an executable Edge Rules Engine contract with QA and performance tests for whitebox fallback, guarded ML score, thresholds, anomaly routing and drift flags.
- Added an executable TinyML Node contract with QA and performance tests for golden vectors, latency/RAM/model-size/hash gates and fallback-rule-only decisions.
- Added an executable Gateway Inference Service contract with QA and performance tests for manifest-only model loading plus REST/MQTT inference, health, readiness and metrics endpoints.
- Added an executable Sense Layer Edge contract with QA and performance tests for MQTT, serial and system-metrics ingestion into one explicit source-trust schema.
- Added an executable OTA Update Layer contract with QA and performance tests for staged rollout, rollback, signed manifests, CI evidence and health-gated activation.
- Added an executable Edge Reference Targets contract with QA and performance tests to keep KubeEdge, eKuiper, Mender and RAUC optional post-MVP/reference integrations.
- Added an executable MultiOS Runtime Host contract with QA and performance tests for OS/hardware probes, runtime selection, optional Windows/macOS control hosts and disabled-by-default remote HTTP health.
- Added an executable Concept Frame governance contract with QA and performance tests for Admin/Architect decision framing, trace IDs, risks/options, dangerous-action approval and Pipeline_RFC hooks.
- Added an executable Sense State / Privacy Filter contract with QA and performance tests for coarse host metrics and redaction-before-persistence of raw paths, usernames, environment and command lines.
- Added an executable Drive State / Drive Adapter contract with QA and performance tests for bounded pressure, fatigue, urgency and curiosity modulation from filtered Sense_State.
- Added an executable Honesty Protocol contract with QA and performance tests for Unknown, Need-Research and traceable Error_Attribution response states.
- Added an executable Slop Score / Critic Stack contract with QA and performance tests for advisory text, provenance and slop quality gates.
- Added an executable Provenance / Watermark Detection Verdict contract with QA and performance tests for advisory aggregation across manifest, signature, watermark and content-consistency hooks.
- Added an executable Research Packet contract with QA and performance tests for offline, source-allowlisted, freshness-bounded cited scouting.
- Added an executable Pipeline RFC contract with QA and performance tests for RFC, dry-run, eval evidence, rollback plan and explicit approval before pipeline mutation.
- Added an executable Typed Governance Track contract with QA and performance tests for dependency-order and registry attachment across Concept_Frame, Sense_State, Drive_State, Detection_Verdict, Research_Packet and Pipeline_RFC.
- [x] Track typed governance contracts with the Typed Governance Track dependency-order and registry-attachment gate.
- Added an executable Alpha Backlog Fence contract with QA and performance tests for keeping typed governance backlog-only until alpha gate stability is manually reviewed.
- [x] Keep this as backlog-only until alpha gates are stable.
- Added an executable Role Kernel / ActiveNN contract with QA and performance tests for four default roles, inactive optional RolePacks, one-heavy-worker batons and the lab-only Evolve boundary.
- [x] Keep base install focused on four default roles: Admin, Surgeon, Scary, Evolver/Darwin.
- [x] Ship optional roles as inactive RolePacks instead of active core roles.
- [x] Implement `ActiveNNManager` with one-heavy-worker invariant and durable sleep/wake batons.
- [x] Treat Admin and Scary as lightweight always-present supervisors, not heavy resident workers.
- [x] Preserve Evolve boundary: mutation only in lab; promotion only through Scary -> Surgeon -> Admin.
- Added an executable RoleFlow Orchestration contract with QA and performance tests for role switching, branching, guard/approval/rollback edges and durable baton payloads.
- [x] Formalize `RoleFlow` / `orchestration_graph` schema for role switching, branching, guards, approvals, rollback edges, and baton payloads.
- Added an executable NoemaShell Lite contract with QA and performance tests for the primary operator shell: active worker, approvals, artifacts, resource budgets, safe mode and recovery.
- [x] Make NoemaShell Lite the primary operator shell: active worker, approvals, artifacts, resource budgets, safe mode, recovery.
- Added an executable Git Exchange Quarantine contract with QA and performance tests for quarantine-first RolePack, RoleFlow, EvalPack, KnowledgeGraphPack, ArtifactPack and lab-only ModelDeltaPack imports.
- [x] Add quarantine-first `git_exchange` for RolePack, RoleFlow, EvalPack, KnowledgeGraphPack, ArtifactPack, and lab-only ModelDeltaPack.
- Added an executable HFBridge Metadata contract with QA and performance tests for metadata-first/read-mostly discovery and no automatic weight, dataset or runtime imports.
- [x] Keep HFBridge metadata-first/read-mostly for MVP; never auto-import arbitrary weights or data into runtime.
- Added an executable Clean Distribution Allowlist contract with QA and performance tests for allowlist-built public distributions and keeping optional HF/community/history/quarantine material outside the public core seed.
- [x] Build public distributions from an allowlist and keep optional HF/community/history/quarantine material outside core seed.
- Added an executable SmartHome Local Control contract with QA and performance tests for local-first devices, MQTT/Home Assistant/Zigbee/Z-Wave/Matter adapter surfaces, visible privacy state, emergency pause and SR/SSR-reviewed automations.
- [x] Smart Home local-first control pack: plugs, switches, vacuums, cameras, sensors, local server, value your privacy. Closed by `smarthome-local-control-core`
- [x] Add local-first SmartHome pack: smart plugs, switches, vacuums, cameras, sensors.
- [x] Keep home telemetry on local NoemaForge server by default: value your privacy.
- [x] Add local MQTT/Home Assistant/Zigbee/Z-Wave/Matter adapter surfaces.
- [x] Add no-hidden-camera/no-hidden-microphone policy and visible privacy state.
- [x] Add room graph, device registry, automation rules, emergency pause and SR/SSR review.
- Added an executable Media Capture Privacy contract `media-capture-privacy-core` with QA and performance tests: live microphone capture, live transcription and virtual camera mask plans require operator consent, visible privacy state, manual commands, no autostart and default-disabled capture backends.
- [x] Add privacy gates for camera/microphone capture and virtual camera masks.
- Added an executable Media Adapter Telemetry contract `media-adapter-telemetry-core` with QA and performance tests: every local media adapter has a plan-only selftest case and required resource telemetry fields for wall time, CPU time, RSS, disk I/O, artifact size and status.
- [x] Add resource telemetry and selftest cases for each media adapter.
- Added an executable Media Wiki Patch contract `media-wiki-patch-core` with QA and performance tests: wiki patch bundles can include media capability deltas and generated artifact manifests, and the manifest records both copied evidence files.
- [x] Extend wiki patches with media capability deltas and generated artifacts.
- Added an executable First Start Summary contract with QA and performance tests for grouped run output and PASS/WARN/FAIL markers.
- [x] Verify first-start summary output is grouped by run and uses PASS/WARN/FAIL markers.
- Added an executable ToolProxy Capability Token contract pack `toolproxy-capability-token-core` with QA and performance tests for issue/list/verify/revoke/smoke UX, secret redaction, SHA256-only persistence and offline token smoke. Closed by `toolproxy-capability-token-core`.
- [x] ToolProxy capability token issuance UX. Closed by `toolproxy-capability-token-core`.
- [x] ToolProxy capability token UX and issuance path. Closed by `toolproxy-capability-token-core`.
- Added an executable Release Provenance contract pack `release-provenance-core` with QA and performance tests for public archive SHA256, manifest pinning, detached signatures, install transcript and verification summary evidence.
- [x] Signed release provenance.
- Added an executable Package Dry-Run Validation contract pack `package-dry-run-validation-core` with QA and performance tests for setup/uninstall dry-run flags, syntax selftest, root guard, recursion guard and no-destructive dry-run scans.
- [x] Add install/uninstall dry-run tests to package validation.
- Added an executable Dashboard Launcher contract pack `dashboard-launcher-core` with QA and performance tests for `noemaforge dashboard path/state/serve/start/stop/status`, operator-writable dashboard-state, static UI serving and no LLM/media autostart.
- [x] Add local web dashboard launcher command.
- [x] Add local dashboard launcher command that writes dashboard-state and serves the static UI.
- Extended `dashboard-launcher-core` with user-level dashboard autostart enable/disable/status commands, dry-run coverage, systemd user timer generation under `XDG_CONFIG_HOME` and no root or LLM/media autostart requirement.
- [x] Add user-level dashboard autostart enable/disable commands.
- Added an executable Self-Test Trend Dashboard contract pack `selftest-trend-dashboard-core` with QA and performance tests for `noemaforge selftest trend`, multi-report case series, regression warnings and JSON/static HTML dashboard export.
- [x] Add trend dashboard over multiple self-test reports.
- Added an executable Pre-Merge Release Guard contract pack `premerge-release-guard-core` with QA and performance tests for `noemaforge selftest release-guard`, baseline/current self-test comparison, failed-case blockers and rollback-plan evidence.
- [x] Promote regression gate into pre-merge release guard for 0.31.x.
- Added an executable Self-Test Event Store contract pack `selftest-event-store-core` with QA and performance tests for `noemaforge selftest events ingest/export`, canonical SQLite test-event tables, deterministic run/case event IDs and JSON export.
- [x] Promote testbench summaries into SQLite canonical test-event tables in 0.31.x.
- Added an executable Self-Test RSS Slope contract pack `selftest-rss-slope-core` with QA and performance tests for `noemaforge selftest stress`, repeat RSS sample analysis, linear slope thresholds and leak-gated JSON artifacts.
- [x] Add stress/repeat runner for RSS-slope memory leak detection in 0.31.x.
- Added an executable Wiki Patch Commit Helper contract pack `wiki-patch-commit-helper-core` with QA and performance tests for `noemaforge wiki-patch commit-plan`, operator-reviewed local branch/commit scripts and no automatic push.
- [x] Add automatic wiki repo branch/commit helper after operator review in 0.31.x.
- Added an executable Pipeline Template Append contract pack `pipeline-template-append-core` with QA and performance tests for `noemaforge pipeline template-import` drafts, reviewed `template-append --approve` catalog writes and local catalog JSON output.
- [x] Turn `template-import` drafts into an explicit reviewed catalog-append workflow.
- Added an executable Executor Stage Worker contract pack `executor-stage-worker-core` with QA and performance tests for `noemaforge pipeline executor-step`, stage contracts, non-placeholder output gates, contract-matching artifacts and wait/advance events. Closed by `executor-stage-worker-core`.
- [x] Promote stage executor from scaffold to real execution engine. Closed by `executor-stage-worker-core`: `noemaforge pipeline executor-step` now validates stage contracts, non-placeholder output gates, contract-matching artifacts and wait/advance events without live host or LLM autostart.
- [x] Promote executor-step into a contract-driven stage worker in 0.31.x. Closed by `executor-stage-worker-core`.
- Added an executable Pipeline Stage Transition contract pack `pipeline-stage-transition-core` with QA and performance tests for `noemaforge pipeline approve|advance|pause|resume|fail`, stage-name validation, deterministic run-state updates and event-log evidence. Closed by `pipeline-stage-transition-core`.
- [x] Add stage transition commands: `advance`, `pause`, `resume`, `fail`, `approve`. Closed by `pipeline-stage-transition-core`.
- Added an executable Model Health Candidate Filter contract pack `model-health-candidate-filter-core` with QA and performance tests for `role-candidate-map.filtered.json`, model-health failed/excluded states and firstboot registry attachment. Closed by `model-health-candidate-filter-core`.
- [x] Confirm no failed-runtime model remains in `role-candidate-map.filtered.json`. Closed by `model-health-candidate-filter-core`: `role_tournament.py` now has a standalone validator contract that rejects selected candidates whose model-health state is failed or excluded.
- Added an executable Previous Install Context contract pack `previous-install-context-core` with QA and performance tests for canonical active runtime roots, archive-only previous install records, detached backup/migration context and legacy share-prefix rejection. Closed by `previous-install-context-core`.
- [x] Confirm previous installation backup/migration context is not active runtime. Closed by `previous-install-context-core`: active runtime roots are validated separately from previous-install, backup and migration records, which may exist only as archive or readonly evidence.
- Added an executable Pytest Suite Partition contract pack `pytest-suite-partition-core` with QA and performance tests: monolithic pytest is blocked in this container shape, pipeline-runtime tests are isolated into bounded shards, and targeted unittest shards carry per-shard timeouts. Closed by `pytest-suite-partition-core`.
- [x] Investigate full monolithic pytest hang around pipeline runtime suite in this container; targeted tests pass. Closed by `pytest-suite-partition-core`: release validation now uses bounded, deterministic pipeline-runtime shards instead of unbounded monolithic pytest in this container.
- Added an executable Backlog Status Legend contract pack `backlog-status-legend-core` with QA and performance tests: status legend lines are plain labels instead of Markdown task items, so `planned` is no longer counted as open work by active-tree scans. Closed by `backlog-status-legend-core`.
- [x] Normalize backlog status legend markers so they do not appear as open Markdown task items. Closed by `backlog-status-legend-core`: the roadmap legend now uses plain text labels and the scanner blocks task-list-shaped status legends.
- Added an executable Job Progress Stream contract pack `job-progress-stream-core` with QA and performance tests: `/api/jobs/stream` emits SSE snapshot/progress events and the dashboard consumes them through `EventSource` while retaining the JSON polling fallback. Closed by `job-progress-stream-core`.
- [x] Add streaming job progress SSE/WebSocket after alpha. Closed by `job-progress-stream-core`: the Admin GUI now exposes `/api/jobs/stream` as a deterministic SSE snapshot stream with `jobs_snapshot` and `job_progress` events.
- Added an executable Admin LLM Smalltalk contract pack `admin-llm-smalltalk-core` with QA and performance tests: casual Admin messages attempt the local LLM chat path when a socket is present, expose `conversation_backend`, and fall back deterministically while explicit control requests remain routed. Closed by `admin-llm-smalltalk-core`.
- [x] Add LLM-backed conversational Admin path for smalltalk while preserving deterministic control-plane routing. Closed by `admin-llm-smalltalk-core`: `AdminGuiServer` now reports `conversation_backend` as `llm_chat` or `deterministic_fallback` and keeps explicit control requests out of smalltalk.
- Added an executable Runtime Observer Cards contract pack `runtime-observer-cards-core` with QA and performance tests: `/api/runtime/observer-cards` and the dashboard Runtime card now show gateway/backend service and socket smoke affirmation cards. Closed by `runtime-observer-cards-core`.
- [x] Add live runtime observer cards for gateway/backend smoke affirmation. Closed by `runtime-observer-cards-core`: Runtime telemetry now includes `observer_cards` with `smoke_affirmation` states for gateway service/socket, main backend service/socket, model manifest and device policy.
- Added an executable Pipeline Drag/Drop Editor contract pack `pipeline-dragdrop-editor-core` with QA and performance tests: the Pipeline Dock now opens a draft-only stage editor with drag/drop reorder, add/remove controls and review-gated draft saves. Closed by `pipeline-dragdrop-editor-core`.
- [x] Add full drag&drop pipeline editor implementation after alpha. Closed by `pipeline-dragdrop-editor-core`: the Admin GUI now provides a `drag_drop_pipeline_editor` that edits stage order and writes `draft_only` pipeline drafts through `/api/pipelines/draft` without activating pipelines.
- Added an executable Public Showcase Guided Scenario contract pack `public-showcase-guided-scenario-core` with QA and performance tests: `/api/public-showcase/scenario` and the Admin GUI Public scenario card now select `polished_admin_gui_guided_scenario` as the reviewable public polish path without enabling live backend demos or packaging. Closed by `public-showcase-guided-scenario-core`.
- [x] Decide the public polish scenario. Closed by `public-showcase-guided-scenario-core`: the selected path is `polished_admin_gui_guided_scenario`, a deterministic Admin GUI guide over health, greeting, public pipeline, Dev Team planning and model-evolution review.
- Added an executable Runtime Default Safety contract pack `runtime-default-safety-core` with QA and performance tests for `max_active_llms=1`, manual-only heavy LLM boot, GUI `runtime_only`, woGUI CPU bootstrap and sequential team-member defaults.
- [x] Do not enable parallel heavy model runtime by default.
- [x] Do not auto-start heavy GPU LLM backends at boot.
- Added an executable Public Autonomy Boundary contract pack `public-autonomy-boundary-core` with QA and performance tests: Self-modification/autonomy is not public-ready; it is alpha/lab-only, approval-gated, and has no automatic apply.
- [x] Do not market self-modification/autonomy as public-ready.
- Added an executable Systemd Happy Path contract pack `systemd-happy-path-core` with QA and performance tests: No happy-path install or boot-mode flow requires hand-editing systemd units; use `noemaforge boot-mode` / setup wrappers and dry-run commands instead.
- [x] Do not require hand-editing systemd units in the happy path.
- Added an executable Machine-Local Defaults contract `machine-local-defaults-core` with QA and performance tests: `/etc/default/noemaforge-recovery`, `/etc/default/noemaforge-runtime` and `/etc/default/noemaforge-firstboot` examples are installed only if missing and are wired through optional systemd `EnvironmentFile` hooks.
- [x] Finalize `/etc/default/noemaforge-*` defaults for machine-local overrides.
- Added an executable Community Pack Contribution contract pack `community-pack-contribution-core` with QA and performance tests: Community-safe pack contributions are quarantine-first, manifest-backed, review-gated and never auto-activated.
- [x] Community-safe pack contribution path.
- Added an executable Admin/Surgeon/Scary Role Review State Machine contract pack `role-review-state-machine-core` with QA and performance tests: Admin/Surgeon/Scary review flows are explicit state machines with Scary risk gates, Surgeon repair proposals, Admin approvals and rollback-ready terminal states.
- [x] Admin/Surgeon/Scary role-flow runtime state machine.
- Added an executable Grounded Administrator contract pack `grounded-administrator-core` with QA and performance tests: Grounded Administrator is the default knowledge surface: Administrator answers query the hypergraph first, cite graph-backed provenance, and say unknown with ingest or research next steps when the graph cannot answer.
- [x] Grounded Administrator as the default knowledge surface.
- Added an executable Hypergraph-First Administrator contract pack `hypergraph-first-administrator-core` with QA and performance tests: Hypergraph-first Administrator answers query the hypergraph before any fallback: supported answers start from graph claim origins, include graph-backed citations, and only use docs/RAG fallback after an explicit graph miss.
- [x] Administrator answers must query the hypergraph first for grounded knowledge.
- Added an executable Graph Gap Notice contract pack `graph-gap-notice-core` with QA and performance tests: Graph-gap Administrator answers are explicit: when the hypergraph cannot answer, Administrator returns a knowledge_gap_notice, says local grounded knowledge cannot support the answer, proposes ingest or research next steps, and never improvises a supported claim.
- [x] If the graph cannot answer, the Administrator must say so explicitly and propose ingest/research, not improvise.
- Added an executable Topic-Adjacent Retrieval contract pack `topic-adjacent-retrieval-core` with QA and performance tests: Retrieval prefers topic-adjacent chunks over naive fixed windows: topic signature overlap and chapter/section locality choose the primary chunk, then adjacent support chunks are added only within budget.
- [x] Retrieval must prefer topic-adjacent chunks over naive fixed windows, using topic signature overlap plus locality within chapter/section.
- Added an executable Memory-Budgeted Retrieval contract pack `memory-budgeted-retrieval-core` with QA and performance tests: Memory-budgeted retrieval degrades gracefully: when a chunk chain exceeds active budget, NoemaForge selects highest-coherence subchunks first and adds adjacent support neighbors only if budget remains.
- [x] If a chunk chain is too large for the active memory budget, retrieval must degrade gracefully: first pull the highest-coherence subchunks, then add supporting neighbors only if budget remains.
- Added an executable Setup Mode Matrix contract pack `setup-mode-matrix-core` with QA and performance tests: Setup mode boundary: Linux host mode uses native services and local paths, macOS dev mode is non-privileged validation and light workflows, VM mode is the recommended no-risk onboarding path, and docker-dev is development/test only, not the full production NoemaForge path.
- [x] Support Linux/macOS dev mode and VM mode.
- Added an executable Onboarding Ladder contract pack `onboarding-ladder-core` with QA and performance tests: Onboarding ladder boundary: README.md is the 5-minute overview, docs/QUICKSTART_VM.md is the first-success VM path, docs/SETUP_MODES.md explains host/VM/docker-dev/macOS-dev differences, and docs/PRODUCTION_INSTALL_TRIXIE.md is only entered after quickstart validation; primary docs do not lead with Windows lab workflow.
- [x] Collapse docs into an onboarding ladder.
- Added an executable Knowledge Core Relations/Gates contract pack `knowledge-core-relations-gates-core` with QA and performance tests: Knowledge core relations boundary: Canonical knowledge relations are frozen as typed links among Source, Passage, Claim, Entity, Concept, Conflict, Trail, TaskContext, Decision and Artifact; publication gates for Passage, Claim, Conflict and Concept must emit auto_publish, review or quarantine decisions before retrieval can treat objects as published.
- [x] Lock the core relations and publication gates.
- Extended `graph-projection-views-core` with generated wiki_markdown/operator_summary/task_context/conflict_review artifacts and B3 acceptance checks.
- [x] Create graph projections instead of replacing the graph.
- Added launcher mount normalization so firstboot maps legacy `/mnt/brainos-share` operator paths to `/mnt/noemaforge-share` before Vault/model/dataset scanning.
- [x] Implement mount normalization to `/mnt/noemaforge-share` in the launcher happy path.
- Added firstboot scoring normalizer coverage so `model_inventory_normalize` filters non-head GGUF shards before role tournament eligibility, legacy firstboot scorecards and ModelStore staging.
- [x] Integrate normalizer directly into every firstboot scoring path.
- Added dataset assurance to the launcher happy path so `/opt/noemaforge/datasets/role_eval_cases` is checked or repaired before firstboot scoring starts.
- [x] Add dataset assurance to launcher happy path.
- Added automatic failed/invalid firstboot attempt archival so blocked, interrupted or malformed runs are copied into `firstboot-attempt-archive` before a new run resets live status/events.
- [x] Add automatic archival of failed/invalid firstboot attempts.
- Added launcher rerun/idempotency protection so active firstboot runs hold `firstboot-run.lock`, duplicate launches return `firstboot_already_running`, stale locks are recoverable, and terminal runs release the lease.
- [x] Make launcher fully rerunnable and idempotent on target hardware.
- Added an executable Cgroup-Aware Stop contract `cgroup-aware-stop-core` with QA and performance tests: stop/service-stop/llm-stop now discover systemd `ControlGroup`, drain `cgroup.procs`/`cgroup.threads` with TERM/KILL before legacy pkill fallback, and reboot-safe audits unit cgroups after stop.
- [x] Make stop/reboot-safe fully cgroup-aware.
- Added an executable Distro Remediation contract `distro-remediation-core` with QA and performance tests: `trixie-preflight` now emits distro/package-manager/missing-command remediation plans, guarded package apply gates, and first-launch uses distro-aware package lists for Debian, Fedora/RHEL, Arch and SUSE families.
- [x] Add distro detection and missing dependency remediation, not only detection.
- Added an executable llama-server launcher gate contract `llama-server-launcher-gate-core` with QA and performance tests: first-start and prepare-gui now run `validate_llama_server_runtime` before model discovery, block unresolved shared libraries from `ldd`, and preserve the read-only `trixie-preflight` checks.
- [x] Add `llama-server` binary/shared-library preflight and full launcher gate.
- Added an executable first-start abort recovery contract `first-start-abort-recovery-core` with QA and performance tests: `noemaforge first-start abort --dry-run` now provides a rootless offline regression path, and `noemaforge-gui-recover-minimal.sh --dry-run` avoids remount/loadkeys/bootstrap writes while preserving non-blocking GUI recovery commands.
- [x] Add automated regression for `noemaforge first-start abort` non-blocking GUI recovery.
- Added an executable Admin smalltalk route contract `admin-smalltalk-route-core` with QA and performance tests: Admin/GUI smalltalk is forced onto the `conversation` path, explicit control requests stay routable, and `public_mwp` is not launched by casual messages.
- [x] Verify Admin smalltalk uses the conversational path and does not launch `public_mwp`.
- Added an executable Vault re-inventory job contract `vault-reinventory-job-core` with QA and performance tests: `/api/vault/reinventory` returns a `needs_privilege` job, a typed privileged fallback command artifact and a GUI plan-only execution policy instead of silently failing.
- [x] Verify `Re-inventory Vault` returns a privileged job/fallback command instead of a silent failure.
- Added an executable Continue model selection idempotency contract `model-selection-continue-idempotency-core` with QA and performance tests: `/api/model-selection/continue` persists enriched `needs_privilege` job state, preserves display-safe dry-run commands, and returns the same active job after refresh/retry.
- [x] Verify `Continue model selection` uses job/idempotency state and does not duplicate active selection work after page refresh.
- Added an executable Model Selection vs Model Evolution distinction contract `model-route-distinction-core` with QA and performance tests: runtime routes, GUI endpoints, personas, artifact grouping and usecase help stay visually and semantically distinct.
- [x] Verify Model Selection and Model Evolution routing are visually and semantically distinct.
- Added an executable Admin task workflow contract `task-workflow-core` with QA and performance tests: task add/edit/prioritize/block/complete works through Admin chat and API, including explicit block/complete/prioritize endpoints.
- [x] Verify task add/edit/prioritize/block/complete through Admin chat and API.
- Added an executable CPU/GPU staged policy contract `runtime-device-policy-staging-core` with QA and performance tests: runtime device policy writes a pending staged setting and applies only on the next persona/model switch or backend restart, without migrating the active backend.
- [x] Verify CPU/GPU staged policy applies only on next persona/model switch or backend restart.
- Added an executable Default Model Runtime Policy contract `default-model-runtime-policy-core` with QA and performance tests: `runtime-device-policy.json` now selects `cpu_safe_always_on_with_gpu_on_demand`, keeps the default device CPU-safe, makes GPU an explicit staged on-demand path and preserves one active heavy worker.
- [x] Decide default always-on CPU-safe model policy vs GPU-on-demand policy.
- Added an executable CPU/GPU Scorecard Separation contract `cpu-gpu-scorecard-separation-core` with QA and performance tests: scorecard writers now accept a `runtime_device` and route explicit CPU/GPU records to `model_scorecards/cpu` and `model_scorecards/gpu`.
- [x] Record CPU and GPU scorecards separately.
- Added an executable Privileged GUI Job Runner contract `privileged-gui-job-runner-core` with QA and performance tests: GUI epoch apply now records a `polkit_approval_required` runner command, approval token and dry-run-first job artifact instead of leaving the browser with only a terminal sudo suggestion.
- [x] Convert GUI epoch apply request into privileged, polkit-mediated local action after safety review.
- Extended `privileged-gui-job-runner-core` to all currently approved privileged GUI job kinds: epoch apply, Continue model selection and Vault re-inventory now share the dry-run-first `polkit_approval_required` runner boundary, deterministic approval tokens and command/step allowlist validation.
- [x] Add polkit/root job-runner for approved privileged GUI jobs after alpha.
- 2026-05-20 heartbeat note: live NoemaForge validation and the full CPU/GPU canonical model matrix remain open because this local workspace has no target-machine services, NVIDIA/GDM state or live model-evaluation hardware. Selected the next safe local item instead.
- Added an executable Production GUI installer contract `production-gui-installer-core` with QA and performance tests. Production GUI installer boundary: setup, installer, delayed GUI systemd timer, Admin GUI dashboard assets, boot-mode CLI, recovery helpers and dry-run/root guards are validated together without touching a live host.
- [x] Production-grade GUI installer.
- Added an executable telemetry card truthfulness contract `telemetry-card-truthfulness-core` with QA and performance tests: telemetry cards show hardware, runtime and product metrics without overstating creative-media quality, using a review-required creative-media policy.
- [x] Verify telemetry cards show hardware, runtime and product metrics without overstating creative-media quality.
- Added an executable stateful Admin GUI install contract `stateful-admin-gui-core` with QA and performance tests: conversation restore, persona portrait, task queue, job panel, telemetry and pipeline dock hydrate through offline Admin GUI APIs after installation.
- [x] Validate stateful Admin GUI after installation: conversation restore, persona portrait, task queue, job panel, telemetry and pipeline dock.
- Added an executable artifact card affordance contract `artifact-card-affordance-core` with QA and performance tests: installed Admin GUI artifact cards expose guarded Open, Download and Copy path controls backed by local preview/download endpoints constrained to NoemaForge state roots.
- [x] Add download/open affordances for artifact cards on installed GUI.
- Added an executable dashboard API endpoint contract `dashboard-api-endpoint-core` with QA and performance tests: installed Admin GUI dashboards now prefer `/api/dashboard`, expose `/api/dashboard/state` as an alias and keep `/api/gui/state` as the compatibility fallback.
- [x] Add UI backend endpoint for dashboard.
- Added an executable locale main chat surface contract `locale-main-chat-surface-core` with QA and performance tests: `/api/locales` now carries required messages for installed locale packs and the Admin GUI main chat applies localized composer, depth-control, pipeline-dock, artifact-download and speaker labels without mixed RU/EN fallback text.
- [x] Confirm `/api/locales` returns messages and GUI does not show mixed RU/EN labels in the main chat surface. Closed by `locale-main-chat-surface-core`.
- Added an executable Dev backlog empty policy contract `dev-backlog-empty-core` with QA and performance tests: an empty Dev backlog creates a bounded seed self-optimization plan, not an auto-apply change.
- [x] Verify Dev backlog empty policy creates a bounded seed self-optimization plan, not an auto-apply change.

## Closed by this archive rebuild

- Markdown files were removed from disallowed documentation folders.
- Package docs root was reduced to `README.md`, `Manifest.md`, and `TODO.md`; the active project root is Markdown-free.
- Similar documentation fragments were merged into canonical grouped files.
- Retired naming and removed public-doc path references were scrubbed.


## 0.32.1 P0 display-safety update

This build hardens first-start/model-selection so local display output is preserved by default. Real model-selection no longer receives `--soft-headless` from the CLI wrapper. Any display-manager stop now requires an explicit operator opt-in flag: `--allow-display-stop` together with `--soft-headless`. GUI continuation jobs are plan/job-only by default and suggest `--dry-run --keep-display` commands first; real terminal commands also include `--keep-display`.

P0 acceptance targets:
- first-start keeps Debian GUI/display-manager running by default;
- model-selection and Continue model selection do not blank the monitor from GUI;
- Ctrl+C/abort and `sudo noemaforge first-start abort` remain recovery paths;
- headless/display stop is separate explicit opt-in behavior;
- epoch apply requests include `--keep-display`.

## NOEMAFORGE-PROP-production-ai-patterns-pack — integrated 2026-05-18

Status: architecture-integrated backlog pack. Runtime base: `0.32.1`; docs overlay: `0.32.1-docs-integrated`.

P0:
- [x] Add Unified Registry for model, prompt, retriever, reranker, tool-policy, pipeline, persona, task, epoch and eval-pack versions.
- [x] Add trace_id across Admin chat, GUI jobs, pipeline runs, model selection and tool calls.
- [x] Add EvaluationGate contract for code, prompt, model, RAG, pipeline and router changes.
- [x] Add Intent Router Eval Pack and per-route metrics.
- [x] Add safe rollout lifecycle for epoch, prompt and routing changes: shadow, canary, promote, rollback.
- [x] Add ReleaseEvidence artifact for every promoted change.
- [x] Add abstention policy: auto-route, ask clarification, defer to Admin/SR/SSR or block.

P1:
- [x] Add production RAG subsystem for docs/wiki/context with retrieval, reranking and citations.
- [x] Add RAG eval: retrieval hit rate, citation coverage, groundedness and answer helpfulness.
- [x] Add Model Card, Prompt Card, Pipeline Card, Epoch Card and Tool Policy Card.
- [x] Add data-centric error loop: classify errors, create regression tests, update docs/eval packs.
- [x] Add trajectory-level evaluation for agent loops.

P2:
- [x] Add GraphRAG experiment pack after classic RAG stabilizes.
- [x] Add MCP adapter registry under zero-trust policy.
- [x] Add A2A only as optional reviewed interoperability layer.
- [x] Add PEFT/LoRA lab only after evaluation and rollback gates mature.
