# TODO

## Optimizations

_Non-blocking improvements harvested from Codex CLI and CodeRabbit reviews. Each is optional; action when convenient. Source review tagged (e.g. `Codex #34`) for traceability._

- [ ] **Update each PR branch from `release/0.32.2-hardening` before merge.** PRs are checked as the head *merged with base*, so a branch behind release produces an inconsistent merged `SHA256SUMS` and fails the manifest/checksum-evidence step — a non-code, regen-fixable failure. Merge release in (or rebase) and regenerate checksums before merge. (Codex #37/#38)
- [ ] **Surface POSIX-rlimit unavailability in sandbox metadata.** On non-POSIX hosts `resource`/rlimits are absent and `sandbox.py` falls back to host execution; add an explicit meta flag (e.g. `rlimits_available: false`) to the sandbox run metadata so operators do not mistake the host fallback for resource-limited execution. (Codex #33)
- [ ] **Normalize `family`/`runtime` like `tags` in `composite_pair_scoring`.** They are compared raw, so `"Llama"` vs `"llama"` (case/whitespace) wrongly earns the diversity bonus; normalize (strip/lower) before comparing. (Codex #35)
- [ ] **`composite_pair_scoring._load_candidates()`: clearer validation errors** for non-object list entries instead of relying on `dict(item)` raising. (Codex #35)
- [ ] **`run_admin_gui.ps1`: fail loudly when `-PythonExe` is given but does not exist**, instead of silently falling back to the `py` launcher / `lib_python.ps1`. (Codex #36)
- [ ] **`role_tournament.py` backend-stop is still Linux/systemd-specific** (`systemctl(...)`); the `SIGKILL` guard only fixes the Windows attribute error, not a cross-platform stop flow — guard it or mark it target-only explicitly. (Codex #34)
- [ ] **DRY the `getattr(signal, "SIGKILL", signal.SIGTERM)` fallback** into a shared helper/constant if the pattern recurs beyond `discord_bridge.py`/`role_tournament.py`. (Codex #34)

## 0.33.0 Roadmap — Hermes-inspired (post-0.32.2)

_Forward-looking design/feature tasks for the 0.33.0 cycle; NOT in 0.32.2 scope. Design notes
and NoemaForge mappings: [reference/HERMES_INTEGRATION_ROADMAP_0.33.0.md](reference/HERMES_INTEGRATION_ROADMAP_0.33.0.md)._

- [ ] Add Hermes-style SKILL.md parser as quarantine-only import.
- [ ] Add SkillProposal schema with SSR/QA review status.
- [ ] Add session_search SQLite FTS5 over conversations, batons, artifacts and tool events.
- [ ] Add gateway-adapter architecture note based on single gateway process + allowlist/pairing.
- [ ] Add provider-runtime-resolver design doc.
- [ ] Add profile isolation contract for config/memory/sessions/gateway tokens.
- [ ] Add skill-bundle concept mapped to NoemaForge RolePack/WorkflowPack.
- [ ] Add marketplace import policy: inspect → quarantine → scan → Pipeline_RFC → epoch.
- [ ] Add Hermes benchmark cases to eval suite: memory recall, skill reuse, gateway command, cron delivery, safe tool denial.
- [ ] Add `noema upgrade` — proper version upgrade from GitHub (NOT first-run install): GitHub-native file fetch, with a fail-safe (download the release archive, replace files by extension/path) that by default never touches user/machine-changed state (`context.md`, config, memory, sessions, gateway tokens, data roots); dry-run diff + rollback; verify the signed manifest first. (see reference/ARCHITECTURE_LEGIBILITY_ROADMAP.md §A)
- [ ] Add version/file proposal back to GitHub (contribution path): open a PR via the GitHub API when a token is present; tokenless fallback = a portable signed proposal bundle (patch + provenance) via relay / "create PR" deep link, so a contributor without a GitHub account can still propose. (§B)
- [ ] Add collaborative-development readiness (architectural legibility layer): `CONTRIBUTING`/`CODE_OF_CONDUCT`/`SECURITY` + issue/PR templates; `docs/architecture/` index linked from README; ADRs; `control-plane.openapi.yaml`; ToolProxy capability-token schema + deny-by-default policy; `noema doctor` readiness matrix; generated capability/epoch catalog; CI `pr-gate`/`release-gate`. (research milestones 1–6; doc-layer in 0.32.2, code in 0.33.0)

## 0.33.x forward roadmap (added 2026-06-09)

_Forward-looking milestones and cross-cutting tasks requested for the 0.33.x cycle._

### Version milestones

- [ ] **0.33.1 — full system independence.** NoemaForge must run completely the same on
  *nix (Linux), macOS and Windows: parity for paths, service/process management, sockets,
  exec/sandbox, display-safety and the Admin GUI launcher across all three OS families
  (builds on the 0.32.2 `platform_paths` migration + sandbox/canary Windows import-safety).
  Acceptance: the artifact-driven AAT suite + the full test matrix pass identically on
  Linux / macOS / Windows.
- [ ] **0.33.2 — hybrid LLM usage.** Allow using external/hosted LLMs alongside local
  models: a provider-runtime resolver for the top ~10 LLMs (e.g. Codex/OpenAI,
  Claude/Anthropic, Gemini, Llama, Mistral, …) behind the ToolProxy capability token +
  deny-by-default policy, with per-provider credentials kept local, redaction-before-egress,
  cost/rate ceilings, and explicit operator opt-in (nothing leaves the machine by default).

### Cross-cutting tasks (any 0.33.x)

- [ ] **Hardening — non-engineer experience.** Harden the product for non-engineer
  operators: one-button install/run, plain-language errors with guided recovery, no
  terminal or YAML required for the happy path, GUI-first flows and safe defaults so a
  non-technical user cannot foot-gun the system.
- [ ] **Documentation & project WIKI rewrite.** Bring all docs and the GitHub WIKI up to
  date with the latest state (noema CLI, AAT suite, OpenSSF Scorecard, security/governance
  front page, scenario pack); rewrite stale pages; keep README v2 as the narrative landing.
- [ ] **PR review-comment fixups.** Systematically address actionable GitHub review
  comments (Codex / CodeRabbit / Copilot) on open PRs, fold recurring nits back into this
  TODO, and clear each PR's review thread before requesting merge.
- [ ] **More pro-active Copilot review usage.** Lean on GitHub Copilot review (and
  CodeRabbit) for routine review to reduce Codex token consumption — request Copilot as a
  reviewer on each `claude/*` PR; reserve Codex for higher-value / contested reviews.

## Accepted optimization decisions (2026-06-10 analysis review)

_The 2026-06-10 full-version analysis was reviewed and accepted by the owner. Each
decision below is a committed work item for the 0.33.x cycle (not an optional nit).
Restored 2026-06-11: this section was added by PR #82 but got lost in the #86
release→main conflict resolution; statuses updated on restore._

### A. Process / CI

- [x] **A1 — evidence generation moves to CI on dev branches.** Done (this PR):
  `ci/regen_evidence.py` is the single generator; the premerge gate regenerates
  and verifies the merged tree (stale-evidence failures abolished); the new
  `evidence-refresh.yml` workflow keeps committed copies current on `release/**`
  after merges. Branches no longer commit regenerated evidence.
- [x] **A2 — docs-hygiene gate joins premerge-quality.** Done in PR #85:
  pre-existing reds cleared (`context.md` legacy host name, CONTRIBUTING/SECURITY
  allowlist, three broken registry wiki refs) and the gate wired as step 11.
- [ ] **A3 — p0-status-ledger concurrency dedupe.** The workflow runs twice per
  push and the concurrency group cancels the older run, leaving misleading
  CANCELLED check entries; dedupe triggers or set `cancel-in-progress` with a
  per-ref group so only one run per push remains.
- [ ] **A4 — version-agnostic installer.** Replace per-release
  `install/uninstall_noemaforge_<ver>_mvp.sh` pairs with a single
  `install_noemaforge_mvp.sh` reading the VERSION SoT; archive the stale 0.32.1
  pair. Also closes the pre-existing red contract check
  `setup_does_not_delegate_to_current_installer` (no 0.33.0 installer exists).
- [ ] **A5 — refresh CLAUDE.md.** Working base is `release/0.33.0-dev`; drop the
  completed 0.32.2 P0 list and stale PR refs; point at the UAT defect register
  and the canonical TODO/roadmap as task sources; record the English-only
  GitHub-communication rule.

### B. Tree canonicalization (single source under the package root)

- [x] **B1 — systemd:** `noemaforge/systemd/` is the only unit tree; newer
  root-tree units merged in, root tree removed, installers/audit/boot-mode
  re-pointed, config refs verified against the contract resolvers. Done in
  PR #81 (and re-asserted in the #86 sync merge).
- [x] **B2 (wiki slice):** `noemaforge/docs/wiki/` is the canonical wiki; the
  drifted project-root mirror was removed, dumps extracted into standalone
  articles, hub + integrity gate + GitHub Wiki auto-publish added. Done in PR #80.
- [ ] **B2 (remaining docs):** merge the remaining drifted `docs/` ↔
  `noemaforge/docs/` pairs (i18n, architecture, reference, onboarding, …) into
  the package tree, make the project-root `docs/` a generated mirror or remove
  it, and re-point referencing paths in JSON/configs the same way as B1.

### C. Code health (refactor-as-you-touch; no big-bang)

- [ ] **Split `admin_gui_server.py` before the GUI fixpack grows it** (~2.2k
  lines, ~119 endpoint references in one handler): route table + modules per
  area (session, jobs, pipelines, model-selection). First slice of the fixpack.
- [ ] **Modularize the dashboard frontend** (`templates/pipeline-dashboard/app.js`)
  and add a small reusable card/progress/artifact component set — precondition
  for the raw-JSON-rendering defects (D-001/D-004/D-006).
- [ ] **Desktop app shell (accepted direction).** The GUI must feel like an
  application window, not a browser tab, via the lightest path: `noemaforge
  dashboard app` launcher using Chromium-family `--app=` mode with plain-browser
  fallback, plus a PWA manifest (`display: standalone`) for installability.
  Zero new mandatory dependencies; pywebview stays an optional future extra.
  ADR: `wiki/architecture/desktop-app-shell.md`.
- [ ] **Replace deprecated `datetime.utcnow()`** (8× in `caps.py`, then repo-wide)
  with timezone-aware `datetime.now(UTC)`; py3.12+ deprecates utcnow and CI on
  3.11 masks it.
- [ ] **Add a minimal `pyproject.toml`** (metadata + extras: `dev` = pytest/pyyaml,
  `vector` = numpy, `gateway` = httpx) without changing the stdlib-only runtime
  posture; tooling deps are currently undeclared anywhere.
- [ ] **Wire targeted contract-test shards into CI and burn down pre-existing
  reds.** premerge runs `py_compile` only, so contract tests rot silently:
  legacy refs to root `TODO.md`/`CHANGELOG.md`/`RELEASE_NOTES.md` in
  machine-local-defaults policy, stale installer delegation, and the
  `test_pr_release_artifacts` snapshot tests (hardcoded file counts) that fail
  on any live tree. Add bounded test shards to premerge/acceptance and fix the
  reds (make snapshot tests dynamic).
- [ ] **Nightly coverage run** (coverage.py over the bounded shards) to expose
  dead zones — src:test line ratio is ~3.4:1 with GUI/pipeline runtime suspected
  under-covered.

### E. Supply chain

- [ ] **Pin GitHub Actions to commit SHAs** (currently `@vN` tags) and enable
  Dependabot for `github-actions` updates; Scorecard already flags this.

## 0.32.2 target-host UAT findings → admin-gui-prod-readiness-fixpack (added 2026-06-10)

_Actionable fixes from the 2026-06-08/10 target-host UAT campaign. Defect IDs, severity
and acceptance criteria are canonical in `../uat/DEFECT-REGISTER-0.32.2.md`; per-run
detail in `../uat/UAT-*.md`. Verdict driving this section: Admin GUI =
PASS_WITH_MAJOR_UI_AND_ROUTING_DEFECTS, user-facing = PASS_WITH_MAJOR_USER_UX_AND_ROUTING_DEFECTS,
production readiness for non-engineer operators = NOT READY._

### P0 — trust and feedback loop (blocks operator use)

- [ ] **D-003** Deterministic glossary answers for known system states: Admin must explain
  `degraded_selected`, `selected=N` and other dashboard terms from a grounded glossary in
  the user's language — never hallucinate them as filenames.
- [ ] **U-002** No silent no-ops: every user command produces at least one visible
  response; async work shows accepted → running → status → result/failure with run id.
- [ ] **D-005** Pipeline confirm OK inserts the generated request into the chat input
  (editable, with visible confirmation); Cancel only closes the dialog.
- [ ] **D-007** Visible pipeline run progress: per-run panel with current stage
  highlighted, completed stages marked, errors with stage + short message, run id linked
  to artifacts/logs (text-only is acceptable for MVP).
- [ ] **U-001/U-005** Deliver artifacts into chat: render the artifact metadata the API
  already returns (`path`, `open_url`, `preview_url`, `download_url`, `open_command`) as
  result cards with open/download/copy actions; readable failure message on error.

### P1 — comprehension and persona UX

- [ ] **D-002** Operator-readable epoch/model-selection panel: clear labels, tooltips for
  state terms, full model names on hover, internally consistent progress numbers, and a
  "Latest plan" that reflects the actually applied run (no stale `normal` after a real
  `full_composite`).
- [ ] **U-003** Distinct personas with an explicit selector: observably different
  behavior/tone/scope per persona, switch logged in chat, completion offers
  stay / return-to-Admin / switch.
- [ ] **D-009** Pipeline persona greeting: every pipeline declares a default persona; on
  launch the chat shows the switch and the persona greets with next steps.
- [ ] **D-008** Iteration controls visibly attach to the next message/job (send-button
  label change + "next message runs as N-step cycle" notice + iteration progress), or are
  disabled with a warning where unsupported.

### P2 — presentation polish and guards

- [ ] **D-001** Hardware card: RAM/Swap bars or gauges in human units (GiB, percent); raw
  JSON only behind Details/Debug.
- [ ] **D-004** Product metrics card: grouped labeled rows (selected model, selection
  status, score, pass rate, JSON parse rate, quality score, avg latency, failed tasks);
  no raw JSON in the default view.
- [ ] **D-006** Render the pipeline diagram as a visual stage graph (readable fallback +
  error if rendering fails; source behind debug).
- [ ] **D-010** Repeat-launch guard: launching the same pipeline again within a short
  interval prompts start-new / continue-existing / cancel; existing runs visible.

### Runtime / ops follow-ups (0.33.x)

- [ ] **R-001** Root-cause the one-off `noemaforge-llm-backends-manager.service` failure
  observed during the composite first-start window (plan-only oneshot; `reset-failed` was
  applied on host but is not a fix); add a regression check.
- [ ] **S-001** Make the shipped ops smoke liveness-oriented: health ok + non-empty model
  reply = live; keep the literal-`OK` expectation as an optional strict mode so a healthy
  tiny instruct model is not reported `degraded`.
- [ ] **U-004** All-pipeline AAT/demo mode (GUI tier of the AAT suite): one control runs
  every available pipeline in safe test mode with small built-in prompts and exports a
  summary report (pipeline, case, status, artifact, error, duration, persona); failures
  do not stop the batch by default.
- [ ] **O-001/O-002** UAT/ops helper polish: model-selection key-scan summary must extract
  real values (or be replaced by the normalized-verdict extraction); fix unit-name and
  path quoting in evidence-collection helpers.
- [ ] **O-003** Document the Admin GUI default posture (no TCP listener until the operator
  starts the localhost dashboard) in the operator guide.

## 0.32.2 release-hardening checkpoints

- 2026-05-30: Docs hygiene now has an executable forbidden-active-text gate.
  Active release docs and evidence use neutral target-host wording instead of
  legacy host-specific names, and `docs_hygiene_runtime.py` fails if those
  forbidden strings reappear outside project trash.

- 2026-05-30: Three new task branches pushed, all with clean single-concern
  three-dot diffs against `release/0.32.2-hardening`:
  - `claude/task-13-config-validate-api` (3 files): adds ConfigValidator +
    `/api/config/validate` endpoint to AdminGuiServer. 17 tests pass.
  - `claude/task-14-fix-double-append` (1 file): fixes duplicate
    `session_store.append_message()` call in `save_message()`. The duplicate
    write caused `test_session_mode_history.py` to report 2× messages per
    save call and a 250-message bound instead of 500. 13 tests pass.
  - `claude/task-11-wire-preflight` and `claude/task-12-json-yaml-validator`
    force-pushed from clean branches (fix/task-11-clean and fix/task-12-clean)
    to eliminate CI workflow noise in three-dot diffs. 210 + 31 tests pass.

- 2026-05-29: Admin GUI job path-safety refactor completed on
  `release/0.32.2-hardening`. `AdminGuiServer` now uses centralized
  `job_file()` and `job_cancel_marker_file()` helpers for per-job JSON and
  `.cancel` sentinel paths, preserving the existing `safe_id()` path-safety
  contract across create, persist, get and cancel paths. Added a focused
  regression test proving unsafe job IDs cannot write cancel markers outside
  `jobs_dir`. Validation run: `py -3 -m unittest
  noemaforge/tests/test_admin_gui_session_event_wiring.py` (34 tests),
  `py -3` compileall for `noemaforge/src`, and `git diff --check`. Claude
  review is required because this touches Admin GUI job/cancel behavior and
  path-safety semantics; see
  `noemaforge/docs/quality/CLAUDE_REVIEW_QUEUE_0.32.2.md`.

- 2026-05-29: PR #12 / `claude/task-10-startup-preflight` processed from
  the open PR queue. CodeRabbit left only an autogenerated summary comment;
  blocking/actionable review comments observed via public API: 0. GitHub
  `validate-claude-push` succeeded, but `codex-review` returned FAIL on commit
  `fa2b15be68a2bd5a0b64ddabd89f257a100be845`. Local Codex checks on the
  current PR head passed: `py -3` compileall,
  `py -3 -m unittest noemaforge/tests/test_startup_preflight.py` (30 tests),
  and `git diff --check`. The Codex FAIL text appears inconsistent with the
  current PR diff (`/api/events` is not present on the checked head), but the
  branch carries CI workflow changes unrelated to startup preflight. Treat this
  as not merge-ready until Claude reviews the safety/CI scope and Codex is
  re-run; see `noemaforge/docs/quality/CLAUDE_REVIEW_QUEUE_0.32.2.md`.

- 2026-05-29: PR #11 / `claude/task-9-job-heartbeat` processed from the
  open PR queue. CodeRabbit left only an autogenerated summary comment;
  blocking/actionable review comments observed via public API: 0. GitHub
  `validate-claude-push` succeeded, but `codex-review` returned FAIL on commit
  `d2232a6d79eb08e3884781dd15015a1e0d7c10ba`. Local Codex checks on the
  current PR head passed: `py -3` compileall,
  `py -3 -m unittest noemaforge/tests/test_job_heartbeat_and_process_runner.py`
  (24 tests), and `git diff --check`. The Codex FAIL text appears inconsistent
  with the current PR diff (`/api/events` is not present on the checked head),
  but the branch carries CI workflow changes unrelated to heartbeat/process
  runner work. Treat this as not merge-ready until Claude reviews the mixed
  scope and Codex is re-run; see
  `noemaforge/docs/quality/CLAUDE_REVIEW_QUEUE_0.32.2.md`.

- 2026-05-29: PR #10 / `claude/task-8-admin-chat-routing` processed from
  the open PR queue. CodeRabbit left only an autogenerated summary comment;
  blocking/actionable review comments observed via public API: 0. GitHub
  `validate-claude-push` succeeded, but `codex-review` returned FAIL on commit
  `b0a8cb389184284c21cc799a465328eeadd1f3fc`. Local Codex checks on the
  current PR head passed: `py -3` compileall,
  `py -3 -m unittest noemaforge/tests/test_admin_chat_routing.py` (26 tests),
  and `git diff --check`. The Codex FAIL text appears inconsistent with the
  current PR diff (`/api/events` is not present on the checked head), but the
  branch also carries CI workflow changes unrelated to chat routing. Treat this
  as not merge-ready until Claude reviews the mixed scope and Codex is re-run;
  see `noemaforge/docs/quality/CLAUDE_REVIEW_QUEUE_0.32.2.md`.

- 2026-05-29: PR #9 / `claude/task-7-wire-job-manager` processed from
  the open PR queue. CodeRabbit left only an autogenerated summary comment;
  blocking/actionable review comments observed via public API: 0. GitHub
  quality gate and `validate-claude-push` succeeded, but `codex-review`
  returned FAIL on commit `970b5267deea27240e37b735e2fa5a9c8cb51f54`.
  Local Codex reproduction confirmed the blocker:
  `py -3 -m unittest noemaforge/tests/test_admin_gui_job_manager_wiring.py`
  ran 27 tests with 5 `NameError: data is not defined` errors in
  `AdminGuiServer.jobs_list()`. `py -3` compileall and `git diff --check`
  passed. This is a return to Claude, not a merge-ready branch; see
  `noemaforge/docs/quality/CLAUDE_REVIEW_QUEUE_0.32.2.md`.

- 2026-05-29: PR #8 / `claude/task-6-version-centralization` processed from
  the open PR queue. CodeRabbit left only an autogenerated summary comment;
  blocking/actionable review comments observed via public API: 0. GitHub
  `validate-claude-push` failed before Codex review on a broad
  `RUNTIME_VERSION =` grep hit in docs/tests, so `codex-review` was skipped.
  Local Codex checks on the PR head passed: `py -3` compileall,
  `py -3 -m unittest noemaforge/tests/test_job_manager.py` (48 tests), and
  `git diff --check`. Claude review is required before merge because this
  touches JobManager/orchestration; see
  `noemaforge/docs/quality/CLAUDE_REVIEW_QUEUE_0.32.2.md`.

- 2026-05-28: `release/0.32.2-hardening` hygiene batch selected first open
  Windows-accessible P0 item. `.gitignore` now ignores Python caches,
  bytecode, test/lint caches and build outputs; tracked `__pycache__`/`.pyc`
  files were checked before the change and none were tracked. Claude review:
  not needed for this hygiene-only batch. Validation run: `py -3` compileall
  passed with an existing `return`-in-`finally` warning in `noemaforge_core.py`;
  `git diff --check`, `git status --short`, and tracked cache checks passed.

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

## 0.32.2 P0/P1 gaps — identified 2026-05-28

### P0-B — docs/release.json active fields (Windows-doable)

- [x] Fix `docs/release.json`: set `release`, `package`, `release_name`, `channel`, `status`, `summary`, `version_audit`, `generated_at`, `updated_at` to 0.32.2. — Done 2026-05-28 in claude/task-15-frontend-event-polling.

### P0-C — Windows premerge audit script (Windows-doable)

- [x] Create `noemaforge/tools/prep/noemaforge-premerge-check.ps1`: Windows-native premerge audit covering VERSION files, `docs/release.json` active fields, no RUNTIME_VERSION= outside `noemaforge_version.py`, `py_compile` 286 src/*.py, JSON parse 169 configs, YAML parse 70 configs, no tracked `__pycache__`. 13/13 PASS (2026-05-28).

### P0-G — CI workflow (not yet created)

- [x] Create `.github/workflows/premerge-quality.yml`: CI workflow on PRs to `release/0.32.2-hardening` and `main`. 8 steps: py_compile, no RUNTIME_VERSION= leak, VERSION files, docs/release.json fields, JSON parse, YAML parse, no tracked __pycache__, bash -n. `permissions: contents: read`. No auto-commits (2026-05-28).

### P1 — safety review of autonomous workflow files (audit only)

- [x] Safety review of autonomous workflow files — created `noemaforge/docs/quality/AUTONOMOUS_WORKFLOW_SAFETY_REVIEW_0.32.2.md` (2026-05-28). Findings: `autonomous-pipeline-v2.yml` has CRITICAL `--approval-mode auto-edit` risk; `qa-version-bump.yml` pushes directly to release branch (HIGH); batch-counter auto-triggers version bump without human approval (HIGH). All three untracked workflows need fixes before enabling. See review doc for required operator actions.

### P1 — PR #2 reviewability (manual action)

- [ ] Add to PR #2 description: functional review base `v0.32.1-prelaunch...release/0.32.2-hardening`, list of actual 0.32.2 changed files grouped by area (runtime/helpers/docs/configs), and a summary of what a reviewer needs to check vs what is legacy/historical. (Requires GitHub web UI or `gh` CLI — do via web.)

## 0.32.2 hardening — second deep analysis cycle (2026-05-30)

Eight new proposals from cross-cutting analysis of completed tasks 13–19.
All are Windows-doable.

- [x] **task-20 (HIGH): Add threading.Lock on shared file read-modify-write in
  AdminGuiServer** — Added `self._state_lock = threading.Lock()` and wrapped
  the R-M-W sections of `_upsert_job()`, `_persist_job()`, `job_cancel()`, and
  `save_message()`. Done in `claude/task-20-state-lock` (9 tests including
  concurrent-create stress test with 20 threads). All passing.

- [x] **task-21 (HIGH): Cap `conversation-current.json` to MAX_CONVERSATION_MESSAGES**
  — `save_message()` appends to `conv["messages"]` with no upper bound (unlike
  `session_store` which has a 500-message cap). Long-running sessions produce
  multi-MB files that are fully re-read and re-written on every request.
  Fix: add `MAX_CONVERSATION_MESSAGES = 1000` slice in `_save_conversation()`.
  DONE: `claude/task-21-conversation-cap` — 13 tests passing (747334d).

- [x] **task-22 (HIGH): Confirm/re-fix save_message() double append_message call**
  — Audit the task-14 fix is correctly applied (the double-write bug sends two
  calls to `session_store.append_message()` per `save_message()`, doubling the
  message count and halving the 500-message window). Verify tests pass on
  `release/0.32.2-hardening` after task-14 merges.
  DONE: `claude/task-22-fix-double-append` — removed slim-dict call, 10 tests passing (75d23d2).

- [x] **task-23 (MEDIUM): Add `_write_json` atomic tmp-rename pattern**
  — `_write_json` calls `path.write_text()` directly; a crash or concurrent
  read during the write will observe a truncated/partial JSON file. Fix: adopt
  the same tmp-then-rename approach already used by `SessionStore._write_atomic()`.
  DONE: `claude/task-23-atomic-write-json` — thread-unique tmp names, 12 tests passing (6e94a1e).

- [x] **task-24 (MEDIUM): Clamp `/api/events` limit parameter to prevent DoS**
  — `?limit=1000000` causes `EventLog.read()` to build a million-entry list in
  memory before responding. Fix: `limit = min(max(1, limit), 1000)` in
  `do_GET` before calling `events_api()`.
  DONE: `claude/task-24-clamp-events-limit` — clamp + stub fix + 8 new clamp tests, 20 total (ca5b0a4).

- [x] **task-25 (MEDIUM): Add EventLog rotation/size cap**
  — `EventLog.append()` opens the JSONL file in `"a"` mode indefinitely; after
  weeks of uptime the file can be tens of thousands of lines loaded entirely into
  memory per request. Fix: add a rotation threshold (10 000 lines or 10 MB).
  DONE: `claude/task-25-eventlog-rotation` — `_maybe_rotate()` + 19 tests (612714d).

- [x] **task-26 (MEDIUM): Cap `session_id` query param length to prevent proliferation**
  — `GET /api/session/current?session_id=<10k-chars>` creates a new session file
  for any novel sanitized id, enabling unbounded session-file growth. Fix: clamp
  to 128 characters in `do_GET` and return 400 for all-non-alphanumeric values.
  DONE: `claude/task-26-cap-session-id` — [:128] clamp + alphanumeric guard + 16 tests (8a7165d).

- [x] **task-27 (MEDIUM): Surface `noemaforge_core.py` exception in role output load**
  — Around line 2118, a `return None` in a finally-equivalent path silently
  swallows any exception from `_load_json(out_path)`. Callers receive
  `(None, runner_out)` with no indication of why output parsing failed.
  Fix: log the exception or add it to the return tuple as a structured field.
  DONE: `claude/task-27-surface-core-exception` — `_write_event("S2", "ROLE_OUTPUT_PARSE_FAILED")` in except block, 7 tests (3db19bf).

- [x] **task-34 (HIGH): SessionStore threading.Lock + thread-unique _write_atomic**
  DONE: `claude/task-34-sessionstore-lock` — Lock on update()/append_message() + thread-unique tmp names, 14 tests (48b3cdf).

## 0.32.2 hardening — deep code-review cycle (2026-05-30)

High-effort three-angle code review on `claude/task-13-config-validate-api`
(config_validator.py + /api/config/validate wiring). Six candidates surfaced;
four fixed in commit `5d9961b` on the same branch:

- [x] **CONFIRMED-HIGH fixed**: `scan()` returned `ok=True` with `files_checked=0`
  when the root directory did not exist. Now returns `ok=False` with an explicit
  error describing the missing path.

- [x] **CONFIRMED-MEDIUM fixed**: `validate_json_file` and `validate_yaml_file`
  used `errors='replace'` before parsing, silently repairing invalid UTF-8 byte
  sequences and reporting corrupt files as valid. Changed to `errors='strict'`.

- [x] **CONFIRMED-MEDIUM**: `ValidationReport` now includes a `yaml_skipped: bool`
  field exposed via `to_dict()` so consumers can distinguish a passing scan from
  one where PyYAML was absent and YAML files were never parsed.

- [x] **PLAUSIBLE-LOW fixed**: `report.get("ok", True)` → `report.get("ok", False)`
  in `config_validate_api()` — wrong default would silently promote a missing key
  to success instead of failure.

- **REFUTED**: mid-iteration OSError in `_iter_files` — Python's `Path.rglob()`
  handles per-directory PermissionError internally; the outer `try/except` is
  redundant but harmless.

New open items from this review (both absorbed into task-13 branch):

- [x] **task-17: Rate-limit / cache `/api/config/validate`** — Added 60-second
  TTL cache with `threading.Lock` (prevents cache stampede) in
  `config_validate_api()`. Committed in `fb3ecfa` on
  `claude/task-13-config-validate-api`. 22 tests pass.

- [x] **task-18: Surface `yaml_skipped=True` in Admin GUI health badge** — Added
  "Config validation" card to the right sidebar in index.html with a status pill;
  `refreshConfigValidate()` in app.js shows `⚠ yaml skipped` pill-warn when
  `yaml_skipped=true`, `✗ N errors` pill-error with first-three error paths, or
  `✓ ok (N files)` pill-ok. Polled on startup and every 5 minutes. Committed in
  `656d00d` on `claude/task-13-config-validate-api`. 27 tests pass.

## 0.32.2 hardening — new proposals (2026-05-30)

Windows-doable items derived from deep analysis of task-11/12/13/14 work:

- [x] Wire ConfigValidator into AdminGuiServer as `/api/config/validate` endpoint.
  Done in `claude/task-13-config-validate-api` (17 tests pass).

- [x] Fix duplicate `session_store.append_message()` call in `save_message()`.
  Done in `claude/task-14-fix-double-append` (13 tests pass). Root cause:
  `save_message()` called `append_message` twice, doubling session message
  count and halving the effective 500-message window.

- [ ] **Add `JobManager.prune_terminal(max_age_seconds=86400)`** to prevent
  unbounded growth of the job index. Blocked until task-11
  (`claude/task-11-wire-preflight`) merges to release.

- [x] **Add idempotency integration test for `/api/model-selection/continue`**
  Done in `claude/task-15-idempotency-test` (13 tests pass). Covers:
  model_selection_continue repeated calls return same job_id, vault_reinventory
  idempotency, needs_privilege status, polkit policy, --keep-display in command.
  Note: job_id uses second-precision timestamps so sub-second uniqueness is
  tracked separately in task-16.

- [ ] **Add `_run_preflight()` exception reporting mode** — currently any
  exception in PreflightSuite is silently swallowed and returns None.
  Add a `_preflight_warning` field to `/api/health` output when preflight
  raises. Blocked until task-10/11 merge.

Target-host required items:

- [ ] **SHA256SUMS regeneration** after all PR branches merge.
- [x] **Verify `noemaforge-premerge-check.ps1` catches SHA256SUMS staleness** —
  Added Check 9 to `noemaforge-premerge-check.ps1`: reads SHA256SUMS and
  verifies every `noemaforge/src/*.py` has an entry. Done in
  `claude/task-19-sha256sums-premerge-check` (8 tests: 5 source-text + 3
  functional pwsh subprocess). The check currently flags 4 files added during
  0.32.2 hardening that are absent from SHA256SUMS and need regeneration on
  the target host: `event_log.py`, `noemaforge_version.py`,
  `orchestration_state.py`, `session_store.py`.

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
- [x] Jobs panel: added Cancel button (✕) for cancellable jobs; `cancelJob()` calls POST /api/jobs/{id}/cancel then refreshes the panel (2026-05-28).
- [x] Stale version metadata bumped to 0.32.2: release.json, docs/release.json, noemaforge.runtime.yaml, quantization-policy.yaml (3 copies), model_capabilities.py heuristic tag.
- [x] 244 stale alpha/0.29.x files removed from git tree (moved to trash/).
- [x] Docs versions bumped: noemaforge/docs/README.md, noemaforge/docs/Manifest.md → 0.32.2.

## 0.32.2 hardening — third deep analysis cycle (2026-05-30)

Third-cycle deep review of tasks 21–27 (conversation cap, double-append, atomic write,
events-limit clamp, EventLog rotation, session_id cap, noemaforge_core exception surface).
Ten findings — 9 new Windows-doable tasks (28–36) proposed below.

- [x] **task-28 (HIGH): Fix EventLog `_maybe_rotate()` TOCTOU race and per-append full-file read**
  DONE: `claude/task-28-eventlog-lock` — `threading.Lock` + double-checked re-stat inside
  lock + `_append_count % _ROTATION_CHECK_INTERVAL` throttle; 21 tests pass (fcba7a0).

- [x] **task-29 (HIGH): Validate `session_id` in POST `/api/session/mode` body**
  DONE: `claude/task-29-mode-session-id-validation` — [:128] clamp + alphanumeric guard
  in do_POST; removed dead duplicate block; 16 tests pass (38f78f3).

- [x] **task-30 (MEDIUM): Log session_store failures instead of silent pass in save_message()**
  DONE: `claude/task-30-log-session-store-errors` — `except Exception as _ss_exc` +
  `event_log.append("gui.session_store_error", ...)` + inner guard; 11 tests pass (62075c3).

- [x] **task-31 (MEDIUM): Clean up orphaned `.{tid}.tmp` files on AdminGuiServer startup**
  DONE: `claude/task-31-cleanup-tmp-files` — `_cleanup_stale_tmp_files()` added; scans
  gui_state_dir/jobs_dir/sessions with `glob("**/*.tmp")`; 13 tests pass (20062af).

- [x] **task-32 (MEDIUM): Stream EventLog.read() instead of loading entire file into RAM**
  DONE: `claude/task-32-stream-eventlog-read` — `path.open()` iteration with early
  `break`; OSError guard added; 14 tests pass (6a1d859).

- [x] **task-33 (LOW): Avoid in-place mutation of conv dict in `_save_conversation()`**
  DONE: `claude/task-33-conv-no-mutation` — `conv = dict(conv)` shallow copy before
  stamping updated_at; 5 tests pass (628a3da).

- [x] **task-34 (HIGH): Add threading.Lock to SessionStore to prevent message-loss race**
  DONE: `claude/task-34-sessionstore-lock` — Lock on update()/append_message() +
  thread-unique tmp names, 14 tests (48b3cdf).

- [x] **task-35 (LOW): Add comment explaining clamp handles negative limit values**
  DONE: `claude/task-35-36-minor-fixes` — comment + `min(max(1, limit), 1000)` clamp
  added to /api/events do_GET; 9 tests pass.

- [x] **task-36 (MEDIUM): Wrap `_write_event()` call in except block in noemaforge_core.py**
  DONE: `claude/task-35-36-minor-fixes` — nested try/except guards `_write_event()`
  inside `_load_json` except block; ROLE_OUTPUT_PARSE_FAILED event + inner guard;
  7 source-text tests pass (24336d1).

## 0.32.2 hardening — fourth deep analysis cycle (2026-05-30)

High-effort three-angle code review of tasks 28–36 (EventLog lock/rotation,
session_id validation, session_store error logging, tmp cleanup, streaming read,
conv mutation guard, limit clamp comment, _write_event guard).
Four findings — 4 new Windows-doable tasks (37–40) proposed below.

- [x] **task-37 (HIGH): Fix `append()`-outside-lock vs `_maybe_rotate()`-rename race**
  DONE: `claude/task-37-eventlog-append-lock` — entire append + rotation cycle now
  under `self._lock`; eliminates archive-pollution race (Linux) and PermissionError
  race (Windows); incorporates task-28 Lock/throttle and task-32 streaming-read
  improvements; 23 tests pass (574e10b).

- [x] **task-38 (MEDIUM): Fix combined task-32 + task-28 Windows handle-vs-rename race**
  DONE: `claude/task-38-read-rotate-windows` — `_maybe_rotate()` now uses
  copy-then-truncate (`archive.write_bytes(content)` + `path.open("r+b").truncate(0)`)
  instead of `path.replace()` (MoveFileEx); readers with an open handle hit EOF at
  truncation instead of causing PermissionError; 16 tests pass (2815756).

- [x] **task-39 (LOW): Narrow `_cleanup_stale_tmp_files()` glob pattern**
  DONE: `claude/task-39-narrow-tmp-glob` — added module-level
  `_STALE_TMP_RE = re.compile(r'\.\d+\.tmp$')` and filters every glob hit through
  the regex before unlinking; plain `.tmp` files are preserved; 10 tests pass (a1b55bc).

- [x] **task-40 (LOW): Fix falsy `session_id` substitution in POST `/api/session/mode`**
  DONE: `claude/task-40-session-id-falsy` — replaced `or "default"` with explicit
  `is not None` guard; added `[:128]` clamp and `composite_top_n` 400-error;
  removed dead unreachable duplicate block; switched to `session_set_mode` interface;
  10 tests pass (b3922d2).

## 0.32.2 hardening — fifth deep analysis cycle (2026-05-30)

High-effort three-angle review of tasks 37–40 (append-lock, copy-truncate rotation,
glob narrowing, session_id falsy fix). Three confirmed/plausible findings.

- [x] **task-41 (HIGH): Fix `_maybe_rotate()` archive overwrite**
  DONE: `claude/task-41-archive-rotate` — added `_shift_archives()` that shifts
  `.1`→`.2`→`.3` before each rotation, dropping the oldest generation beyond
  `_MAX_ARCHIVE_DEPTH=3`; copy-then-truncate retained; lock and throttle included;
  13 tests pass (65b7958).

- [x] **task-42 (MEDIUM): Remove duplicate SessionStore init in AdminGuiServer.__init__**
  DONE: `claude/task-42-session-store-init` — removed the two early discarded
  assignments (`gui_state_dir/sessions`, early `event_log`); kept only the single
  correct `data_root/sessions` and `data_root/events` assignments after the
  mkdir loop; 7 tests pass (0f3af2a).

- [x] **task-43 (LOW): Document `_cleanup_stale_tmp_files()` coverage gap until task-23 merges**
  DONE: `claude/task-43-cleanup-tmp-comment` — added detailed docstring explaining
  that gui/jobs dir scans are forward-looking (become active after task-23 atomic
  write merges) while sessions scan is already active via task-34 `_write_atomic()`;
  absorbed task-39 narrow-regex fix; 10 tests pass (de45b2b).

## 0.32.2 hardening — sixth deep analysis cycle (2026-05-30)

High-effort three-angle review of tasks 41–43 (archive-shift rotation,
duplicate-init removal, cleanup-tmp comment). Three surviving findings.

- [x] **task-44 (HIGH): Fix `_STALE_TMP_RE` pattern — does not match current `_write_atomic` output**
  DONE: `claude/task-44-stale-tmp-regex` — changed pattern from
  `r"\.\d+\.tmp$"` (requires digits, never matched `default.json.tmp`) to
  `r"\.json(\.\d+)?\.tmp$"` (matches both pre-task-34 `{sid}.json.tmp` and
  post-task-34 `{sid}.json.{tid}.tmp` while rejecting unrelated `.tmp` files);
  16 tests pass (c7db340).

- [x] **task-45 (MEDIUM): `_shift_archives()` must abort on partial failure to prevent data loss**
  DONE: `claude/task-45-shift-archives-abort` — `_shift_archives()` now returns
  `True`/`False` instead of `None`; `_maybe_rotate()` skips archive write and
  truncate when it receives `False`, preserving both existing archives and live
  file data; also incorporated task-37/38/41 improvements (Lock, copy-truncate,
  generation shift, streaming read); 12 tests pass (272071e).

- [x] **task-46 (LOW): Document `read()` after-rotation blind spot for `after_index` callers**
  DONE: `claude/task-46-read-generation` — added `_rotation_count` counter
  (incremented once per successful truncation in `_maybe_rotate()`), exposed via
  new `status()` method returning `rotation_count/current_size_bytes/path`;
  documented reset-on-rotation polling pattern in class/read/status docstrings
  with code example; 16 tests pass (bccdf2f).

## 0.32.2 hardening — seventh deep analysis cycle (2026-05-30)

High-effort three-angle review of tasks 44–46 (regex fix, abort-on-shift-failure,
rotation_count/status). Three confirmed findings.

- [x] **task-47 (HIGH): Include `rotation_count` in `/api/events` response + reset in `pollEvents()`**
  `events_api()` returns `{ok, events, count}` but does NOT include
  `EventLog.status()["rotation_count"]`. The browser's `pollEvents()` advances
  `lastEventIndex` but has no way to detect when the live file was truncated to 0.
  After a rotation, every subsequent `GET /api/events?after_index=N` returns
  `{count: 0}` — indistinguishable from "no new events" — until the log
  re-grows past line N. Fix: add `"rotation_count": self.event_log.status()["rotation_count"]`
  to `events_api()` return dict; add `let lastRotationCount = 0` tracking in app.js
  `pollEvents()` and reset `lastEventIndex = 0` when `rotation_count` changes.
  Done: implemented on claude/task-47-events-rotation-count (8fc4bf2) and
  superseded by task-50 which adds both rotation_count AND server_epoch.

- [x] **task-48 (LOW): Fix misleading lock-consistency comment in `EventLog.status()`**
  The comment in `status()` says "to ensure consistency between the two counters"
  but `current_size_bytes` is captured OUTSIDE `self._lock` while only
  `_rotation_count` is captured inside. A caller can receive `rotation_count=1`
  (post-rotation) alongside `current_size_bytes=10485760` (pre-rotation). Fix:
  update the comment to state the lock only protects `_rotation_count`; update the
  docstring to explicitly note `current_size_bytes` is a best-effort sample and may
  not be consistent with `rotation_count` in a single call.
  Done: fixed on claude/task-48-status-comment (7154b45); status() docstring now
  explicitly states "May not be consistent with rotation_count."

- [x] **task-49 (LOW): Document non-OSError half-rotation risk in `_maybe_rotate()` docstring**
  `_maybe_rotate()` uses `except OSError: pass`. A `KeyboardInterrupt` or
  `SystemExit` raised between `archive.write_bytes(content)` (archive written) and
  `fh.truncate(0)` (live file not yet cleared) leaves both the live file and the
  `.1` archive containing the same content. On subsequent startup/rotation,
  `_shift_archives()` moves that archive to `.2`, and the next rotation writes a
  new `.1` with the same data again. Over several such events, archive slots fill
  with duplicate copies of the live data, consuming up to `_MAX_ARCHIVE_DEPTH ×
  MAX_EVENT_BYTES` (30 MB) of disk space. Fix: narrow the `except OSError` guard
  to wrap only step A (`archive.write_bytes`) and step B (`fh.truncate`) with
  separate try/except blocks, using `BaseException` for the outer guard or
  adding a plain comment explaining why `KeyboardInterrupt` is an accepted risk
  in this path.
  Done: expanded `_maybe_rotate()` docstring to document KeyboardInterrupt/SystemExit
  risk, intentional narrowness of `except OSError`, and accepted duplicate-archive
  scenario. 11 tests in `test_rotate_interrupt_doc.py` pass (bea0aca,
  claude/task-49-rotate-interrupt-doc).

## 0.32.2 hardening — eighth deep analysis cycle (2026-05-31)

Tasks 44-49 completed (sixth and seventh cycles): stale-tmp regex,
_shift_archives() abort-on-failure, EventLog.status()/rotation_count,
rotation_count in /api/events + pollEvents() reset, status() comment
correction, _maybe_rotate() half-rotation docstring.

Deep review found three new Windows-accessible improvements:

### Finding 1 — Server-restart missed-event bug (HIGH)

`_rotation_count` is an in-process counter: it resets to 0 every time the
server restarts.  `pollEvents()` detects rotation by checking
`r.rotation_count !== lastRotationCount`.  If no rotation had occurred
before the restart, `lastRotationCount` is 0 and `r.rotation_count` is also
0 after restart → the browser sees no change, keeps its old `lastEventIndex`
(say 1000), and `read(after_index=1000)` returns `[]` for a freshly-started
empty log.  New events are silently skipped until the file grows past line
1000, which may never happen.

Fix: add a `server_epoch` field (UUID4 hex, generated at `EventLog.__init__`
time) to `status()` and include it in `/api/events`.  Browser tracks
`lastServerEpoch`; any mismatch → `lastEventIndex = 0` + update.

- [x] **task-50 (HIGH): Add `server_epoch` to `EventLog.status()` and `/api/events`
  to fix missed-event bug after server restart**
  In `EventLog.__init__`: `self._server_epoch = uuid.uuid4().hex[:16]`.
  In `status()`: add `"server_epoch": self._server_epoch`.
  In `events_api()` (admin_gui_server.py): include `server_epoch` from
  `status()` in the response dict.
  In `app.js` `pollEvents()`: add `let lastServerEpoch = null;` and reset
  `lastEventIndex = 0` + update `lastServerEpoch` when `r.server_epoch !==
  lastServerEpoch`.
  Tests: `test_eventlog_server_epoch.py` (epoch stable within process,
  different across instances, present in status() dict, triggers reset in
  pollEvents simulation).
  Done: 13 tests pass; events_api() returns server_epoch + rotation_count;
  app.js resets lastEventIndex on epoch or rotation_count change (620f5db,
  claude/task-50-server-epoch).

### Finding 2 — Dead `hasattr` guard in `events_api()` (LOW)

`events_api()` (task-47 branch) uses `if hasattr(self.event_log, "status"):
try: rotation_count = int(self.event_log.status()...)` as a defensive
fallback.  Since `EventLog` always has `status()`, this guard is dead code
that adds visual noise and an extra try/except nesting level.

- [x] **task-51 (LOW): Remove dead `hasattr(self.event_log, "status")` guard
  in `events_api()`**
  Replace the three-level defensive block with a direct call:
  `rotation_count = int(self.event_log.status().get("rotation_count", 0))`.
  Wrap the whole body in one `except Exception` for consistency with the
  existing error path.
  Tests: update `test_events_api_rotation_count.py` to assert no `hasattr`
  call is made (source inspection); verify the simplified path in unit test.
  Done: absorbed into task-50 — events_api() on claude/task-50-server-epoch
  was written without hasattr guard from the start; direct st = self.event_log.status()
  call used throughout. No separate commit needed.

### Finding 3 — Threshold constants not exported from `event_log` (LOW)

`__all__` in `event_log.py` includes `EventLog`, `DEFAULT_EVENT_STATE`,
`_MAX_ARCHIVE_DEPTH` (private) but NOT `MAX_EVENT_LINES` or `MAX_EVENT_BYTES`
(the public rotation thresholds).  Tests in `test_eventlog_shift_abort.py`
and `test_eventlog_rotation_count.py` hardcode `10_000` and `10 * 1024 *
1024` instead of importing the constants, making them brittle if thresholds
change.

- [x] **task-52 (LOW): Add `MAX_EVENT_LINES` and `MAX_EVENT_BYTES` to
  `event_log.__all__` and update tests to import them**
  One-line change to `__all__` in `event_log.py`.
  Update affected test files to `from event_log import MAX_EVENT_LINES,
  MAX_EVENT_BYTES` instead of hardcoding values.
  Tests: verify `from event_log import MAX_EVENT_LINES, MAX_EVENT_BYTES`
  works in a stub-installed environment (add to test_rotate_interrupt_doc or
  a new focused file).
  Done: __all__ updated to include MAX_EVENT_LINES and MAX_EVENT_BYTES;
  import verified in stub environment (claude/task-50-server-epoch).

## 0.32.2 hardening — ninth deep analysis cycle (2026-05-31)

High-effort review of tasks 50-52 (server_epoch, hasattr cleanup, __all__ exports).
Six candidate findings; three confirmed/plausible and fixed.

- [x] **task-53 (MEDIUM): Remove duplicate EventLog/SessionStore init in AdminGuiServer.__init__**
  Second init at lines 631-632 used `data_root/sessions` (wrong path, differs from
  DEFAULT_SESSION_STATE=`.../gui/sessions`) and created a fresh EventLog with a new
  server_epoch mid-init. Removed duplicate assignments; kept correct first init
  (lines 620-621) using `gui_state_dir/sessions`.
  Done: 4 source-guard tests pass; py_compile OK (cb668ec).

- [x] **task-54 (MEDIUM): Fix pollEvents() stale-events processing after rotation/restart**
  After resetting `lastEventIndex=0` on epoch/rotation change, the function
  continued processing `r.events` from the stale poll (fetched with the OLD
  after_index). If the new log already had >N lines when rotation was detected,
  events 0..N-1 would be permanently skipped.
  Fix: added `return` immediately after the reset in both branches.
  Done: 3 source-guard tests pass; node --check OK (cb668ec).

- [x] **task-55 (LOW): Guard status() call in events_api() to preserve events on failure**
  Previously one try block covered both read() and status(); a status() failure
  discarded already-fetched events and returned ok=false with empty events.
  Fix: two separate try blocks — read() failure returns ok=false; status()
  failure returns ok=true with fetched events and safe defaults.
  Done: 3 tests pass (source inspection + behavioural) (cb668ec).

## 0.32.2 hardening — tenth deep analysis cycle (2026-05-31)

Review of ninth-cycle fixes (double-init, stale-events return, events_api split).
Five candidate findings; three confirmed and fixed.

- [x] **task-56 (LOW): Add server_epoch/rotation_count shape assertions to events_api tests**
  Test stubs for events_api() only checked `{ok, events, count}`; removing
  server_epoch or rotation_count from the real method would pass silently.
  Done: 4 source-guard tests in test_session_store_thread_safety.py verify
  both fields appear in ok AND error return paths (72597f4).

- [x] **task-57 (MEDIUM): Fix empty-string server_epoch trap in app.js pollEvents()**
  First-poll assignment `lastServerEpoch = r.server_epoch || null` coerced ""
  (returned by events_api error path) to null, keeping lastServerEpoch=null
  permanently and making restart-detection always false.
  Fix: `if(lastServerEpoch === null && r.server_epoch) lastServerEpoch = r.server_epoch`
  — only adopts truthy (non-empty) epoch values. 3 source-guard tests pass (72597f4).

- [x] **task-58 (HIGH): Add threading.RLock() to SessionStore**
  ThreadingHTTPServer dispatches concurrent request threads; concurrent
  `append_message()`/`update()` calls shared `_append_event()` which used bare
  open("a") without any lock, risking interleaved JSONL writes.
  Fix: self._lock = threading.RLock(); acquired at top of load(), save(),
  `update()`, `append_message()`. Reentrant so update→load→save chain does not
  deadlock. 6 tests including concurrent-write JSONL validation all pass (72597f4).

## 0.32.2 hardening — eleventh deep analysis cycle (2026-05-31)

Review of tenth-cycle fixes (SessionStore RLock, empty-epoch guard, test shape).
Four candidate findings; one real improvement actioned.

- [x] **task-59 (LOW): Add session-count assertion to concurrent-write test**
  test_concurrent_append_message_no_corruption() only checked JSONL format;
  a lost-update regression would pass silently. Added final session load +
  len(messages) == 80 assertion (955fe5e).

## 0.32.2 hardening — twelfth deep analysis cycle (2026-05-31)

Broad review of admin_gui_server.py beyond event_log/session_store.
Five findings; one confirmed and fixed, others refuted or low-priority.

- Path traversal via fallback-avatar path: REFUTED — safe_id().strip("-._")
  converts ".." → "" → default "item"; no literal separator survives.
- /api/shutdown without auth: accepted design — local-only 127.0.0.1 service.
- _append_jsonl() race: low risk — concurrent admin GUI calls are rare.
- _serve_static() without per-handler try/except: outer do_GET catch-all covers it.

- [x] **task-60 (MEDIUM): Make _write_json() atomic via tmp-then-replace**
  `path.write_text(json_dumps(obj))` writes directly — a concurrent reader
  could see a half-written file (partial JSON). Fix: write to `.tmp` then
  `tmp.replace(path)`, matching SessionStore._write_atomic() pattern.
  Added OSError cleanup (tmp.unlink) on failure to prevent tmp-file leaks.
  7 tests in test_write_json_atomic.py pass (consistency with SessionStore
  and event_log patterns verified) (see current commit).

## 0.32.2 hardening — thirteenth deep analysis cycle (2026-05-31)

Broad coverage scan: identified zero-coverage paths in SessionStore and
admin_gui_server. Two gaps found: SessionStore.events() had no tests, and
_serve_static() parent-dir boundary had no tests.

- [x] **task-61 (MEDIUM): Add test coverage for SessionStore.events() read-back path**
  `SessionStore.events()` — the JSONL read-back method feeding `/api/events`
  polling and SSE — had zero test coverage. Any regression (missing index field,
  broken after_index filter, malformed-line crash) would pass silently.
  14 tests in `test_session_store_events.py` cover: empty file returns [],
  index field injection, after_index pagination (0/N/9999), limit truncation,
  malformed JSON skipped without crash, empty lines skipped, and event-type
  verification (session.created / session.updated / session.message).
  14/14 pass; ResourceWarning (unclosed file) fixed before commit (954df64).

- [x] **task-62 (MEDIUM): Add test coverage for AdminGuiHandler._serve_static()**
  `_serve_static()` — the static asset dispatch path — had zero test coverage.
  Key behaviors now verified: api/ prefix returns 404 JSON without filesystem
  access; ui/ path traversal (../../etc/passwd) is blocked by parent-containment
  guard and returns 404; ui/ non-existent and directory paths return 404; valid
  ui/ file served with correct bytes; general path traversal falls back to
  index.html (SPA safe default, no data exposure); URL-encoded traversal
  (%2e%2e) also falls back; empty/root path serves index.html; content-type
  detection for CSS and PNG verified.
  14 tests in `test_serve_static.py`; 14/14 pass (1df64a1).

## 0.32.2 hardening — fourteenth deep analysis cycle (2026-05-31)

Coverage scan of admin_gui_server.py found two dead-code bugs:
1. `session_current()` defined twice — second definition (line ~1105) silently
   overrides the first (line ~802); first had no try/except and hardcoded "default"
   with no session_id param.
2. `POST /api/session/mode` handled twice in `do_POST` — the second handler
   (after /api/vault/reinventory) was unreachable because the first already
   `return`s; dead handler also lacked composite_top_n validation.

- [x] **task-63 (HIGH): Remove dead session_current() overload and duplicate
  POST /api/session/mode handler from admin_gui_server.py**
  Removed 4-line dead `session_current(self)` method (no session_id, no
  try/except) that was always shadowed by the 6-line version at line ~1105.
  Removed 6-line unreachable second `POST /api/session/mode` handler in
  do_POST (called session_set_mode() without composite_top_n validation).
  Updated `test_session_current_api.py`: changed stale zero-arg check
  `session_current()` to `session_current(session_id)` (the real call).
  Added 7 source-guard tests in `test_dead_code_removal.py`.
  All directly-related tests pass; test_session_mode_history.py has 3 pre-
  existing failures unrelated to this change (double-append regression in
  the unmerged branch state). py_compile clean (580ec78).

- [x] **task-64 (MEDIUM): Unit tests for safe_id() and resolve_artifact_path()**
  `safe_id()` is used for ALL path construction (job files, avatar paths,
  artifact names). A regression allowing '..' or '/' would re-introduce
  path traversal in every caller. 13 safe_id tests cover: normal input
  unchanged, slashes replaced, '..' → "item" (default), traversal seq
  sanitized, empty/whitespace → default, all-special → default, 96-char
  truncation, custom default parameter.
  `resolve_artifact_path()` enforces containment in allowed roots (security
  critical). 9 tests cover: empty rejected, tilde rejected, relative rejected,
  outside-roots rejected, traversal via '..' rejected, nonexistent rejected,
  valid file accepted with size, valid directory accepted with is_dir=True.
  22/22 pass; py_compile clean (15aa488).

- [x] **task-65 (MEDIUM): Add OSError cleanup to SessionStore._write_atomic()**
  `_write_atomic()` used no try/except — if `tmp.replace(path)` failed, the
  `.tmp` file was left behind (disk full, permissions, Windows lock). Multiple
  failed writes would accumulate orphaned `.tmp` files.
  Fix: wrap the write+replace in try/except OSError; unlink the tmp file on
  failure (matching the pattern already enforced in AdminGuiServer._write_json()
  since task-60). Added `test_session_store_cleans_up_tmp_on_error` guard to
  test_write_json_atomic.py `TestWriteJsonConsistency`.
  8 write_json_atomic tests + 35 total session-store tests all pass; py_compile clean.

- [x] **task-66 (MEDIUM): Direct unit tests for _session_path(), set_mode(),
  attach_active_jobs() in SessionStore**
  20 tests in `test_session_store_sanitization.py` covering path sanitization
  (_session_path: normal/default/traversal/slash/long/empty/None, plus
  functional load tests), mode validation (set_mode: normal/fast/full/
  full_composite accepted; 6 invalid modes fall back to "normal"; composite_top_n
  persisted/defaults), and active-job filtering (attach_active_jobs: dict items
  persisted, non-dict filtered out, empty list clears jobs).
  20/20 pass; py_compile clean (cf083ba).

## 0.32.2 hardening — fifteenth deep analysis cycle (2026-05-31)

Cross-cutting review of tasks 61-66 (events() test coverage, _serve_static()
tests, dead-code removal, safe_id/resolve_artifact_path tests, _write_atomic
OSError cleanup, _session_path/set_mode/attach_active_jobs tests).
Four findings — all Windows-doable and fixed in commit 7c1b86d.

### Finding 1 — do_GET missing outer try/except (MEDIUM)

`do_POST` wraps all handler dispatch in `try/except Exception` → JSON 500.
`do_GET` had NO such wrapper: any uncaught exception in a GET handler (e.g.
`self.server.health()` raising) propagated to `BaseHTTPRequestHandler.
handle_one_request()`, which logged the traceback but closed the connection
without sending any HTTP response. Clients received a connection reset instead
of a structured error.

Fix: wrap the entire do_GET dispatch body in `try: ... except Exception as exc:
self._send_json({"ok": False, "error": repr(exc)}, status=500)` — matching the
do_POST pattern exactly.

- [x] **task-67 (MEDIUM): Add outer try/except to do_GET matching do_POST pattern**
  6 source-guard tests in `test_do_get_safety.py` verify: outer try: block
  present, except Exception block present, 500 status in except, "error" field
  in 500 response, safety-net comment present, do_POST safety net still present.
  py_compile clean; 12/12 new tests pass (7c1b86d).

### Finding 2 — /api/events limit unclamped in do_GET (LOW)

`?limit=999999` was parsed and passed unclamped to `events_api()` → `EventLog.
read()`. File bounded by `MAX_EVENT_LINES=10 000` but a 10 000-row JSON
response is still ~3 MB per poll. Task-24 clamp existed on a separate unmerged
branch; current branch never had it.

Fix: `limit = min(max(1, limit), 1000)` after parsing, with comment explaining
DoS rationale. Clamp also prevents `?limit=0` or negative values from yielding
zero or unbounded results.

- [x] **task-68 (LOW): Clamp ?limit= in /api/events to [1, 1000]**
  6 source-guard tests in `test_do_get_safety.py` verify: clamp expression
  present, applied before events_api() call, upper bound 1000, lower bound 1,
  comment explaining rationale, limit reassigned. 12/12 new tests pass (7c1b86d).

### Finding 3 — normalize_session_record() raises ValueError on non-numeric fields (MEDIUM)

`int(record.get("selected_composite_top_n") or 0)` raises ValueError when the
value is a non-numeric string (e.g. "abc"). This is because `"abc" or 0` == `"abc"`
(truthy), so `int("abc")` raises. `load()` catches this via `except Exception:
pass` and silently recreates the session from scratch — losing all session
history. Same issue affected `last_event_index`.

Fix: introduced `_safe_int(value, default=0)` helper in orchestration_state.py
that returns `default` on any TypeError/ValueError; replaced both `int(... or 0)`
calls with `_safe_int(...)` in `normalize_session_record()`.

- [x] **task-69 (MEDIUM): Fix normalize_session_record() ValueError on non-numeric
  selected_composite_top_n / last_event_index**
  `_safe_int()` introduced; both fields now use it. 7 _safe_int tests + 14
  normalize_session_record tests in `test_orchestration_state.py` (39 total)
  include explicit "abc" and None inputs that previously would have caused
  silent session loss. 39/39 pass; py_compile clean (7c1b86d).

### Finding 4 — orchestration_state functions had zero direct test coverage (LOW)

`nowz()`, `normalize_session_record()`, `normalize_job_record()`, `is_active_job()`
and `_safe_int()` were covered only via stubs in other test files. The real
implementations could regress silently.

- [x] **task-70 (LOW): Direct unit tests for all orchestration_state public functions**
  39 tests in `test_orchestration_state.py` cover all 5 functions (nowz: 5 tests,
  _safe_int: 7 tests, normalize_session_record: 14 tests, normalize_job_record:
  8 tests, is_active_job: 5 tests). 39/39 pass (7c1b86d).

## 0.32.2 hardening — sixteenth deep analysis cycle (2026-05-31)

High-effort three-angle review of tasks 67-70 (do_GET safety wrapper, events
limit clamp, safe int fix, orchestration_state direct tests). Five findings;
two MEDIUM fixed, three LOW noted below.

- [x] **task-71 (MEDIUM): Fix _safe_int() NaN/Inf fast-path raises**
  `_safe_int`'s `isinstance(value, (int, float))` branch called `int(value)` bare:
  `int(float('nan'))` raises ValueError and `int(float('inf'))` raises OverflowError.
  Both were outside the `try/except` block, breaking the "always return default"
  contract. Fix: wrapped the isinstance branch in `try/except (ValueError, OverflowError)`.
  3 new NaN/Inf tests (42 total in test_orchestration_state.py); py_compile clean (aebbc44).

- [x] **task-72 (MEDIUM): Guard do_GET and do_POST safety-net except with inner try/except**
  If `wfile.write()` already failed (BrokenPipeError on client disconnect mid-stream),
  the outer safety-net `except Exception` fired and tried `_send_json({"ok": False, ...})`
  on the same dead socket — raising a second BrokenPipeError that propagated to
  `process_request_thread()` and logged a spurious unhandled error. Fix: both do_GET
  and do_POST safety-net blocks now wrap `_send_json(...)` in `try: ... except Exception: pass`.
  3 new source-guard tests (15 total in test_do_get_safety.py); py_compile clean (aebbc44).

### LOW findings (deferred, not yet fixed):

- **Asymmetric validation (LOW)**: `after_index < 0` returns HTTP 400; `limit <= 0` is
  silently clamped to 1. Minor API contract inconsistency, no crash risk. Noted.

- **Three duplicate _safe_int implementations (LOW)**: `lsp_facade.py`, `mcp_router.py`,
  `orchestration_state.py` each define their own `_safe_int` with different default
  parameter signatures. Not a runtime bug; refactoring would reduce maintenance burden.

- **normalize_job_record dead code (LOW)**: Defined in orchestration_state.py but never
  imported from any production source. `jobs_list()` returns raw job dicts via `dict(job)`
  without normalization — jobs created through the normal API path are well-formed, so
  this is defence-in-depth gap, not a crash. Task-73 would wire it into jobs_list().

## 0.32.2 hardening — seventeenth deep analysis cycle (2026-06-01)

High-effort review of tasks 73-76 (final-state guard in job_cancel, _jobs_lock,
session_id clamp, needs_privilege in ACTIVE_JOB_STATES). Commit 5ea49db.
19/19 tests pass in test_job_state_machine.py; all four session suites green.

Four new findings — all Windows-doable:

### Finding 1 — jobs_list() reads jobs_data() without holding _jobs_lock (MEDIUM)

`jobs_list()` calls `self.jobs_data()` (which reads `jobs.json`) without
acquiring `self._jobs_lock`. Meanwhile `_upsert_job()`, `_persist_job()` and
`job_cancel()` all write `jobs.json` inside the lock. A concurrent GET
`/api/jobs` request can read a partially-overwritten file if a tmp-then-replace
write races with the JSONL parse. The atomic `_write_json()` (tmp-rename) makes
a partial-JSON read unlikely, but the read is still outside the lock intent.
Fix: wrap `jobs_data()` call in `jobs_list()` with `with self._jobs_lock:` to
make the read-then-copy operation consistent with the write callers.

- [x] **task-77 (MEDIUM): Acquire _jobs_lock in jobs_list() for consistent read**
  Wrap the `jobs_data()` call and the subsequent list comprehension in
  `jobs_list()` inside `with self._jobs_lock:`. Add a source-guard test
  verifying `_jobs_lock` appears in the `jobs_list` method body.
  Done: 4 lock source-guard tests + session_store-sync-outside comment guard;
  15/15 in test_jobs_list_lock_normalize.py (8566a81).

### Finding 2 — job_cancel() writes cancel marker OUTSIDE _jobs_lock (LOW)

After the `with self._jobs_lock:` block closes, `job_cancel()` calls
`self._write_json(self.job_file(jid), target)` and
`marker.write_text(now_iso())` without re-acquiring the lock. A second
concurrent call to `job_cancel()` on the same job could interleave between
the status update (inside lock) and the marker write (outside lock). The
status update is atomic (lock-guarded), but the marker sentinel could be
written twice, which is idempotent. Risk is LOW (benign double-write), but
inconsistent with the stated lock semantics.
No fix required; document the intentional out-of-lock marker write with a
comment explaining the double-write is safe (sentinel is idempotent).

- [x] **task-78 (LOW): Document out-of-lock cancel marker write in job_cancel()**
  Add a one-line comment above the `self.job_file()` / `marker.write_text()`
  calls explaining they are intentionally outside `_jobs_lock` because the
  marker write is idempotent and the status is already committed under lock.
  Done: multi-line comment added explaining idempotency + atomic tmp-replace;
  3 source-guard tests pass (8566a81).

### Finding 3 — normalize_job_record() still dead code; jobs_list() returns raw dicts (LOW)

`normalize_job_record()` was added to orchestration_state.py (task-76 cycle) but
`jobs_list()` still returns `dict(job)` (shallow copy of the raw stored dict).
If a job was created by an older code path missing a key (e.g. `"artifacts"`,
`"progress"`), the frontend receives `undefined` fields. Using
`normalize_job_record(job)` in `jobs_list()` would guarantee all fields are
present with safe defaults.

- [x] **task-79 (LOW): Wire normalize_job_record() into jobs_list() return path**
  In `jobs_list()`, replace `dict(job)` with
  `normalize_job_record(dict(job))` (import already present from
  orchestration_state). Add a source-guard test verifying `normalize_job_record`
  is called inside the `jobs_list` method body.
  Done: 3 source-guard tests + 5 behavioural tests (minimal job gets all schema
  fields, progress defaults to dict, full job preserved); 15/15 (8566a81).

### Finding 4 — Three duplicate _safe_int implementations (LOW, deferred from cycle 16)

`lsp_facade.py`, `mcp_router.py`, and `orchestration_state.py` each define
their own `_safe_int` with slightly different default-parameter signatures.
The canonical version is in `orchestration_state.py` (covers NaN/Inf,
tested at 42 assertions). The others lack NaN/Inf coverage.
Risk: LOW — none are on the same hot path. Windows-doable refactor.

- [x] **task-80 (LOW): Deduplicate _safe_int — import from orchestration_state**
  Remove `_safe_int` from `lsp_facade.py` and `mcp_router.py`; add
  `from orchestration_state import _safe_int` (or promote it to a shared
  `utils.py`). Add import-verification source-guard tests for both files.
  Note: orchestration_state imports must not create a circular dependency;
  verify import graph before applying.
  Done: no circular dependency (lsp_facade/mcp_router don't import orch_state);
  13 source-guard + functional tests pass (plugin_runner also deduplicated as part
  of task-86). Commit 14e7670 / cd827fe.

## 0.32.2 hardening — eighteenth deep analysis cycle (2026-06-01)

High-effort three-angle review of tasks 77-80 (jobs_list lock, job_cancel
out-of-lock comment, normalize_job_record in jobs_list, _safe_int dedup).
Eight findings identified; six fixed as tasks 81-86.

- [x] **task-81 (MEDIUM): Fix save_message() double append_message() call**
  Two calls to session_store.append_message() per message: slim dict at line ~866
  and full msg dict inside try/except at ~881. Sessions accumulated 2× entries,
  halving the 500-message cap. Removed the slim-dict call; kept the try/except
  wrapped full-msg call. 3 source-guard tests; py_compile clean (cd827fe).

- [x] **task-82/85 (MEDIUM): Acquire _jobs_lock in job_get() + apply normalize_job_record()**
  job_get() read jobs_data() without _jobs_lock, racing with concurrent writes.
  Also returned raw job dicts, diverging schema from jobs_list(). Fixed: wrapped
  read inside with self._jobs_lock:; applied normalize_job_record() +
  enrich_artifact_cards(). 4 source-guard + 2 behavioural tests (cd827fe).

- [x] **task-83 (MEDIUM): Normalize job_cancel() return dicts**
  Both return paths (FINAL_JOB_STATES early return, success/not-found) returned
  raw job dicts. Frontend could receive undefined for progress/lock_key/version.
  Fixed: both paths now call normalize_job_record() + enrich_artifact_cards().
  2 source-guard + 2 behavioural tests (cd827fe).

- [x] **task-84 (LOW): Guard _write_json in job_cancel() against not-found**
  _write_json(self.jobs_file(), data) executed unconditionally inside _jobs_lock
  even when no matching job_id was found (no-op write while holding the lock).
  Fixed: added 'if target is not None:' guard. 2 source-guard + 1 behavioural
  (mtime unchanged for not-found) tests pass (cd827fe).

- [x] **task-86 (LOW): plugin_runner._safe_int dedup**
  plugin_runner.py had the same local _safe_int as lsp_facade/mcp_router
  (missed in task-80). Removed local def + autodoc header; added import from
  orchestration_state. 2 new source-guard tests in test_safe_int_dedup.py
  (13 total); py_compile clean (cd827fe).

### Remaining findings from this cycle (deferred as new tasks):

- [x] **task-87 (LOW)**: _read_json() swallows all exceptions silently including
  json.JSONDecodeError from corrupt files. Operator gets no log output; next
  _upsert_job() overwrites jobs.json with empty list. Fix: add sys.stderr.write
  warning inside the except block to surface corruption without re-raising.
  Done: 3 source-guard + 3 behavioural tests; py_compile clean (2106cd9).

- [x] **task-88 (LOW)**: normalize_job_record() sets progress to {"current":0,"total":0,
  "label":"queued"} only when progress is not a dict. If progress IS a dict but
  missing internal keys (e.g. {"current": 5}), normalize_job_record returns it
  as-is. Frontend code that accesses progress.label receives undefined.
  Fix: add normalize_job_progress() helper ensuring all three sub-keys exist.
  Done: normalize_job_progress() in orchestration_state.py; normalize_job_record()
  delegates to it; 8 functional + 2 source-guard tests pass (2106cd9).

## 0.32.2 hardening — nineteenth deep analysis cycle (2026-06-01)

Targeted review of remaining gaps after tasks 77-88 (jobs_list lock, per-job
normalize, job_cancel normalize/write-guard, save_message dedup, job_get lock,
_read_json stderr, normalize_job_progress). Five findings; four MEDIUM fixed.

- [x] **task-89 (MEDIUM): Remove double session.saved event from session_store.save()**
  save() emitted 'session.saved' then each caller (update/append_message) emitted
  its own semantic event — every GUI action wrote 2 events to session-events.jsonl,
  doubling the log size and making after_index polling unreliable.
  Fixed: save() is now a pure persistence helper; callers retain their events.
  4 source-guard tests + 157 total tests green (5306b2b).

- [x] **task-90 (MEDIUM): _upsert_job() and _persist_job() write normalized per-job files**
  Per-job .json files were written with raw job dicts — missing fields like
  lock_key, finished_at, version that normalize_job_record() would add.
  Fixed: both methods now call normalize_job_record(dict(job)) for the per-job
  file write so job_get() always reads a schema-complete record.
  3 source-guard tests; all regression suites green (5306b2b).

- [x] **task-91 (MEDIUM): Add _tasks_lock to task_create() and task_update()**
  Both methods did tasks_data() + _write_json() without a lock — concurrent
  POST /api/tasks requests could silently overwrite each other's tasks.
  Fixed: self._tasks_lock = threading.Lock() in __init__; both methods acquire it.
  6 source-guard tests (5306b2b).

- [x] **task-92 (LOW): Initialize norm_target before 'if target:' in job_cancel()**
  norm_target was only defined inside 'if target:' but used in the ternary on the
  return line. Runtime-safe due to ternary short-circuit, but fragile under refactor.
  Fixed: norm_target: Dict[str, Any] = {} initialized before the if block.
  2 source-guard tests (5306b2b).

### Remaining findings from nineteenth cycle (deferred as new tasks):

- [x] **task-93 (LOW)**: `_append_event()` in session_store.py documented "Caller must
  hold self._lock" but did not enforce this contract. A future developer adding a
  new call outside the lock would create a JSONL race silently.
  Fix: `_append_event()` now acquires self._lock internally (RLock, so callers
  already holding it re-enter without deadlock). No caller changes needed.
  20/20 session_store_sanitization tests pass; py_compile clean.

## 0.32.2 hardening — twentieth deep analysis cycle (2026-06-01)

Final Windows-accessible hardening scan. Two concurrency gaps found in paths
not yet locked. Both fixed.

- [x] **task-94 (MEDIUM): tasks_list() acquires _tasks_lock for consistent reads**
  tasks_list() called tasks_data() without _tasks_lock, racing with concurrent
  task_create()/task_update() writes. Fixed: wrapped in 'with self._tasks_lock:'
  (same pattern as jobs_list/_jobs_lock from task-77).
  3 source-guard tests; py_compile clean (5b57adb).

- [x] **task-95 (MEDIUM): save_message() acquires _conv_lock for conversation R-M-W**
  Two concurrent request threads calling save_message() could both read
  conversation-current.json, both append a message, and the last writer would
  overwrite the other's entry. Fixed: self._conv_lock = threading.Lock() added
  to __init__; save_message() acquires it around _conversation() + _save_conversation().
  Lock order documented: _tasks_lock → _conv_lock (task_create holds _tasks_lock
  first, then calls save_message — never reversed, no deadlock).
  8 source-guard tests; all regression suites green (5b57adb).

### Windows-accessible tasks status: ALL CLOSED (tasks 1-95)
All remaining open items require the target host (SHA256SUMS, smoke tests,
shell validation) or are blocked on other branches merging (prune_terminal,
preflight exception). No new Windows-doable hardening tasks identified after
twentieth analysis cycle.

## 0.32.2 Cursor Brief — remaining open items

Items below are DoD requirements from the Cursor Implementation Briefs (Days 1–5) not yet closed.

### Day 1 — repository hygiene (partial — needs Linux / target host for shell validation)

- [ ] Run `find . -name '*.sh' -type f -exec bash -n {} \;` on the target host to verify all shell scripts pass syntax check.
- [ ] Run `noemaforge/tools/prep/noemaforge-version-audit.sh --root . --expected 0.32.2 --strict-all` on the target host.
- [x] Check `noemaforge/configs/llm-backends-policy.yaml` and `noemaforge/configs/role-catalog.yaml` for stale version strings (0.31.13.alpha, 0.29.10, 0.29.11) and update if found. — Both files clean, no stale strings (2026-05-28).
- [x] Audit `noemaforge/src/dataset_inventory.py` and `noemaforge/src/vault_reorg.py` for any hardcoded RUNTIME_VERSION assignments outside `noemaforge_version.py`. — Both clean (2026-05-28).
- [x] Verify `.gitignore` has `__pycache__/` and `*.pyc` exclusions (and add them if missing). — Created full `.gitignore` (2026-05-28).

### Day 3 — frontend UX (partial — needs live GUI on the target host)

- [x] Add explicit mode confirmation message in chat after user picks a model-selection mode: "Mode selected: normal / full / full_composite N". — Implemented in app.js sendAdmin() (2026-05-28).
- [ ] Verify user message is appended exactly once and not duplicated after page refresh (needs manual smoke on live GUI).
- [ ] Manual smoke: `noemaforge dashboard start`, open `http://127.0.0.1:8765/`, send a message, refresh page, verify messages and selected mode both survive.

### Day 4 — duplicate-safe jobs (partial — needs target-host smoke)

- [x] Cancel marker wired in `job_cancel()`: status set to `cancel_requested`; `.cancel` sentinel file written to `jobs_dir` for subprocess polling (2026-05-28). Remaining: long-running runtime scripts (`noemaforge first-start`) must read the sentinel file — needs the target host.
- [ ] Manual smoke on the target host: send two identical `/api/model-selection/continue` requests back-to-back and confirm the same `job_id` is returned both times.
- [ ] Manual smoke on the target host: click Vault re-inventory twice rapidly and confirm one job, not two.

### Day 5 — release validation (target host required)

- [ ] Run full test suite on the target host: `python -m unittest discover noemaforge/tests/` and record pass/fail counts.
- [ ] Regenerate SHA256SUMS after all branches are merged to `release/0.32.2-hardening`: `bash noemaforge/bootstrap/make-checksums.sh`.
- [ ] Create clean release archive: `tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' -czf noemaforge-0.32.2.tar.gz noemaforge/ && sha256sum noemaforge-0.32.2.tar.gz > noemaforge-0.32.2.tar.gz.sha256`.
- [ ] Target-machine validation checklist (all on the target host):
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
