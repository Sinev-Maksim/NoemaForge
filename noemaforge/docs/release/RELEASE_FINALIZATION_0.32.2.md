# NoemaForge 0.32.2 — Release Finalization Status

_Prepared 2026-06-05 on `release/0.32.2-hardening` @ `de6cafd`. This is a finalization
**status + scope** record; the GO/NO-GO gate remains the target-host validation in
[`RELEASE_VALIDATION_CHECKLIST_0.32.2.md`](RELEASE_VALIDATION_CHECKLIST_0.32.2.md). It does
**not** authorize the release→main merge — that needs the production-target-host validation
and a human GO decision._

## Verdict

- **Local static gates: GREEN** (evidence below).
- **Release→main: BLOCKED** pending (1) the production-target-host (Debian Trixie / GNOME-GDM /
  RTX 3080 Ti) validation in the checklist, and (2) the one open in-scope PR **#44** merging.
- Everything **not** in the 0.32.2 scope below is **deferred to 0.33.0** — see the backlog.

## 0.32.2 scope (hardening features merged to release)

Version source of truth `0.32.2`; `VERSION`, `noemaforge/VERSION`, `docs/VERSION` all `0.32.2`.

| Area | Lands via |
|---|---|
| Cross-platform paths (platform_paths migration) | #29 |
| Admin-GUI idempotency: model-selection-continue + Vault re-inventory duplicate-safe | #30, #31 |
| Codex-runner guardrails (usage-limit pause, ≤1 review comment/branch) | #32 |
| Sandbox/canary Windows import-safety (`resource` guard) + `rlimits_available` metadata | #33, #42 |
| Unix-only syscall guards (geteuid / SIGKILL) | #34 |
| `JobManager.prune_terminal` (+ path-traversal guard) | #37 |
| One-command Windows Admin-GUI launcher | #36 |
| Premerge checksum-gate informativeness + Optimizations harvest | #38 |
| UAT acceptance scenarios | #41 |
| Composite-pair diversity scorer (version-header-clean re-submit) | **#44 (open)** |

## Local static-gate evidence (Windows dev host, on `de6cafd`)

Windows premerge audit (`noemaforge/tools/prep/noemaforge-premerge-check.ps1`): **13 passed, 0 failed**.

| Gate | Result |
|---|---|
| VERSION files = 0.32.2 | PASS |
| `docs/release.json` version fields = 0.32.2 | PASS |
| No `RUNTIME_VERSION=` outside `noemaforge_version.py` | PASS |
| `py_compile` all `noemaforge/src/*.py` | PASS (292 files) |
| JSON parse `noemaforge/configs/*.json` | PASS (169 files) |
| YAML parse `noemaforge/configs/*.yaml` | PASS (70 files) |
| No tracked `__pycache__` / `*.pyc` | PASS |
| Manifest/checksum evidence (`--hash-source git-index`) | `ok=true` (clean worktree) |

Not reproducible on the Windows dev host (target-host gates, see checklist): `bash -n` of all
`*.sh` (WSL/HCS unavailable here), full `unittest discover`, and the live GUI / GPU / GDM smokes.

## Remaining for release→main (NOT deferred — these are the 0.32.2 gate)

1. **Merge the open in-scope PR #44** (composite scorer re-submit), then regenerate the final
   release `SHA256SUMS` / `MANIFEST.json` against the frozen tree.
2. **Clean release archive** `noemaforge_0.32.2_release.tar.gz` (excluding `__pycache__`/`*.pyc`)
   + its `.sha256`, produced on the target/release host.
3. **Target-host (production) validation** — the 8 P0 target gates in
   `RELEASE_VALIDATION_CHECKLIST_0.32.2.md` (display safety, admin chat, mode persist,
   idempotency, vault, refresh, job cancel, gateway/ToolProxy/llama smokes).
4. **Human GO decision**, then merge `release/0.32.2-hardening` → `main`.

## Deferred to 0.33.0 (not touched / not required for 0.32.2)

- **Sockets (#3b):** migrate `/run/noemaforge/*.sock` defaults (`model_scorecards`, `surgeon_auto`,
  `team_scorecards`, `noemaforge_llm_client`, `roles/role_entry`) — cross-component, must sync with
  the Go gateway.
- **Version-header convention cleanup:** the `Version: 0.32.2` line is in every source file's
  header (it is why #35 was reverted); a project-wide strip of that template line (so it no longer
  reads as a hardcoded version literal) is a separate decision.
- **Open review optimizations** (from the TODO `## Optimizations` block) not yet actioned:
  `role_tournament.py` backend-stop is still Linux/systemd-specific (`systemctl`); DRY the
  `getattr(signal,"SIGKILL",SIGTERM)` fallback into a shared helper.
- **Wire the shipped primitives into callers:** call `JobManager.prune_terminal` from
  startup/periodic cleanup; wire the composite-pair scorer into the `full_composite` plan preview
  in `model_selection_runtime.plan_doc()`.
- **`_run_preflight` exception-reporting mode** (`_preflight_warning` in `/api/health`) — depends on
  `PreflightSuite` being wired into `admin_gui_server.health()`, which is not on release.
- **Policy-validation cluster** (`test_workspace_*_policy_validates`) — governance/doc-token
  alignment.
- **Runtime (not import-only) cross-platform exercise** of the self-evolution loop.

_All 0.33.0 items are tracked here for the next cycle; none block 0.32.2._
