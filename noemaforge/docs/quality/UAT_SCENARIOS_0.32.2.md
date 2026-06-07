# NoemaForge 0.32.2 — UAT Scenarios

User Acceptance Test scenarios for the 0.32.2 hardening features. Each scenario is a
short, runnable acceptance check with explicit pass criteria. "Windows" = the dev host
(PowerShell, `py -3`); "Target" = the production target host (Debian Trixie, GNOME/GDM,
RTX 3080 Ti). Display-safety rule: every model-selection / heavy-GPU command on the
target MUST carry `--keep-display`.

## Before you run — which tree to test (READ FIRST)

Each scenario below is tagged with the PR that delivered it. **"PR #N — merged" means the
feature lives on `release/0.32.2-hardening`, not necessarily on the branch you have checked
out.** Running these scenarios on a feature branch or an older branch will produce confusing
failures that are *environment faults, not product defects*, for example:

- `ModuleNotFoundError: No module named 'resource'` → you are on a tree from **before** PR #33.
- `AttributeError: 'AdminGuiServer' object has no attribute 'bootstrap_dir'` → before PR #30/#31.
- `can't open file '...composite_pair_scoring.py'` / `No module named 'test_..._prune_terminal'`
  / launcher `.ps1` "does not exist" → before PR #44 / #37 / #36.

So **run UAT against the fully integrated release** (or the installed 0.32.2 package):

```powershell
cd C:\Users\sinev\!Projects\NoemaForge
git fetch origin
git checkout release/0.32.2-hardening
git pull --ff-only            # ensure every merged hardening PR is present
```

Common setup (Windows), used by several scenarios:

```powershell
cd C:\Users\sinev\!Projects\NoemaForge
$env:PYTHONPYCACHEPREFIX = "$env:TEMP\nfpyc"      # keep .pyc out of the tree
$env:PYTHONPATH = "noemaforge/src;noemaforge/tests"
```

### Preflight self-check (fails loudly if your tree is stale)

Run this once before the scenarios. If any line says `MISSING`, your checkout predates a
hardening PR — update it (above) before continuing; do not file a UAT failure.

```powershell
$ok = $true
@(
  "noemaforge/src/composite_pair_scoring.py",
  "noemaforge/tests/test_composite_pair_scoring_runtime.py",
  "noemaforge/tests/test_job_manager_prune_terminal.py",
  "noemaforge/tests/test_vault_reinventory_job_runtime.py",
  "noemaforge/tools/windows/run_admin_gui.ps1"
) | ForEach-Object {
  if (Test-Path $_) { "OK      $_" }
  else { $ok = $false; "MISSING $_" }
}
# sandbox import must not raise on Windows (PR #33)
$env:PYTHONPATH = "noemaforge/src;noemaforge/tests"
py -3 -c "import sandbox, canary_runner" 2>$null
if ($LASTEXITCODE -ne 0) { $ok = $false; "MISSING sandbox import-safety (pre-#33 tree)" }
if ($ok) { "PREFLIGHT OK — tree has all 0.32.2 hardening features" }
else { Write-Error "PREFLIGHT FAILED — update to release/0.32.2-hardening before running UAT" }
```

---

## UAT-1 — Model-selection-continue & Vault re-inventory are duplicate-safe (PR #30, #31 — merged)

**Goal:** a repeated GUI action does not create a second job.

**Windows (unit-level acceptance):**
```powershell
py -3 -m unittest test_model_selection_continue_idempotency_runtime `
                  test_model_selection_continue_idempotency_qa `
                  test_model_selection_continue_idempotency_performance
py -3 -m unittest test_vault_reinventory_job_runtime `
                  test_vault_reinventory_job_qa `
                  test_vault_reinventory_job_performance
```
**Accept if:** both groups print `OK` (6 tests each).

**Target (live acceptance):** with the dashboard running, POST the same
`/api/model-selection/continue` request twice back-to-back and click **Vault re-inventory**
twice rapidly.
**Accept if:** both `/api/model-selection/continue` responses return the **same `job_id`**,
and the double Vault click yields **one** job, not two.

---

## UAT-2 — Sandbox & canary import on Windows (PR #33 — merged)

**Goal:** the self-evolution import chain no longer dies on the Unix-only `resource` module.

**Windows:**
```powershell
py -3 -c "import sandbox, canary_runner; print('import OK')"
py -3 -c "import plugin_runner, glove_runner, localgw_uplink; print('importers OK')"
```
**Accept if:** both print `... OK` with **no** `ModuleNotFoundError: No module named 'resource'`.

---

## UAT-3 — Unix-only syscalls are guarded for non-POSIX (PR #34)

**Goal:** `netguard`, `discord_bridge`, `role_tournament` import and behave safely on Windows
(no `AttributeError` for `os.geteuid` / `signal.SIGKILL`).

**Windows:**
```powershell
py -3 -c "import netguard, discord_bridge, role_tournament; print('import OK')"
py -3 -c "import signal; print('SIGKILL fallback:', getattr(signal,'SIGKILL', signal.SIGTERM))"
```
**Accept if:** modules import without error; the fallback line prints a signal value (SIGKILL
on POSIX, SIGTERM on Windows) rather than raising.

---

## UAT-4 — Composite-pair diversity scorer (PR #35)

**Goal:** ranking model pairs rewards diversity (different family/runtime/role) and is
deterministic.

**Windows:**
```powershell
@'
[
  {"id":"a","family":"llama","runtime":"llama.cpp","score":30,"tags":["chat"]},
  {"id":"b","family":"llama","runtime":"llama.cpp","score":28,"tags":["chat"]},
  {"id":"c","family":"qwen","runtime":"vllm","score":26,"tags":["code","router"]}
]
'@ | Set-Content $env:TEMP\cand.json -Encoding utf8
py -3 noemaforge/src/composite_pair_scoring.py --candidates $env:TEMP\cand.json
py -3 -m unittest test_composite_pair_scoring_runtime
```
**Accept if:** the JSON output ranks pair **`["a","c"]` first** (diverse beats the homogeneous
top pair `a,b`), reports `total_pair_count: 3`, and the unit test prints `OK` (10 tests).

---

## UAT-5 — One-command Windows Admin GUI launcher (PR #36)

**Goal:** start the Admin GUI dashboard with a single command and reach it in a browser.

**Windows:**
```powershell
powershell -ExecutionPolicy Bypass -File noemaforge\tools\windows\run_admin_gui.ps1
```
**Accept if:** the console prints `NoemaForge Admin GUI: http://127.0.0.1:8765/`, the default
browser opens that URL within a couple of seconds, and the dashboard page loads (HTTP 200).
Stop with `Ctrl+C`. (Optional non-interactive check: add `-NoBrowser -Port 8799`, then in a
second shell `Invoke-WebRequest http://127.0.0.1:8799/api/health` returns **200**.)

---

## UAT-6 — JobManager prunes old terminal jobs (PR #37)

**Goal:** terminal jobs (done/failed/cancelled) older than the cutoff are removed from the
index; active jobs are never pruned.

**Windows:**
```powershell
py -3 -m unittest test_job_manager_prune_terminal test_job_manager
```
**Accept if:** prints `OK` (9 prune cases + the existing JobManager suite). Spot-check intent:
the suite asserts old `done/failed/cancelled` jobs are removed, `running/queued/needs_privilege`
are kept, and a corrupt `finished_at` falls back to a valid `created_at`.

---

## UAT-7 — Premerge checksum gate failure is self-explanatory (PR #38)

**Goal:** when the manifest/checksum evidence gate fails, the PR check explains *why* and that
it is not a code defect.

**Steps (GitHub UI):** open any PR whose **Quality gate** failed on the checksum step (e.g. a
branch left behind release) and read the job summary / annotations.
**Accept if:** there is an `::error` annotation titled **"Release evidence stale (not a code
defect)"** and a job-summary section naming the likely cause (stale checksums or a branch behind
release) and the fix (update from release + regenerate), with the raw mismatches in a
collapsible block — instead of a bare JSON dump.

---

## UAT-8 — Codex-runner guardrails (PR #32 — merged)

**Goal:** when the Codex/ChatGPT account hits its usage limit, the self-hosted runner pauses
Codex review until reset, and there is at most one Codex review comment per branch.

**Steps:** inspect `.github/workflows/autonomous-pipeline.yml` and a recently-reviewed PR.
**Accept if:** (a) a usage-limit marker `CODEX_HOME\runner-pause-until.txt` causes the gate step
to skip Codex review while `now < marker`; (b) each branch shows exactly **one**
`### Codex CLI review` bot comment (the newest replaces older ones), not an accumulating stack.

---

## UAT-9 — Cross-platform paths (PR #29 — merged)

**Goal:** runtime state directories resolve on Windows instead of hardcoded `/var/lib...`.

**Windows:**
```powershell
py -3 -c "from platform_paths import DEFAULT_PATHS as p; print(p.root); print(p.model_selection_state_dir)"
```
**Accept if:** the printed paths are under the Windows user-data area (e.g. `%LOCALAPPDATA%`),
not POSIX `/var/lib/...`, and no exception is raised.

---

## Notes

- **All hardening features (UAT-1 … UAT-9) are now merged into `release/0.32.2-hardening`**
  (PRs #30, #31, #33–#38, #44). Run every scenario against that branch (see the preflight above).
- Full end-to-end acceptance (live GPU model selection, GDM display-safety, first-start) is
  **target-host only** and tracked separately in the release validation checklist; those are
  not reproducible on the Windows dev host.

## Verification record

| Date | Tree | Result |
|---|---|---|
| 2026-06-07 | `release/0.32.2-hardening` @ `af30b54` (clean worktree) | **All UAT-1…7 unit/static scenarios PASS** on Windows dev host (`py -3`, Python 3.14): idempotency 6/6 + 6/6, sandbox/canary + importers import OK, syscall-guarded imports OK (SIGKILL→SIGTERM fallback), composite scorer CLI + tests OK, JobManager.prune_terminal + job_manager OK, launcher parses with 0 errors. |

A prior tryout that reported failures was traced to running on a **stale branch 83 commits
behind release** (pre-hardening code); the preflight self-check above now catches that case.
