Project identity



Product: NoemaForge — local-first AI OS, privacy-first, runs on Linux host BigBro-BOS

Repo: https://github.com/Sinev-Maksim/NoemaForge

Working branch: release/0.32.2-hardening

PR: https://github.com/Sinev-Maksim/NoemaForge/pull/2

Local root (Windows): C:\\Users\\sinev\\!Projects\\NoemaForge

Version source of truth: noemaforge/src/noemaforge\_version.py

Current target version: 0.32.2



Language and communication



Respond in Russian in all commit messages, PR comments, and issue comments

Code, file names, and CLI commands stay in English

Commit messages: English, imperative mood, concise



Git workflow — CRITICAL

Never commit directly to main.

Working branch: release/0.32.2-hardening

Feature sub-branches: claude/task-{issue-number}-{slug}

After completing a task: open PR into release/0.32.2-hardening, NOT main.

Commit message format:

<type>(<scope>): <short description>



Types: fix, feat, refactor, test, docs, chore

Example: fix(admin-gui): clear input box after message send

Always run before committing:



python -m py\_compile <changed .py files>

python -m json.tool <changed .json files> (verify parses)

Check no RUNTIME\_VERSION =  assignment outside noemaforge\_version.py



Task queue

Tasks come from GitHub Issues with label claude-next.

Workflow per task:



Assign issue to yourself, move to "In Progress"

Create branch: git checkout -b claude/task-{N}-{slug}

Implement, test, commit in small logical chunks

Push, open draft PR targeting release/0.32.2-hardening

Add label codex-review to the PR

Pull next claude-next issue and repeat



Do NOT batch-commit everything in one giant commit.

Do NOT create new files in noemaforge/src/\_\_pycache\_\_/.

Current P0 blockers (must complete before merge)

Priority order:



Admin GUI wiring — wire orchestration\_state.py, job\_manager.py,

session\_store.py, event\_log.py into admin\_gui\_server.py:



GET /api/session/current

GET /api/events

GET /api/jobs + POST /api/jobs/cancel

POST /api/model-selection/continue (duplicate-safe)

POST /api/vault/reinventory (duplicate-safe)

Clear input box after send

Persist selected mode across refresh

Restore message history after refresh





Checksum regeneration — regenerate SHA256SUMS after all content changes

Clean release archive — noemaforge\_0.32.2\_release.tar.gz

Test evidence — collect output of: pytest, py\_compile, bash -n,

version-audit, smoke tests

P1: noemaforge\_core.py:2118 — return inside finally block

(can suppress exceptions — fix or add suppression comment with justification)



Version rules



RUNTIME\_VERSION assignment allowed ONLY in noemaforge\_version.py

VERSION files at root, noemaforge/VERSION, docs/VERSION must all equal 0.32.2

Never hardcode version strings in Python source outside version module



Display safety — host: BigBro-BOS (Debian Trixie, GNOME/GDM, RTX 3080 Ti)

CRITICAL: Every command that starts model selection or heavy GPU work MUST include

\--keep-display or equivalent. First-start without this flag blanked the display before.

Default behavior for stop helpers: preserve graphical desktop (GDM, Firefox, Nautilus).

Code style



Python: follow existing style in file, no new external deps without discussion

Shell: POSIX-compatible where possible, add bash -n self-check

No .pyc files in git — .gitignore must cover \_\_pycache\_\_/ and \*.pyc

Markdown only in: noemaforge/docs/\*\*, helpers/, prelaunch/

Docs root noemaforge/docs/ allows only: README.md, Manifest.md, TODO.md



Forbidden strings in active files

These must never appear outside historical context:



BigBro-BOS (use env var or config instead)

docs/public or noemaforge/docs/public

OUTDATED



MCP tools available in Claude Code



github — read/write issues, PRs, comments, branches

filesystem — local file operations



Use github MCP to:



Fetch next claude-next issue automatically

Post PR description with test evidence

Add codex-review label after push

Comment on issue when task is done



After completing each task

bash# 1. Verify

python -m py\_compile $(git diff --name-only HEAD\~1 | grep '\\.py$')



\# 2. Commit with issue reference

git commit -m "fix(scope): description



Closes #N"



\# 3. Push and label

git push origin claude/task-N-slug



\# 4. Via MCP: add label codex-review to PR, comment on issue

Autonomous review TODO for Claude

Keep this block current after each claude/task-* branch is reviewed. Record branch, PR,
Codex verdict, CodeRabbit status, actionable/blocking comments, fixes and next action.
If CodeRabbit and Codex overlap on the same nitpick, record it once as carry-forward
context instead of treating it as a blocker.

- task-1 / PR #3 / claude/task-1-session-current:
  Codex PASS on 4829f2f; CodeRabbit success; blocking/actionable comments = 0.
  Only nitpick matched Codex: route tests were brittle source-string checks. Pilot
  contour works; proceed to the next branch from the start of the task list.
- task-2 / PR #4 / claude/task-2-events-api:
  Codex PASS on c28a8e8; CodeRabbit success after fix; blocking/actionable comments = 0.
  Fixed /api/events after_index validation so non-integer and negative values return
  JSON 400; route tests now exercise AdminGuiHandler.do_GET behavior instead of
  source-string checks. Ready for downstream review or merge.
- Copilot review note:
  Automated reviewer requests were attempted through the API but were not visibly
  attached as requested reviewers. If explicit Copilot review evidence is required,
  use the PR UI reviewer picker and record the result here.

Do NOT do



Do not run sudo noemaforge first-start without --keep-display

Do not merge to main directly

Do not create CHANGELOG\_\*, RELEASE\_NOTES\_\* extra files

Do not leave .pyc / \_\_pycache\_\_ in git tree

Do not mark task complete unless py\_compile + basic test pass

