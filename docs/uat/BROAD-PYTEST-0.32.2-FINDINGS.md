# Broad pytest collection + failure findings — 0.32.2-hardening (dev-host)

Status: living triage record · Created 2026-06-16 · Branch `release/0.32.2-hardening`.

This is **not** a target-host UAT run (those are the `UAT-*.md` reports in this
folder). It records what happened when the full developer-host unit suite
(`python -m pytest noemaforge/tests`) was made to run end-to-end on Windows
after a long-standing, order-dependent collection blocker was fixed.

## TL;DR

- The broad suite used to abort at collection with 3 import errors, so **zero
  test bodies executed** and every downstream failure was invisible.
- Root cause: ~17 test files install incomplete stand-in modules into
  `sys.modules` at import time and never tear them down, so broad collection was
  order-dependent (`ImportError: cannot import name '_safe_int' from
  'orchestration_state' (unknown location)`).
- Fix: one shared `noemaforge/tests/conftest.py` (no runtime changes, no edits to
  individual test files) makes collection **and** execution order-independent.
- With the suite now running: **1556 passed, 193 failed, 129 subtests passed**
  (Windows / CPython 3.14). The `orchestration_state` "unknown location" import
  failures are **0**.
- The 193 failures are **pre-existing** — the fix did not cause them, it
  *unmasked* them (a collection crash runs nothing). They are classified below
  and must be triaged, not hidden.

## What shipped in this PR (the core fix)

1. `noemaforge/tests/conftest.py` — uniform isolation mechanism:
   - `pytest_configure` pre-imports the real runtime leaf modules, so an
     incomplete `setdefault` stub finds the real module already present and is a
     no-op (real module wins, as in a previously-lucky passing order).
   - `pytest_collectstart` restores that pristine baseline before each test
     module imports → an import-time assignment stub / `pop()` cannot leak into
     the next module (collection phase). Earlier attempts failed because they
     used `pytest_collect_file` / `pytest_pycollect_makemodule`, which fire
     during the up-front collector-creation pass, before any module is imported.
   - an autouse fixture restores the baseline after every test → a stub a test
     installs in `setUp`/a test body cannot leak during execution. (The specific
     `test_audit_remediation_unit` leaker does not exist on 0.32.2; the fixture
     is kept for parity with 0.33.0 and to harden against future execution-phase
     stubs.)
2. Cross-platform interpreter in three subprocess tests
   (`test_admin_control_plane_03112`, `test_admin_gui_evolution_03112`,
   `test_multimodal_shards_03112`): the hardcoded `/usr/bin/python3` now defaults
   to `sys.executable` (override via `NOEMAFORGE_TEST_PYTHON`). After this the
   suite has **0** `/usr/bin/python3` execution failures.

## Failure classification (193 failures)

| Count | Class | Root cause | Verdict |
|------:|-------|-----------|---------|
| 119 | `AssertionError` | docs/policy **content** drift ("discoverable"/"capture"/boundary/policy-validates assertions) | real — fix per track, not Windows |
| 50 | `FileNotFoundError` | tests open **repo-root** docs directly: `CHANGELOG.md` (27), `TODO.md` (19), other paths | real — root-doc layout drift, not Windows |
| ~20 | `OSError` (`WinError 193`) | tests / runtime execute a POSIX `.sh` / bash entrypoint | Windows-execution — see below |
| (111 raw refs) | stale `0.32.1` references | active validators/tests still reference `0.32.1` artifacts | real — stale-ref audit |
| ~9 | misc (`AttributeError`, schema, …) | assorted content/schema drift | real — triage per case |

The large majority are **not** Windows-related: real content/docs/policy drift
that exists on the branch independently of platform and would also fail on CI.

## Windows-execution failures (deferred to follow-up PR)

These are the only platform-coupled failures. They are **not** addressed in this
PR (the core isolation fix is kept clean); they are the scope of the D2 follow-up:

- **POSIX/bash entrypoint tests** — `test_code_qa_0310`, `test_pipeline_p1_03021`,
  `test_pipeline_runtime_03019`, `test_self_improvement_03022`,
  `test_team_member_03101` execute `bin/noemaforge` (a `#!/usr/bin/env bash`
  operator CLI), and `test_autostart_policy_03103` executes `.sh` ops scripts.
  Running via Git Bash is not viable on the dev host (bash fork-fails on the
  fork-heavy CLI; `bin/noemaforge` internally calls `/usr/bin/python3` and
  Linux-only tools). Follow-up plan: rewrite the five CLI tests to call the
  mapped Python entrypoint via `sys.executable`, each marked as bypassing the
  bash wrapper (limited coverage; the wrapper is validated on the Debian target /
  CI); `test_autostart_policy_03103` (no Python entrypoint) gets a documented
  skip-with-reason.
- **Runtime shells out to POSIX scripts (D3)** — after the interpreter fix,
  `admin_runtime.py` pipeline execution itself spawns a shell script
  (`WinError 193`, e.g. the music pipeline). This is a runtime-layer Linux
  coupling (0.33.1 system-independence track), not a test bug.

## Reproduce locally

```powershell
cd <worktree>
$env:PYTHONPATH = "$((Resolve-Path 'noemaforge/src').Path);$((Resolve-Path 'noemaforge').Path)"
python -m pytest noemaforge/tests -q `
  --ignore=noemaforge/tests/test_discord_bridge.py `
  --ignore=noemaforge/tests/test_toolproxy_roundtrip_and_local_workflows.py `
  --ignore=noemaforge/tests/test_toolproxy_voice_chat.py -p no:cacheprovider
# Order-dependence repro (3 collection errors before the conftest fix):
python -m pytest noemaforge/tests/test_admin_gui_init_and_events.py `
  noemaforge/tests/test_lsp_facade.py noemaforge/tests/test_mcp_router.py `
  noemaforge/tests/test_orchestration_state.py -q
```

`NOEMAFORGE_TEST_ISOLATION_DEBUG=1` makes the conftest print which modules it
restores before each test module.

## Status

- [x] Collection blocker fixed (`conftest.py`) — suite runs to completion.
- [x] Interpreter-path tests fixed (`sys.executable`).
- [ ] D2 POSIX/bash tests — follow-up PR (rewrite to Python entrypoint + mark
      limited; skip-with-reason where no entrypoint).
- [ ] Class A/B/C and D3 — pre-existing content / docs / stale-ref / runtime
      backlog; see `noemaforge/docs/TODO.md`.
