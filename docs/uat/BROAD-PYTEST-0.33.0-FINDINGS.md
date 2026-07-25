# Broad pytest collection + failure findings — 0.33.0-dev (dev-host)

Status: living triage record · Created 2026-06-16 · Branch `release/0.33.0-dev`
(worktree `codex/hosted-review-action`).

This is **not** a target-host UAT run (those are the `UAT-*.md` reports in this
folder). It records what happened when the full developer-host unit suite
(`python -m pytest noemaforge/tests`) was made to run end-to-end for the first
time on Windows, after a long-standing collection blocker was fixed.

## TL;DR

- The broad suite never used to run to completion: collection aborted with 3–56
  import errors, so **zero test bodies executed** and every downstream failure
  was invisible.
- Root cause of the blocker: ~17 test files install incomplete stand-in modules
  into `sys.modules` at import time and never tear them down, so broad
  collection was order-dependent (`ImportError: cannot import name '_safe_int'
  from 'orchestration_state' (unknown location)`).
- Fix: one shared `noemaforge/tests/conftest.py` (no runtime changes, no edits to
  individual test files) makes collection **and** execution order-independent.
- With the suite now running: **1975 passed, 211 failed, 164 subtests passed**
  (2186 tests, 17m23s, Windows / CPython 3.14).
- The 211 failures are **pre-existing** — the fix did not cause them, it
  *unmasked* them (a collection crash runs nothing). They must be triaged, not
  hidden. The classification and per-class verdicts are below.

## The fix

`noemaforge/tests/conftest.py` — a single uniform mechanism:

1. `pytest_configure` pre-imports the real runtime leaf modules
   (`orchestration_state`, `production_ai_contracts`, `privileged_gui_job_runner`,
   `job_manager`, `platform_paths`, …). An incomplete `setdefault` stub then
   finds the real module already present and is a no-op — the real module wins,
   exactly as in a previously-lucky passing order.
2. `pytest_collectstart` restores that pristine baseline before each test module
   imports → an import-time assignment stub / `pop()` cannot leak into the next
   module (collection phase). The earlier community attempts failed because they
   used `pytest_collect_file` / `pytest_pycollect_makemodule`, which fire during
   the up-front collector-creation pass, before any module is imported.
3. An autouse fixture restores the baseline after every test → a stub installed
   in `setUp` or a test body (e.g. `test_audit_remediation_unit` drops a
   `platform_paths` double) cannot leak into a later test that imports the real
   module during execution (execution phase).

Effect measured: the `platform_paths`/`orchestration_state` "unknown location"
import failures dropped to **0**; a targeted reproduction
(`test_audit_remediation_unit.py` then `test_code_evolution_loop.py`) went from
21 failures to the 3 that are genuine content failures; +25 tests pass overall
versus the collection-only fix, with no new failures.

## Failure classification (211 failures)

| Count | Class | Root cause | Verdict |
|------:|-------|-----------|---------|
| 130 | `AssertionError` | docs/policy **content** drift — "discoverable" / "capture" / boundary assertions over docs, policies, changelog/release-notes records | real — fix per track |
| 57 | `FileNotFoundError` | missing **repo-root** docs the tests open directly: `CHANGELOG.md` (27), `TODO.md` (20), plus other paths | real — root-doc layout drift |
| 18 | `OSError` (`WinError 193` / `/usr/bin/python3` / `WinError 2`) | tests (or the runtime they drive) execute a POSIX interpreter / shell script | Windows-execution — see below |
| ~9 | misc (`AttributeError`, `jsonschema`, …) | assorted content/schema drift | real — triage per case |
| (206 raw refs) | stale `0.32.1` references | registry/docs not advanced to 0.33.x | real — stale-ref audit |

The per-class counts above sum to ~214 against a 211 pytest-reported total; the
~3-item gap is not yet reconciled (likely a handful of overlapping/double-counted
cases between the `AssertionError` and misc buckets from the original triage
pass) — treat 211 as the authoritative total and the per-class breakdown as
approximate until re-audited against a fresh raw run. None of the 211 are caused
by the isolation fix. The large majority are **not** Windows-related: they are
real content/docs/policy drift that exists on the branch independently of
platform and would also fail on Debian/CI.

### Class A — root-doc layout drift (FileNotFoundError, 57)

Tests open `<repo-root>/CHANGELOG.md` and `<repo-root>/TODO.md` directly, but the
canonical docs live under `noemaforge/docs/`. Either the tests should target the
canonical location or root shims should exist. Not Windows-specific. Fix track:
docs-reference ledger.

### Class B — content/policy assertions (AssertionError, 130)

Source-guard / policy-validation tests assert that docs, policies and
changelog/release-notes records contain expected items ("…_are_discoverable",
"…_capture_…", "policy_validates"). These are real expectation/content drift and
need per-track fixes. Not Windows-specific.

### Class C — stale `0.32.1` references (206 raw hits)

The branch still carries `0.32.1`-scoped references that active validators/tests
flag. Fix track: stale-ref audit advancing refs to 0.33.x. Not Windows-specific.

### Class D — Windows execution (OSError, 9 test files)

These are the only genuinely platform-coupled failures. Two sub-groups:

D1 — **interpreter-path test bugs (fixed in this change):** the test hardcoded
`/usr/bin/python3` to run a `.py` script. Defaulting to `sys.executable`
(override via `NOEMAFORGE_TEST_PYTHON`) makes them cross-platform. Files:

- `test_admin_control_plane_03112.py`
- `test_admin_gui_evolution_03112.py`
- `test_multimodal_shards_03112.py`

`test_multimodal_shards` now fully passes on Windows. Two residual subtests in
the other two still fail for a **different** reason — see D3.

D2 — **POSIX/bash entrypoint tests (decision pending):** these execute
`bin/noemaforge` (a `#!/usr/bin/env bash` operator CLI) or `.sh` ops scripts
directly. Files:

- `test_code_qa_0310.py`
- `test_pipeline_p1_03021.py`
- `test_pipeline_runtime_03019.py`
- `test_self_improvement_03022.py`
- `test_team_member_03101.py`
- `test_autostart_policy_03103.py` (runs `noemaforge-autostart-safe.sh`,
  `noemaforge-boot-mode.sh`, `noemaforge-op-safe-start.sh`)

"Run them via Git Bash" was attempted and is **not viable on this host**:
Git Bash runs trivial commands but fork-fails on the fork-heavy CLI
(`dofork … 0xC0000142 — Resource temporarily unavailable`), and `bin/noemaforge`
internally calls `/usr/bin/python3` and Linux-only tools (`pkill`, `pgrep`,
`journalctl`, `systemctl`, `/var/lib/...`) that do not resolve under Git Bash on
Windows. They run on the Debian target / CI. Recommended handling: explicit
`skip` on non-POSIX hosts **with a stated reason** (so output shows
`skipped (reason)`, never a fake pass), or a faithful rewrite to the underlying
Python entrypoint where one exists. **Owner decision required** before applying.

D3 — **runtime shells out to POSIX scripts (real cross-platform runtime gap):**
after the D1 interpreter fix, `admin_runtime.py` pipeline execution itself spawns
a shell script (`WinError 193` inside the pipeline, e.g. the music pipeline). The
runtime — not the test — is Linux-coupled here. This is target-host/CI behaviour;
on Windows it is either skipped-with-reason at the test layer or treated as a
runtime portability item (0.33.1 system-independence track).

## Reproduce locally

```powershell
cd <repo-root>
$env:PYTHONPATH = "$((Resolve-Path 'noemaforge/src').Path);$((Resolve-Path 'noemaforge').Path)"
# Whole suite (Windows-safe ignores for known non-collecting integration files):
python -m pytest noemaforge/tests -q `
  --ignore=noemaforge/tests/test_discord_bridge.py `
  --ignore=noemaforge/tests/test_toolproxy_roundtrip_and_local_workflows.py `
  --ignore=noemaforge/tests/test_toolproxy_voice_chat.py -p no:cacheprovider
# Order-dependence repro (was 3 collection errors before the conftest fix):
python -m pytest noemaforge/tests/test_admin_gui_init_and_events.py `
  noemaforge/tests/test_lsp_facade.py noemaforge/tests/test_mcp_router.py `
  noemaforge/tests/test_orchestration_state.py -q
```

Setting `$env:NOEMAFORGE_TEST_ISOLATION_DEBUG = "1"` makes the conftest print
which modules it restores before each test module.

## Status

- [x] Collection blocker fixed (`conftest.py`) — suite runs to completion.
- [x] D1 interpreter-path tests fixed (`sys.executable`).
- [ ] D2 POSIX/bash tests — handling pending owner decision (skip-with-reason vs
      Python-entrypoint rewrite).
- [ ] Class A/B/C and D3 — pre-existing content / docs / stale-ref / runtime
      backlog; see `noemaforge/docs/TODO.md`.
