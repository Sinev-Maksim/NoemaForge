You are Codex working locally in the NoemaForge repository.

Mission:
Drive NoemaForge 0.33.0 to prod-ready for the current install/re-entry hardening loop.

Primary target:
- Work from release/0.33.0-dev.
- Keep heavy LLM autostart disabled.
- Preserve max_active_llms=1.
- Preserve runtime_only semantics: gateway/toolproxy only; no main backend required.
- Do not make /opt/noemaforge mutable runtime state.
- Do not silently change boot persistence.
- Do not hide real failures as green. Expected degraded/skip states must be explicit and evidenced.

Issue set to resolve first:
- #212 installed payload loses executable bits for smoke/preflight/operator scripts.
- #213 installer installs /opt/noemaforge as invoking user and group-writable.
- #214 runtime_only smoke should not fail on intentionally missing main backend.
- #215 safe-start runtime_only mutates persistent systemd enablement despite manual boot mode.
- #216 installed systemd units rely on hotfix drop-ins and stale 0.32.1 metadata.
- #217 mvp-smoke reports failures without actionable stderr/artifact links.
- #218 pipeline catalog validation fails because media/admin pipelines reference missing media_team.
- #219 mvp-smoke lifecycle check is blocked by degraded_readonly under degraded_selected staffing.
- #220 pipeline validate emits JSON but rejects --json.
- #221 umbrella loop task.

Local evidence from re-entry:
- Trixie baseline is clean.
- runtime_only safe core starts successfully.
- /opt chmod/chown local repair confirmed install payload problems.
- pipeline validate currently fails on unknown team media_team.
- pipeline approve/advance in smoke state returns degraded_readonly under staffing_state=degraded_selected.
- pipeline validate --json currently rejects --json.
- manual boot-mode was restored by disabling gateway/toolproxy after diagnostic start.

Required work loop:
1. Inspect issue JSON files under .codex/tasks/0.33.0-prod-ready/issues/.
2. Fix all relevant source/install/test/docs problems for #212-#220.
3. Add/update tests.
4. Regenerate release manifests/checksums if this repository requires it.
5. Run focused validation.
6. If issues are fixed, update install/re-entry/operator docs.
7. Run automated recheck:
   - unit/source tests relevant to changes;
   - catalog validation;
   - noemaforge pipeline validate;
   - noemaforge pipeline validate --json if implemented;
   - mvp-smoke or test equivalent;
   - runtime_only/profile-aware smoke.
8. For newly discovered unfixed problems, create concise GitHub issues with evidence, link them from #221, and return to fixing.
9. Reconcile implementation against current 0.33.0 requirements:
   - implemented;
   - partial;
   - missing;
   - deferred;
   - safety-driven changes.
10. Convert gaps into TODO points:
   - 0.33.0 release blockers first;
   - post-0.33.0;
   - research/design;
   - target-host/manual validation.
11. Solve 0.33.0 TODOs first, then lower-priority TODOs.

Token/rate-limit behavior:
- Do not loop on repeated Codex failures.
- If rate/usage/token limit is hit, stop cleanly.
- The outer runner will write a pause marker and resume after reset/fallback time.
- Leave a compact status note in .codex/tasks/0.33.0-prod-ready/status.md.

GitHub behavior:
- If ALLOW_GH_WRITE=1, you may create/update issues/comments when new evidence is found.
- If ALLOW_PUSH=1 and tests pass, you may push the work branch.
- If ALLOW_PR=1 and a coherent change set exists, open or update a draft PR.
- Keep PRs bounded and reviewable.

Acceptance before declaring done:
- #212-#220 are fixed or explicitly closed with documented reason.
- Clean install/re-entry layout has correct /opt ownership and executable modes.
- runtime_only validation does not fail because backend is intentionally absent.
- manual boot mode remains manual unless persistence is explicitly requested.
- systemd unit surface is clean, current-versioned, and not dependent on undocumented hotfix drop-ins.
- pipeline validate passes with media/admin catalogs.
- degraded staffing behavior is intentionally represented by mvp-smoke.
- failed smoke checks include command, exit code, stdout/stderr/report paths.
- docs reflect actual operator flow.
- final recheck report is attached/linked.
- requirements reconciliation creates/updates TODOs for remaining gaps.

Start by reading:
- .codex/tasks/0.33.0-prod-ready/issues/issue-221.json
- then issue-212.json through issue-220.json
- current git status and relevant install scripts/systemd/config/test files.

Runtime env passed by runner:
- ALLOW_GH_WRITE=1
- ALLOW_PUSH=1
- ALLOW_PR=1
- GH_REPO=Sinev-Maksim/NoemaForge
- WORK_BRANCH=codex/0.33.0-prod-ready-loop
