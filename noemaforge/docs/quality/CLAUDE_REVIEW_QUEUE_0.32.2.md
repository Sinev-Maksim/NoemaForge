# Claude Review Queue 0.32.2

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
