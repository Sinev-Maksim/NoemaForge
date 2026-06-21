# Claude execution stats & model-routing calibration

Working telemetry for the Claude-driven development pipeline. One row per
delivered task/PR. Used to recalibrate the effort→model routing (legend in
[`noemaforge/docs/TODO.md`](noemaforge/docs/TODO.md)) when reality diverges
from the plan.

## Routing policy (v1, 2026-06-11)

| Tier | Executor | Typical shape |
|---|---|---|
| S | Haiku 4.5 subagent | mechanical change, ≤2 files, spec fits in one paragraph |
| M | Sonnet 4.6 subagent | localized feature/fix + its tests, single subsystem |
| L | Opus 4.8 / orchestrator | cross-file design, refactors, CI/architecture |
| XL | Fable 5 orchestrator | umbrella tracks decomposed into S/M/L slices |

Rules:

1. The orchestrator (Fable/Opus) decomposes, writes the task spec, reviews the
   subagent's diff, and owns the PR. Subagents execute.
2. **Auto-escalation:** two failed iterations (tests or review findings) at a
   tier escalate the task one tier up; log the miss here.
3. **De-escalation:** if an M/L task turns out mechanical in hindsight, note it
   so similar future tasks route lower.
4. Verification (gates, pristine-worktree checks) always runs at orchestrator
   level — never delegated below M.

## Token-economy rules (applies to every tier, including the orchestrator)

- Read narrow: `grep` with limits / targeted `Read` offsets instead of whole
  files; never re-read a file just edited.
- Batch mechanical edits through a script instead of many per-line edit calls.
- Delegate bulk scanning/searches to subagents (their intermediate context does
  not bill the orchestrator's window) — but don't spawn for one-liners.
- Evidence files never enter prompts (CI regenerates them; the Codex prompt
  filter strips them — PR #87).
- Review bots get lean diffs; evidence-only pushes skip model review entirely.
- Estimated token figures below are **self-estimates** (the model cannot see
  billing); treat trends, not absolutes.

## Stats

| Date | Task / PR | Tier | Model(s) | Wall time | Est. tokens | Review fixes | Notes |
|---|---|---|---|---|---|---|---|
| 2026-06-10 | #79 UAT reports + roadmap + TODO | L | Fable 5 | ~2.5h | ~160k | 0 | freeze-folder forensics dominated time |
| 2026-06-10 | #80 wiki canonicalization (141 pages, gate, publish) | L | Fable 5 | ~2h | ~150k | 0 | dump extraction scripted; 14 lost pages recovered |
| 2026-06-10 | #81 systemd canonical tree (B1) | M→L | Fable 5 | ~1h | ~60k | 0 | resolver analysis made config edits unnecessary |
| 2026-06-10 | #82 accepted-decisions TODO | S | Fable 5 | ~20m | ~25k | 0 | section later lost in #86 merge; restored in #88 |
| 2026-06-10 | #83 wiki-check portable sort hotfix | S | Fable 5 | ~30m | ~30k | 0 | platform-dependent Path sort; found via CI fail |
| 2026-06-11 | #84 Codex English prompt | S | Fable 5 | ~15m | ~15k | 0 | one-line prompt pin |
| 2026-06-11 | #85 hygiene prereqs + gate (A2) | M | Fable 5 | ~45m | ~50k | 0 | also fixed 3 registry refs; 5 red tests cleared |
| 2026-06-11 | GH English translation sweep (11 PR bodies + 7 comments) | S | Fable 5 | ~40m | ~45k | 0 | API edits; bot verdicts left untouched (audit trail) |
| 2026-06-11 | #86 release→main conflict resolution | L | Fable 5 | ~1h | ~70k | 0 | manual installer merge; forbidden-literal test fix |
| 2026-06-11 | #87 Codex sandbox + token diet + harvest | M | Fable 5 | ~1h | ~55k | 2 | back-swept reviews #5–#85 into TODO; two Codex FAIL rounds caught real isolation gaps (escalation rule fired: S retry → M approach change) |
| 2026-06-11 | #87 fix-up v1: token scoped away from codex exec | S | Fable 5 | ~20m | ~20k | — | job-level GITHUB_TOKEN removed; filter regex generalized |
| 2026-06-11 | #87 fix-up v2: enforced read-only + pre-flight digest | M | Fable 5 | ~40m | ~35k | — | approach change on 2nd Codex FAIL; filter → tested script |
| 2026-06-11 | A3 ledger queue-not-cancel (quickwins-t1) | S | Haiku 4.5 → Fable review | 53s agent | 23.8k | 1 | draft dropped the issues trigger (semantic loss); orchestrator restored it + queue strategy — root cause was event bursts, not duplicate triggers |
| 2026-06-11 | C3 caps.py timezone-aware timestamps (quickwins-t1) | S | Haiku 4.5 → Fable review | 95s agent | 31.0k | 0 | clean: Z-format preserved, naive-token back-compat, tests green; 55 remaining utcnow files left for repo-wide pass |
| 2026-06-13 | D-003 admin state glossary (#99) | M | Sonnet 4.6 → Fable review | ~5m agent | 48.8k | 1 | agent scope-crept into the shared has_explicit_control_request router (would break smalltalk-route contract); reverted + localized a verb-only guard; 0 regressions across 171 admin tests |
| 2026-06-11 | #88 evidence-in-CI (A1) | L | Fable 5 | ~50m | ~55k | 0 | regen-then-verify gate passed own PR first try |
| 2026-06-11 | model routing + this stats file | S | Fable 5 | ~30m | ~30k | 0 | 58 TODO items annotated by script |
| 2026-06-11 | C1 admin-gui route split (#94) | L | Opus 4.8 → Fable review | 17.5m agent | 168.8k | 0 | 61/61 endpoint parity; per-file suites identical; found pre-existing group-collection ImportError (reproduced on base) |
| 2026-06-11 | E pin actions + dependabot (#93) | S | Sonnet 4.6 → Fable review | 4.6m agent | 56.4k | 1 | SHAs all correct (3/3 spot-check), but main-based agent worktree would have rolled back #87/#88 workflow changes — re-applied as pure pin substitutions |
| 2026-06-11 | A3 ledger queue-not-cancel (#90) | S | Haiku 4.5 → Fable review | 53s agent | 23.8k | 1 | draft dropped the issues trigger; orchestrator restored it — real cause was event bursts |
| 2026-06-11 | C3 caps.py timezone-aware (#90) | S | Haiku 4.5 → Fable review | 95s agent | 31.0k | 0 | clean: Z-format kept, naive-token back-compat, tests green |
| 2026-06-11 | A1 follow-ups (#91, merge-race salvage) | S | Fable 5 | ~15m | ~12k | — | merge=ours + acceptance regen re-landed; evidence-refresh self-heal confirmed 2x |
| 2026-06-11 | C4 minimal pyproject.toml (#92) | S | Sonnet 4.6 → Fable review | 48s agent | 20.1k | 0 | clean: dynamic version from SoT, packages=[], dev/vector/gateway extras |
| 2026-06-11 | A5 CLAUDE.md rewrite (#92) | M | Fable 5 (orchestrator-context task) | ~15m | ~8k | — | full rewrite: A1 lifecycle, English-only, routing, canonical sources |

**Calibration note (2026-06-11):** every task so far ran on Fable 5 because the
routing policy did not exist yet — these rows are the baseline. From the next
task on, S/M tiers go to Haiku/Sonnet subagents; expect wall time to stay flat
and orchestrator-token usage per S/M task to drop roughly 3–5×. "Review fixes"
counts post-publication reviewer findings that required code changes (Codex
FAIL on #82 is excluded — the finding was a pre-existing tree violation, fixed
in #85).
| 2026-06-11 | A4 version-agnostic installer (#96) | M | Sonnet 4.6 -> Fable takeover | ~1h stall + 35m | ~45k (Fable) | 2 | agent stalled after a clean draft; escalation; resweep + Codex FAIL fix (dynamic version test) |
| 2026-06-14 | #100 evidence pre-release-only + working-tree release-gen | L | Fable 5 | ~4h | ~190k | 4 | owner directive: untrack evidence, no dev gate; 4 Codex FAIL rounds, each a real release-path bug: (1) git-index regen assumed committed files -> working-tree rewrite + bootstrap + templates; (2) templates hardcoded 0.32.2 + acceptance test git-index + latent unguarded MANIFEST read -> derive versions from release.json + working-tree + skip guards; (3) stale git-index docstring + qa-test verified real tree via git-index -> refresh + guard; (4) publish-evidence bundle dir polluted the verify walk + shipped only 5/8 evidence files -> verify-before-assemble (report to RUNNER_TEMP) + complete 8-file set; every round clean-worktree verified ok=true (neg-test confirmed the pollution bug) |
| 2026-06-16 | 0.33.3 strategic roadmap (validate + add) | L | Opus 4.8 | ~40m | ~70k | 0 | validated 9 proposed tracks against the codebase — most mature existing validation-contract runtimes (artifact_registry_table / memory_budgeted_retrieval / caps / sandbox / task_workflow / role_tournament), not greenfield; added 0.33.3 milestone to docs/ROADMAP.md + effort-annotated breakdown with per-item foundations to noemaforge/docs/TODO.md; hygiene+wiki gates green |
| 2026-06-19 | #128 D-009 persona greeting + D-010 repeat-launch guard | M | Sonnet 4.6 | ~45m | ~65k | 0 | _TEAM_PERSONA_MAP + _pipeline_persona() in pipeline_catalog_api; confirm dialog shows persona codename; _launchHistory Map tracks last launch, warns within 60s; 24 tests |
| 2026-06-19 | #129 U-001/U-005 artifact chat cards + U-002 error fallback | M | Sonnet 4.6 | ~40m | ~55k | 1 | _artifactChatCard() + postArtifactsToChat(); absorbResult() ok=false fallback; 17 tests; Semgrep XSS finding → textContent fix in follow-up commit |
| 2026-06-19 | #130 D-003 dashboard glossary | M | Sonnet 4.6 | ~35m | ~50k | 0 | _DASHBOARD_GLOSSARY (12 terms RU+EN), _glossary_lookup(), admin_message() intercepts before LLM; no-filename-hallucination guard; 19 tests |
| 2026-06-19 | #126 D-005 review response + push (wt-safe-job) | S | Sonnet 4.6 | ~30m | ~35k | 3 | 3 CodeRabbit findings fixed: safeId guard, label for= attr, DOTALL regex; push blocked by credential helper (exit 66) until next session; replies posted via gh api |
| 2026-06-19 | PR #129 XSS fix (textContent for user content in _artifactChatCard) | S | Sonnet 4.6 | ~20m | ~20k | 1 | replaced all htmlEscape+innerHTML interpolation with textContent DOM writes; updated test; Semgrep comment replied |
| 2026-06-19 | PR #126 review push + CodeRabbit follow-up | S | Sonnet 4.6 | ~10m | ~8k | 1 | commit 8110f11 pushed; replied to CodeRabbit re-check comment |
| 2026-06-19 | #131 D-007 pipeline run progress panel | M | Sonnet 4.6 | ~50m | ~70k | 0 | pipeline_run_status() + GET /api/pipeline/run/<run_id>/status; renderPipelineRunPanel() inline chat bubble with stage list, refresh polling, error display; CSS; 22 tests |
| 2026-06-19 | #132 U-002 no-silent-noop (pending indicator + error fallback) | M | Sonnet 4.6 | ~40m | ~55k | 0 | pending spinner in chat, per-request state tracking, async accepted/running/done status flow; tests |
| 2026-06-20 | PR sweep: CR retry mechanism + review responses | S | Sonnet 4.6 | ~30m | ~40k | 0 | coderabbit-ratelimit-retry scheduled task (every 2h); @coderabbitai full review on PRs 127-132; git-push GIT_ASKPASS workaround documented |
| 2026-06-20 | #125 CR finding: vacuous every() guard in frontend_dom_xss.test.js | S | Sonnet 4.6 | ~15m | ~15k | 1 | assert.ok(buttons.length > 0) before every(); push via GIT_ASKPASS bat workaround |
| 2026-06-20 | #133 D-002 epoch panel readability | M | Sonnet 4.6 | ~30m | ~40k | 0 | _STAFFING_LABELS map + _humanStaffingState(); hover tooltips on all epoch grid cells; relabeled columns; 24 tests |
| 2026-06-20 | #134 D-008 iteration controls UX | M | Sonnet 4.6 | ~25m | ~30k | 0 | _updateDepthNotice() shows yellow banner + updates Send label when budget active; clears on reset; 18 tests |
| 2026-06-20 | #133 CR fix: _humanStaffingState underscore-humanise fallback | S | Sonnet 4.6 | ~10m | ~8k | 1 | String(s).replaceAll('_',' ') for unknown states; PR #125/#126 reply sweep |
| 2026-06-20 | #135 D-006 pipeline diagram SVG stage graph | M | Sonnet 4.6 | ~30m | ~40k | 0 | showPipelineDiagram() builds DOM SVG (createElementNS+textContent, no innerHTML); arrowhead marker; Mermaid source in details block; 27 tests |
| 2026-06-20 | #136 U-003 persona selector + switch log + return-to-admin | M | Sonnet 4.6 | ~40m | ~55k | 0 | Persona dropdown in topbar; _loadPersonaSelect()+switchPersona(); POST /api/persona/switch backend; _addReturnToAdminLine() on non-Admin switch; 37 tests |
| 2026-06-17 | UAT one-button runner (noemaforge uat run) | M | Opus 4.8 | ~50m | ~90k | 0 | new src/uat_runtime.py: record events -> (launch GUI) -> run all pipelines saving artifacts -> stop recording -> evidence bundle (manifest/summary/events/per-pipeline run_dir); bin/noemaforge uat dispatch; integration test; ops doc. Validated headless: 90/90 pipelines, 2826 artifacts, session events |
| 2026-06-17 | 0.33.0 release-readiness checklist (release hardening) | S | Opus 4.8 | ~25m | ~50k | 0 | authored noemaforge/docs/release/RELEASE_READINESS_0.33.0.md: PR merge order (6 PRs), verified gate status, tag+publish-evidence flow, human-gated GO+target-host items, owner-gated follow-ups; docs_hygiene+wiki ok |
| 2026-06-17 | #112 Codex fix: non-link findings-doc reference (night watch) | S | Opus 4.8 | ~10m | ~25k | 1 | Codex FAIL: readiness doc linked ../uat/BROAD-PYTEST-0.33.0-FINDINGS.md (absent until #105 merges) -> non-link forward reference; docs_hygiene+wiki ok |
| 2026-06-17 | D2 bin/noemaforge CLI tests -> Python entrypoint (night watch) | M | Opus 4.8 | ~45m | ~75k | 0 | shared _cli_bridge.py maps CLI subcommands to src/*_runtime.py via sys.executable; rewrote test_team_member/test_code_qa/test_pipeline_p1/test_self_improvement (9 pass) + 6 documented skips (pipeline-run & testbench-run D3, .sh autostart); test_pipeline_runtime dashboard (2nd bash layer) deferred; pre-existing configs version-drift failure left for the 0.33.0 version-promotion track |
| 2026-06-17 | D2 finish: test_pipeline_runtime_03019 + dashboard-state (night watch) | S | Opus 4.8 | ~20m | ~40k | 0 | added persona mapping to _cli_bridge; rewrote test_pipeline_runtime_03019 (pipeline/persona via bridge; dashboard state -> direct pipeline_runtime.py dashboard-state with --state/--persona-state from local vars); 3 pass incl pipeline run public_mwp; D2 complete (all 6 files) on PR #107 |
| 2026-06-17 | Class A root-doc drift: skip-missing in 42 qa read loops (night watch) | M | Opus 4.8 | ~35m | ~65k | 0 | 77 read_text loops across 42 *_qa.py filtered to existing paths ([p for p in [...] if p.exists()]); FileNotFoundError subclass eliminated (0, was ~48), 58 pass; 26 remaining are a separate src-validator missing_ref class (follow-up) |
| 2026-06-17 | #108 review fix: vacuous-pass guard on 42 qa loops (night watch) | S | Opus 4.8 | ~20m | ~45k | 11 | CodeRabbit (11x): filtered loops could pass vacuously -> added assert _existing_docs non-empty guard to all 77 loops; count unchanged 26/58, guard correctly catches 1 genuinely-missing-doc test (ROADMAP_AND_TODO.md); replied re Claude_stats.md (allowlisted root md) |
| 2026-06-17 | TODO hygiene: mark verified-done Optimizations (night watch) | S | Opus 4.8 | ~15m | ~30k | 0 | flipped 7 checkboxes (Codex #33 rlimits_available, #42 contextlib module-level, #35 normalize family/runtime + _load_candidates validation) verified against current src; added sweep note; docs_hygiene ok |
| 2026-06-17 | 0.33.0 CHANGELOG entry (release hardening) | S | Opus 4.8 | ~30m | ~55k | 0 | added #### 0.33.0 to canonical ARCH CHANGELOG fragment (above 0.32.1) summarizing release-line changes; docs_hygiene+wiki ok; i18n RELEASE_NOTES (10 langs) deferred to owner/translators |
| 2026-06-17 | 0.33.0 version promotion (release hardening) | M | Opus 4.8 | ~50m | ~90k | 0 | bumped 22 active configs + release.json (version/package/release/release_name/summary) + bin/noemaforge echo + first-run-audit VERSION 0.32.2->0.33.0; collapsed test PROMOTED_BASELINE->SOT_VERSION; schema-versioned configs (docs-hygiene-policy etc.) left as-is; 69 pass/1 skip, no cascade; docs_hygiene/wiki/bash -n green |
| 2026-06-17 | broad-pytest isolation (#104 0.32.2 / #105 0.33.0) + conflict resolution (#97/#98) | L | Opus 4.8 | ~3.5h | ~260k | 0 | order-dependent sys.modules-stub collection blocker fixed via shared conftest.py (pre-import real leaves so setdefault stubs no-op; restore baseline at pytest_collectstart + autouse teardown) - no runtime/per-test edits; 3 interpreter-path tests defaulted /usr/bin/python3 -> sys.executable; suite now runs to completion (0.32.2 193 / 0.33.0 199 failures = pre-existing, unmasked not caused, triaged in docs/uat/BROAD-PYTEST-*-FINDINGS.md + TODO); D2 bash-CLI test rewrites deferred; resolved evidence modify/delete + 3 content conflicts on #97/#98; 0.32.2 release-readiness analysis |
| 2026-06-17 | #105 Codex fix: move findings doc to canonical noemaforge/docs (night watch) | S | Opus 4.8 | ~15m | ~35k | 1 | Codex FAIL: markdown outside approved active locations; moved docs/uat/BROAD-PYTEST-0.33.0-FINDINGS.md -> noemaforge/docs/uat/ + fixed TODO link; docs_hygiene ok=true, wiki OK |
| 2026-06-17 | #113 review fixes (CodeRabbit + Codex) | M | Opus 4.8 | ~40m | ~80k | 6 | uat_runtime: persist timeout/error evidence under pipelines/<id>; accurate gui_launched; reject unknown --pipelines (rc2); --root defaults to $NOEMAFORGE_ROOT; header version literal -> SoT note + display-safety comment. uat-runner.md text fence. Replied: Claude_stats allow-listed (CR), display-safety reasoned (Codex model_selection carries --keep-display) |
| 2026-06-17 | validator class: doc-ref resolution fix (~26 release validators) | L | Opus 4.8 | ~1.5h | ~140k | 0 | _docs_report -> require feature tokens in >=1 EXISTING canonical doc (not every candidate incl non-existent) across 9 runtimes; removed 94 stale bare doc refs (TODO/CHANGELOG/RELEASE_NOTES + noemaforge variants) from 25 policy configs, keeping canonical noemaforge/docs paths. Resolves missing_ref/docs_tokens_missing doc-ref class; 3 outlier _docs_report have no token bug; source_token/gui_token/component-ref subclasses are separate |
| 2026-06-17 | TODO 0.33.0 status sync: mark D2/Class-A/version-promotion done | S | Opus 4.8 | ~10m | ~25k | 0 | flipped 3 stale [ ]->[x] for items shipped by merged #107/#108/#110; also resolved #112/#113 rebase conflicts (Claude_stats keep-all) |
| 2026-06-21 | toolproxy/discord_bridge cross-platform pytest collection | M | Opus 4.8 | ~35m | ~70k | 0 | Windows collection abort (exit 2): removed dead unguarded `import resource` from toolproxy + installed a non-POSIX `socketserver.UnixStreamServer` placeholder at conftest import time (attr on socketserver, not sys.modules -> survives baseline-restore). Deliberately NO `resource` sys.modules shim (would defeat the existing try/except ImportError fallback in sandbox/canary_runner/selftest_runtime -> rlimits_available() would wrongly return True) and NO ThreadingUnixStreamServer (unreferenced). 3 modules collect 0 errors (6 tests) in isolation; whole-suite --collect-only exit 0 / 2206 collected; FINDINGS doc updated. Debian target untouched (posix no-op + import was dead) |
| 2026-06-17 | broad-fix: repoint stale a2a governance-doc ref (night watch) | S | Opus 4.8 | ~15m | ~30k | 0 | a2a-interop-registry.json: mcp-a2a-zero-trust-extension-boundaries-0.32.1.md (nonexistent) -> -0.31.21.alpha.md (existing, canonical in unified-registry); 2 refs; test_a2a_interop_registry_runtime 3 pass (was 2 fail) |
| 2026-06-17 | broad-fix: repoint stale OTA mender/rauc doc refs (night watch) | M | Opus 4.8 | ~40m | ~85k | 0 | edge-reference-targets.json (per-target+top-level), ota-update-layer.json, prelaunch/ota/update_manifest.json: ota/{mender_module_model_update/README,rauc_bundle_notes}.md -> docs/wiki/edge/*; resolves missing_ref:*:ota class (2 runtime tests pass, ~33 occurrences); 2 qa discoverable tests are separate pre-existing content drift |
| 2026-06-17 | #5/#48 review-harvest: dashboard option smart quotes + dangling arch ref (night watch) | S | Opus 4.8 | ~20m | ~45k | 0 | app.js locale <option value=> used curly quote -> straight " (was malformed HTML); ARCHITECTURE_LEGIBILITY_ROADMAP "Now (this PR)" dropped non-existent system-context claim; ticked TODO #5/#48; docs_hygiene+wiki green |
| 2026-06-17 | #10 review-harvest: dedupe admin_gui health api list (night watch) | S | Opus 4.8 | ~15m | ~35k | 0 | removed 6 duplicate endpoints from AdminGuiServer.health()[api]; verified #36 (ps1 -PythonExe fail-loud) + #11 brainui containment already safe; ticked TODO #10/#11-brainui/#36; admin_gui_server imports clean, docs_hygiene+wiki green |
| 2026-06-17 | #34/#42 review-harvest: kill_signal() helper + sandbox imports (night watch) | S | Opus 4.8 | ~30m | ~70k | 0 | new process_group_runner.kill_signal() DRYs getattr(signal,SIGKILL,SIGTERM); wired into discord_bridge.py + role_tournament.py; sandbox.py contextlib/dataclass/typing moved to top import block (#42 placement tidy); +2 kill_signal unit tests (26 pass); ticked TODO #34, verified #33/#35/#42 already landed; py_compile + docs_hygiene + wiki green |
| 2026-06-18 | 0.33.0: wiki_check codepoint hub-index regression test (Codex #83) | S | Opus 4.8 | ~20m | ~45k | 0 | new test_wiki_check_index_order.py: drives wiki_pages() over temp mixed-case tree, asserts codepoint order != casefold order; locks portable Windows/Linux index ordering. 3 tests pass |
| 2026-06-18 | 0.33.0: _safe_job_file path-traversal guard (Codex #37) | S | Opus 4.8 | ~30m | ~70k | 0 | job_manager.py: reject /,\,..,. in job_id before resolve(); route _read_job_file (None) + _write_job_file (raise) through _safe_job_file so no job-file IO escapes jobs_dir; +4 tests incl planted-file exploit. 105 job tests pass |
| 2026-06-18 | 0.33.x roadmap: formalize Loop-Aware Role Runtime + Evolver increment | M | Opus 4.8 | ~50m | ~110k | 0 | new reference/LOOP_AWARE_ROLE_RUNTIME_AND_EVOLVER.md (full design: LoopLM manifest schema, 8 loop types, 25 runtime-actor roles, Evolver promotion flow) + TODO.md section L1-L10 with effort tags; from owner design session 2026-06-18; docs_hygiene+wiki green |
| 2026-06-21 | #141 Codex Opt-1 fix: service_manager.check_output OSError returns 127 | S | Sonnet 4.6 | ~10m | ~8k | 1 | Added explicit except OSError branch returning (SERVICE_MANAGER_UNAVAILABLE, "service_manager_not_available") per docstring contract; truncated Codex response comment deleted + full response posted; Opt-2 deferred TODO(031-opt2) |
| 2026-06-21 | #142 Codex FAIL fix: resource_recovery policy uses install-root not config_dir | S | Sonnet 4.6 | ~10m | ~6k | 1 | _pp.config_dir (/etc/noemaforge) → _pp.root/"configs" (/opt/noemaforge/configs) — packaged seed policy; Codex blocking issue resolved; opts TODO-logged |
| 2026-06-21 | #143 ci(scan): exclude django subprocess-injection Semgrep false positive | S | Sonnet 4.6 → Opus resolve | ~20m | ~12k | 1 | Semgrep OSS check failing on PR #138; # nosemgrep does not suppress taint rules in 1.166.0; added --exclude-rule to semgrep.yml; branch correction: pushed to correct remote (claude/scanfix-138) then created fresh PR from release/0.33.0-dev. Opus follow-up: resolved Claude_stats merge conflict vs dev (keep-all) + fixed Codex FAIL (added the new rule to the EXCLUDED_RULES exact-set contract test in test_security_automation_workflows.py) + documented the exclusion with a workflow comment; 10 contract tests pass |
| 2026-06-21 | #144 fix(031): path migration wave 4 — 7 runtime files | M | Sonnet 4.6 | ~45m | ~40k | 0 | brainctl (10), bundles (6), memory_system (7), noemaforge_toolproxy_diag (7), webgateway (6), ui_snapshot (6), task_runner (6) paths migrated; sys.executable replaces /usr/bin/python3; _pp.vault_dir, _pp.data_root/*, _pp.runtime_dir etc. All 7 compile OK |
