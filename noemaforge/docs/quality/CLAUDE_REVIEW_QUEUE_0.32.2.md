# Claude Review Queue 0.32.2

## Claude Review Packet: PR #11 Job heartbeat and ProcessGroupRunner mixed-scope review

Status: pending-claude-review
Branch: release/0.32.2-hardening
Related issue: #1
Related PR: #11
Changed files:
- .github/workflows/autonomous-pipeline.yml
- .github/workflows/qa-version-bump.yml
- noemaforge/src/job_manager.py
- noemaforge/src/process_group_runner.py
- noemaforge/tests/test_job_heartbeat_and_process_runner.py

Intent:
Add JobManager heartbeat/staleness handling and ProcessGroupRunner support for
process-group-aware long-running job execution and cancellation foundations.

Risk areas:
- JobManager/orchestration lifecycle semantics.
- Process-group creation and cancellation behavior across Windows/Linux target
  differences.
- Repeated introduction of `job_manager.py` across task branches.
- CI workflow changes are present in this orchestration branch and need scope
  review before this PR can be considered clean.
- GitHub `codex-review` is FAIL, but the failure text references `/api/events`,
  which is not present on the current checked head.

Questions for Claude:
1. Are the heartbeat/staleness thresholds and ProcessGroupRunner contracts
   correct for target BigBro-BOS orchestration?
2. Should CI workflow changes be removed from this branch or split into a
   dedicated workflow PR?
3. Should Codex be re-run after branch cleanup because the current Codex FAIL
   text appears inconsistent with the checked diff?

Validation already run:
- Public GitHub API inspection of PR #11 comments/checks.
- CodeRabbit summary comment present; blocking/actionable review comments
  observed: 0.
- GitHub `validate-claude-push`: success.
- GitHub `codex-review`: FAIL on commit
  `d2232a6d79eb08e3884781dd15015a1e0d7c10ba`.
- `py -3 -c "import compileall, sys; ok = compileall.compile_dir('noemaforge/src', quiet=1, force=True); sys.exit(0 if ok else 1)"`
- `py -3 -m unittest noemaforge/tests/test_job_heartbeat_and_process_runner.py`
  (24 tests)
- `git diff --check origin/release/0.32.2-hardening...HEAD`

Do not merge before:
- Claude reviews the heartbeat/process-group contract and target OS implications.
- Claude reviews or removes the CI workflow changes from this task branch.
- Codex review is re-run on the scope-cleaned/current branch.
- Duplicate JobManager changes are reconciled with PR #8/#9 ordering.

## Claude Review Packet: PR #10 Admin chat routing mixed-scope review

Status: pending-claude-review
Branch: release/0.32.2-hardening
Related issue: #1
Related PR: #10
Changed files:
- .github/workflows/autonomous-pipeline.yml
- .github/workflows/qa-version-bump.yml
- noemaforge/src/admin_gui_server.py
- noemaforge/src/job_manager.py
- noemaforge/tests/test_admin_chat_routing.py

Intent:
Route direct Admin GUI chat actions into model-selection and Vault
re-inventory job creation, with focused tests around Admin chat routing.

Risk areas:
- Admin GUI behavior and job creation semantics.
- Repeated introduction of `job_manager.py` across task branches.
- CI workflow changes are present in a chat-routing branch and need scope
  review before this PR can be considered clean.
- GitHub `codex-review` is FAIL, but the failure text references `/api/events`,
  which is not present on the current checked head.

Questions for Claude:
1. Should the CI workflow changes be removed from this chat-routing PR or split
   into a dedicated workflow PR?
2. Is the current chat-routing behavior sufficient once the workflow scope is
   cleaned up?
3. Should Codex be re-run after the branch is rebased/scope-cleaned, because the
   current Codex FAIL text appears inconsistent with the checked diff?

Validation already run:
- Public GitHub API inspection of PR #10 comments/checks.
- CodeRabbit summary comment present; blocking/actionable review comments
  observed: 0.
- GitHub `validate-claude-push`: success.
- GitHub `codex-review`: FAIL on commit
  `b0a8cb389184284c21cc799a465328eeadd1f3fc`.
- `py -3 -c "import compileall, sys; ok = compileall.compile_dir('noemaforge/src', quiet=1, force=True); sys.exit(0 if ok else 1)"`
- `py -3 -m unittest noemaforge/tests/test_admin_chat_routing.py` (26 tests)
- `git diff --check origin/release/0.32.2-hardening...HEAD`

Do not merge before:
- Claude reviews or removes the CI workflow changes from this task branch.
- Codex review is re-run on the scope-cleaned/current branch.
- Any duplicated JobManager introduction is reconciled with PR #8/#9 ordering.

## Claude Review Packet: PR #9 Admin GUI JobManager wiring return

Status: pending-claude-fix
Branch: release/0.32.2-hardening
Related issue: #1
Related PR: #9
Changed files:
- noemaforge/src/admin_gui_server.py
- noemaforge/src/job_manager.py
- noemaforge/src/orchestration_state.py
- noemaforge/tests/test_admin_gui_job_manager_wiring.py

Intent:
Wire JobManager into AdminGuiServer job methods so Admin GUI job listing,
lookup, creation, persistence, and cancellation use the file-backed job
registry introduced by the previous task.

Risk areas:
- Admin GUI `/api/jobs` behavior and runtime job visibility.
- JobManager integration with legacy job JSON shape and privileged job fields.
- Cancellation behavior and dead legacy code left after early returns.
- Path safety around raw `job_id` lookups through `JobManager.get()`.

Questions for Claude:
1. Fix `AdminGuiServer.jobs_list()` so it no longer references removed `data`
   and all focused tests pass.
2. Decide whether the dead legacy block after `job_cancel()`'s new return should
   be removed in this branch.
3. Decide whether `JobManager.get()` must sanitize `job_id` internally to retain
   the previous `safe_id(job_id)` path-safety contract for all callers.

Validation already run:
- Public GitHub API inspection of PR #9 comments/checks.
- CodeRabbit summary comment present; blocking/actionable review comments
  observed: 0.
- GitHub `Quality gate` and `validate-claude-push`: success.
- GitHub `codex-review`: FAIL on commit
  `970b5267deea27240e37b735e2fa5a9c8cb51f54`.
- `py -3 -c "import compileall, sys; ok = compileall.compile_dir('noemaforge/src', quiet=1, force=True); sys.exit(0 if ok else 1)"`
- `py -3 -m unittest noemaforge/tests/test_admin_gui_job_manager_wiring.py`
  reproduced the blocker: 27 tests run, 5 errors, all in `jobs_list()` with
  `NameError: data is not defined`.
- `git diff --check origin/release/0.32.2-hardening...HEAD`

Do not merge before:
- The `jobs_list()` blocker is fixed and the focused unittest passes.
- Codex review is re-run on the fixed branch.
- Claude explicitly resolves the cancellation dead-code and path-safety
  questions above.

## Claude Review Packet: PR #8 JobManager file-backed registry

Status: pending-claude-review
Branch: release/0.32.2-hardening
Related issue: #1
Related PR: #8
Changed files:
- noemaforge/src/job_manager.py
- noemaforge/tests/test_job_manager.py
- noemaforge/tools/prep/noemaforge-first-run-audit.sh

Intent:
Add a file-backed JobManager for queued/running/final job records with PID/PGID
tracking, cancellation flags, output tails, idempotency keys, and persisted job
metadata for later Admin GUI/API wiring.

Risk areas:
- JobManager/orchestration state correctness and persistence semantics.
- Duplicate-safe behavior for idempotency keys and lock keys.
- Cancellation contract currently records a cancel flag/status but does not
  terminate OS processes by itself.
- File-backed writes are simple JSON writes; review whether atomicity/locking is
  sufficient for expected concurrent Admin GUI/API access.
- GitHub Actions did not run Codex review because `validate-claude-push` failed
  on a broad `RUNTIME_VERSION =` grep match in docs/tests before codex-review.

Questions for Claude:
1. Is the JobManager record schema sufficient for the upcoming Admin GUI
   `/api/jobs` and `/api/jobs/cancel` wiring?
2. Should this file-backed implementation add atomic writes or file locks before
   it is used by concurrent API/runtime callers?
3. Should `cancel()` remain a flag-only request at this layer, or should it own
   process/process-group termination semantics?

Validation already run:
- Public GitHub API inspection of PR #8 comments/checks.
- CodeRabbit summary comment present; blocking/actionable review comments
  observed: 0.
- `py -3 -c "import compileall, sys; ok = compileall.compile_dir('noemaforge/src', quiet=1, force=True); sys.exit(0 if ok else 1)"`
- `py -3 -m unittest noemaforge/tests/test_job_manager.py` (48 tests)
- `git diff --check origin/release/0.32.2-hardening...HEAD`

Do not merge before:
- Claude review has explicitly accepted or requested changes for the
  JobManager/orchestration contract.
- GitHub Actions validation is re-run after the version-grep false positive is
  fixed or bypassed for docs/tests.
