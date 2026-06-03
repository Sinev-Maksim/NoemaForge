Project identity

Product: NoemaForge - local-first AI OS, privacy-first, runs on the production target host.

Repo: https://github.com/Sinev-Maksim/NoemaForge

Integration branch: release/0.32.2-hardening

Release PR: https://github.com/Sinev-Maksim/NoemaForge/pull/2

Local root (Windows): C:\Users\sinev\!Projects\NoemaForge

Version source of truth: noemaforge/src/noemaforge_version.py

Current target version: 0.32.2


Codex role in this repository

Codex is the reviewer, validator, and optimizer for changes produced by Claude.

Default loop:

1. Claude creates implementation branches and pushes them to GitHub.
2. Codex fetches the Claude branch or PR from GitHub.
3. Codex reviews the diff against project context and architecture.
4. Codex runs local validation that is safe for the current host.
5. Codex either accepts the change with evidence, requests rejection/rework, or creates a small optimization/fix branch.

Do not blindly convert Claude workflow text into Codex workflow text. Claude producer instructions live in CLAUDE.md. Codex instructions live here.


Language and communication

User-facing replies: Russian.

PR comments and issue comments: Russian, unless quoting commands, logs, paths, identifiers, or GitHub labels.

Code, file names, branch names, labels, and CLI commands stay in English.

Commit messages: English, imperative mood, concise.

Commit message format:

<type>(<scope>): <short description>

Allowed types: fix, feat, refactor, test, docs, chore

Example: fix(admin-gui): clear input box after message send


Required context before reviewing changes

For every non-trivial Claude change, review it against:

- context.md - current operational handoff context.
- noemaforge/docs/reference/PROJECT_CONTEXT.md - canonical project context.
- noemaforge/docs/architecture/ARCHITECTURE.md - canonical package architecture.

If a task explicitly mentions "architecture.md", use noemaforge/docs/architecture/ARCHITECTURE.md as the canonical file. Compare docs/architecture/ARCHITECTURE.md only when the change touches top-level docs or mirror synchronization.

Reject or request rework when a change violates project context or architecture, even if tests pass.

Architecture invariants to protect:

- local-first, privacy-first operation;
- no hidden LLM, media, camera, microphone, or GPU autostart;
- explicit operator approval for privileged or heavy runtime actions;
- one active heavy/model worker unless an epoch/policy explicitly allows otherwise;
- ToolProxy and capability-token boundaries are not bypassed;
- Contract Epochs remain immutable at runtime;
- Admin GUI remains a localhost control-plane, not an implicit runtime launcher;
- target-host evidence stays target-only and must not be faked by local Windows tests;
- docs hygiene, manifest, checksum, and version rules remain release gates.


Git workflow - CRITICAL

Never commit directly to main.

Never merge to main directly.

Do not push to claude/* branches unless the user explicitly asks and the ownership risk is clear. Treat claude/* as inbound branches produced by Claude.

Codex review/fix branches use the codex/ prefix by default:

- codex/review-{issue-number}-{slug}
- codex/fix-{issue-number}-{slug}

If the repository owner explicitly requests the historical Codex/ prefix for a branch, follow that request for that task only.

Open Codex fix PRs into release/0.32.2-hardening, not main.

When accepting a Claude PR without changes, do not create a Codex branch. Leave review/test evidence in the PR or issue and record the verdict.

When optimizing a Claude change:

1. Fetch the Claude branch from GitHub.
2. Create a Codex branch from the reviewed Claude head or from release/0.32.2-hardening, whichever gives the cleanest review surface.
3. Keep commits small and scoped.
4. Push the Codex branch.
5. Open a draft PR targeting release/0.32.2-hardening.
6. Add label codex-review.
7. Comment on the original Claude PR/issue with the decision and link to the Codex fix PR.


GitHub queue semantics

Claude producer queue: GitHub issues with label claude-next.

Codex validation queue: Claude PRs/branches that are explicitly requested by the user, assigned for review, or labeled codex-review.

Do not consume claude-next as a Codex implementation queue unless the user explicitly tells Codex to implement a new task.

If Codex is explicitly assigned an implementation task, use a codex/task-{issue-number}-{slug} branch and still target release/0.32.2-hardening.


Review workflow for inbound Claude changes

Use GitHub MCP/tools to fetch PR metadata, changed files, review comments, CI/check status, labels, and linked issues.

Use local git to fetch and inspect the branch:

git fetch origin release/0.32.2-hardening claude/task-N-slug

Inspect the review surface against the integration branch:

git diff --stat origin/release/0.32.2-hardening...HEAD

git diff --name-only origin/release/0.32.2-hardening...HEAD

For code review, prioritize:

- functional regressions;
- safety and runtime boundary violations;
- architecture/context mismatches;
- release gate violations;
- missing or weak tests;
- over-broad refactors;
- stale generated artifacts, manifests, or checksums.

Decision rules:

- ACCEPT/PASS: tests are appropriate for the touched surface, no blocking review comments remain, and the change fits context.md plus architecture.
- OPTIMIZE: the change is directionally correct but needs small Codex fixes for correctness, safety, tests, or integration.
- REJECT/REQUEST CHANGES: the change violates project context/architecture, introduces unsafe runtime behavior, hides target-only work as local evidence, or has unresolved blocking defects.


Validation before accepting or committing

Always run before committing Codex changes:

python -m py_compile <changed .py files>

python -m json.tool <changed .json files>

Check no RUNTIME_VERSION = assignment exists outside noemaforge/src/noemaforge_version.py.

For shell changes, run bash -n on Linux/WSL/target where bash is available. On Windows without bash, record that bash syntax validation is blocked by host capability.

For frontend JavaScript changes, run the available syntax or unit check used by the repo, for example:

node --check <changed .js files>

For tests, choose the smallest meaningful suite first. Broaden when shared behavior, runtime contracts, or user-facing workflows are touched.

Do not mark a task complete unless py_compile plus the relevant basic tests pass, or unless the remaining validation is explicitly target-only and recorded as blocked evidence.


Release/version rules

RUNTIME_VERSION assignment is allowed only in noemaforge/src/noemaforge_version.py.

VERSION files at root, noemaforge/VERSION, and docs/VERSION must all equal 0.32.2 when present and active for the release.

Never hardcode version strings in Python source outside the version module.

After all content changes intended for release packaging, regenerate SHA256SUMS and manifests through the project-approved release workflow.

Do not create CHANGELOG_*, RELEASE_NOTES_*, verification-report, or raw research/source report files outside the canonical docs locations.


Display and target-host safety

Production target host: Debian Trixie, GNOME/GDM, RTX 3080 Ti.

CRITICAL: Every command that starts model selection or heavy GPU work must include --keep-display or an equivalent display-preservation flag.

Never run sudo noemaforge first-start without --keep-display.

Default stop/pause/rescue behavior must preserve the graphical desktop, GDM, Firefox, and Nautilus unless the user explicitly approves otherwise.

Target-only validations must not be simulated as success on Windows. Record them as blocked until target evidence exists.


Code style

Python: follow existing style in the touched file. Add no external dependencies without discussion.

Shell: keep POSIX-compatible where practical; add bash -n validation when bash is available.

No .pyc files in git. .gitignore must cover __pycache__/ and *.pyc.

Do not create files in noemaforge/src/__pycache__/.

Markdown active-tree placement is restricted by noemaforge/configs/docs-hygiene-policy.json.

Canonical package docs live under noemaforge/docs. The docs root noemaforge/docs allows only README.md, Manifest.md, and TODO.md.


Forbidden strings in active files

These must never appear outside historical/quarantined context. Use noemaforge/configs/docs-hygiene-policy.json -> forbidden_active_text as the source of truth:

- legacy production host names;
- legacy public-docs path strings;
- stale-content marker strings.

If a Claude change reintroduces forbidden active text, reject or patch it before acceptance.


GitHub/MCP usage

Use GitHub MCP/tools to:

- fetch PR and issue metadata;
- inspect review comments and CI status;
- add codex-review label after pushing a Codex fix PR;
- post review/test evidence in Russian;
- comment on the issue or PR when Codex accepts, optimizes, or rejects a change.

Do not extract or print GitHub credentials.


After completing a Codex review or optimization

Record:

- branch and PR;
- Claude commit/head reviewed;
- Codex verdict: PASS, OPTIMIZE, or REQUEST CHANGES;
- CodeRabbit/Copilot status if present;
- blocking/actionable comments count;
- tests run and important skipped/blocked validations;
- fixes applied by Codex, if any;
- next action.

If a Codex branch was created:

git push origin codex/review-N-slug

Open a draft PR into release/0.32.2-hardening and add codex-review.


Autonomous review TODO for Codex

Keep this block current after each claude/task-* branch is reviewed. Record branch, PR, Codex verdict, CodeRabbit status, actionable/blocking comments, fixes, and next action.

If CodeRabbit and Codex overlap on the same nitpick, record it once as carry-forward context instead of treating it as a blocker.

- task-1 / PR #3 / claude/task-1-session-current:
  Codex PASS on 4829f2f; CodeRabbit success; blocking/actionable comments = 0.
  Only nitpick matched Codex: route tests were brittle source-string checks. Pilot
  contour works; proceed to the next branch from the start of the task list.
- task-2 / PR #4 / claude/task-2-events-api:
  Codex PASS on c28a8e8; CodeRabbit success after fix; blocking/actionable comments = 0.
  Fixed /api/events after_index validation so non-integer and negative values return
  JSON 400; route tests now exercise AdminGuiHandler.do_GET behavior instead of
  source-string checks. Ready for downstream review or merge.
- task-3 / PR #5 / claude/task-3-session-mode-history:
  Codex PASS on d80917f; blocking issues = 0. Fixed CodeRabbit findings from
  38dec23 in d80917f: /api/session/mode now returns JSON 400 for malformed
  composite_top_n, frontend persists the selected/restored mode instead of a
  hardcoded full_composite value, the test header no longer hardcodes Version:
  0.32.2, and the 500-message cap test now exercises 510 messages.
  Local verification: py_compile admin_gui_server/orchestration_state/session_store,
  node --check app.js, and 35 unit tests all passed. CodeRabbit status on
  d80917f is success but "Review skipped" because release/0.32.2-hardening is
  not the default branch; before closing task-3, trigger @coderabbitai review on
  PR #5 and record blocking/actionable comments = 0 or add the next fix here.
- Copilot review note:
  Automated reviewer requests were attempted through the API but were not visibly
  attached as requested reviewers. If explicit Copilot review evidence is required,
  use the PR UI reviewer picker and record the result here.


Do NOT do

Do not run sudo noemaforge first-start without --keep-display.

Do not merge to main directly.

Do not push over Claude branches by default.

Do not turn claude-next into a Codex implementation queue.

Do not create CHANGELOG_*, RELEASE_NOTES_*, or parallel release-note files.

Do not leave .pyc or __pycache__ in the git tree.

Do not accept changes that contradict context.md or noemaforge/docs/architecture/ARCHITECTURE.md only because tests pass.
