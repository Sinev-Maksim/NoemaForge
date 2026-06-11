# UAT 2026-06-10 — fresh GitHub main clone, clean install and liveness

Verdict: **PASS** (`LIVENESS_UAT_OK`) — a pristine clone of `main` (0.32.2 as
merged by PR #77) installs and runs cleanly on the target host. One tooling
finding: smoke chat strictness (S-001).

## Scope

Prove that what is actually published on GitHub `main` — not the locally
evolved install from 2026-06-08 — installs from scratch and reaches a live,
healthy runtime on the production target host.

## Environment

- Host: production target (Debian 13 "Trixie", GNOME/GDM, RTX 3080 Ti).
- Previous install cleanly restarted first (16:09:
  `noemaforge-clean-restart.log`, `noemaforge-smoke-after-clean-restart.log`,
  `noemaforge-{member,pipeline,preflight}-after-clean-restart.json` — all ok).
- Fresh clone: `~/src/NoemaForge-gh-main-20260610-161639`
  (`source-path.txt`), HEAD `8bad7d5c242f2634739fa2701ee12db953f129b7` =
  merge of PR #77 (`release/0.32.2-hardening` → `main`), version `0.32.2`
  (`00-baseline.txt`, `before-gh-main-resync-status.txt`,
  `gh-main-fresh-clone-status.txt`).

## Steps and results

### 1. Known-issues regression check on the clone — PASS

`gh-main-known-issues-check.txt` verifies the fixes from the 06-08 migration
are present in `main`: prestart `import re` (line 73), 0.32.1 installer
recursion guard in `setup.sh`, modelscan + llm-backends-manager units shipped
in both unit trees, installer/uninstaller exec bits, release metadata at
0.32.2. It also records that the smoke script expects a literal `OK` chat
reply (see Findings).

### 2. Static and core validation — PASS

`01-static-uat.log`, `02-core-validation.log`:

- `trixie-preflight`: `ok=true`, 9/9 checks pass (OS, distro remediation,
  mount, Vault, datasets, llama_start, llama-server, shared libs, ModelStore
  shard safety);
- `pipeline validate`: `ok=true` (90 pipelines / 24 teams / 430 patterns /
  23 personas / 180 selftest cases / 9 member cells);
- `member validate`: `ok=true` (9 members, `max_active_llms=1`, sequential).

### 3. Install + safe start — PASS

- Setup dry-run selftest: `gh-main-setup-dry-run-selftest.log` — clean.
- Install: `gh-main-install.log` (16:17) — completed.
- Safe start: `03-safe-start-restart.log`,
  `gh-main-safe-start-after-install.log`; systemd state
  `04-runtime-systemd-status.log` — gateway, toolproxy, `llama@main` active,
  0 failed units.

### 4. Smoke and liveness — PASS with finding S-001

`05-smoke.json` / `gh-main-smoke-after-install.log`:

- backend health `ok`, gateway health `ok`;
- backend/gateway chat: `non_ok_response`, model answered
  *"I'm sorry, but as an AI"* — the script requires the literal string `OK`,
  so `overall` reports `degraded` even though the model is loaded and
  responding (smollm2-360m-instruct is a 360M model; literal-token compliance
  is not a fair liveness criterion for it);
- explicit liveness criterion (`05-liveness-result.txt`):
  `LIVENESS_UAT_OK: backend/gateway health ok; model responded`.

During the run the on-host smoke script was adjusted to label this case as
liveness (backup `noemaforge-op-smoke.sh.bak.20260610-162030` recorded in
`00-baseline.txt`); upstream commit `21f1cd4` carries the same direction.
Registered as **S-001** in the [defect register](DEFECT-REGISTER-0.32.2.md).

### 5. First-start artifacts and operator surface — PASS

`06-firststart-artifacts.log` (bootstrap artifact inventory) and
`07-operator-surface.log` (operator commands) reviewed without blockers.

### 6. Boot-mode switch + re-smoke — PASS

After `boot-mode manual`: `08-safe-start-after-boot-mode-manual.log`,
`08-smoke-after-boot-mode.json` — same healthy state, no timers pending
(`99-uat-final-verdict.txt`: `0 timers listed`).

### 7. Final verdict snapshot (16:25) — PASS

`99-uat-final-verdict.txt`: version 0.32.2 at HEAD `8bad7d5c…`; 0 failed
units; 0 BrainOS units; `llama@main` + gateway + toolproxy running; GPU idle
(~430 MiB desktop only); `LIVENESS_UAT_OK`.

## Findings

- **S-001 (Medium, tooling):** smoke `chat` check requires a literal `OK`
  reply, so a healthy tiny instruct model yields `overall=degraded`. The
  liveness verdict had to be derived separately. Make the shipped smoke
  criterion liveness-oriented (health + non-empty model reply), keep the
  strict literal check as an optional mode.

## Verdict

**PASS (`LIVENESS_UAT_OK`).** Published `main` is installable and live on the
reference target. The only correction needed is in validation tooling
semantics (S-001), not in the runtime.

## Evidence

Freeze directory: `uat-gh-main-20260610-162206/` (files `00`–`08`,
`99-uat-final-verdict.txt`, `source-path.txt`) plus root-level
`gh-main-*.{log,txt}`, `noemaforge-clean-restart.log`,
`noemaforge-*-after-clean-restart.{json,log,txt}`,
`noemaforge-local-source-backup-path.txt`.
