# UAT 2026-06-08 — BrainOS freeze and NoemaForge migration cutover

Verdict: **PASS** — BrainOS control plane frozen and inert, NoemaForge 0.32.2
installed from `main`, first-start completed, runtime healthy, display preserved.

## Scope

Replace the legacy BrainOS control plane on the production target host with
NoemaForge in a reversible way:

1. snapshot and back up the running BrainOS state;
2. mask all BrainOS units so nothing legacy can start;
3. install NoemaForge from GitHub `main`;
4. run the real (non-dry-run) first-start in `--normal` mode;
5. prove the resulting runtime is healthy and the desktop session survived.

## Environment

- Host: production target (Debian GNU/Linux 13 "Trixie", GNOME/GDM, RTX 3080 Ti
  12 GiB, NVIDIA driver 550.163.01, CUDA 12.4).
- Source: GitHub `main` at commit `d93f8724ec6ff0fbe813575494273de73f42b11d`
  (`noemaforge-main-commit.txt`), version `0.32.2`.
- Share: `/mnt/noemaforge-share` mounted; canonical Vault present.

## Steps and results

### 1. Pre-freeze snapshots — PASS

Captured before any change (13:18): running AI processes
(`ai-processes-before.txt`), BrainOS services/timers/unit files
(`brainos-services-before.txt`, `brainos-timers-before.txt`,
`brainos-unit-files-before.txt`), host state (`host-before.txt`).

### 2. BrainOS backup — PASS

- Control-plane archive: `brainos-control-plane-20260608-131852.tgz`
  (~208 MiB, `brainos-control-plane-backup.log`).
- State copy: `/var/lib` rsync (`brainos-var-lib-rsync.log`).
- Share content index: `brainos-share-index.txt` (~0.8 MB listing).

Rollback to BrainOS therefore remains possible from the archive.

### 3. BrainOS units masked — PASS

18 units masked (`brainos-units-to-mask.txt`): bootdoctor, llm-gateway,
memsentinel, toolproxy, autostart-wogui, `llama@`, `onfailure@`, both
`auditor@*` timers, autostart-gui, dailyplan, llm-backends-manager,
maintenance, modelscan, both `recurring@*` timers, storage-guard, teamworker.

Every later status snapshot confirms `BRAINOS RUNNING: 0 loaded units`.

### 4. NoemaForge install from main — PASS

- Dry-run selftest: `noemaforge-vm-dry-run-selftest.log` — clean.
- Host install: `noemaforge-host-install.log` (13:26) — completed.
- Safe start + smoke (13:32): `noemaforge-safe-start.log`,
  `noemaforge-smoke.log`; success snapshot `noemaforge-success-status.txt`.
- Trixie preflight after permissions fix: 9/9 checks `pass`
  (`noemaforge-trixie-preflight-after-chmod.json`).

### 5. Real first-start (`--normal`) — PASS after one upstream fix

The first attempt surfaced a prestart failure caused by a missing `import re`
in the prestart script (service journal:
`noemaforge-first-start-service-last300.log`,
`noemaforge-first-start-service-since-1350.log`). After the fix landed
upstream, the rerun (`noemaforge-first-start-normal-real-after-import-re.log`,
14:05) started cleanly as `noemaforge-first-start.service` with the
display-safety banner confirming GDM is preserved by default:

> The display will NOT be stopped unless you explicitly pass
> `--allow-display-stop`.

The fix is verified present in later `main` checks
(`gh-main-known-issues-check.txt`: `prestart import re` → line 73).
Model-scan output captured in `noemaforge-modelscan-grep.txt`.

### 6. Final working status (14:15) — PASS

`noemaforge-final-working-status.txt`:

- preflight: `ok=true`, 9 passed / 0 warned / 0 failed;
- pipeline validate: `ok=true` — 90 pipelines, 24 teams, 430 patterns,
  23 personas, 180 selftest cases, 9 member cells;
- member validate: `ok=true` — 9 members, invariant `max_active_llms=1`,
  sequential execution;
- units: `noemaforge-llama@main`, `llm-gateway`, `memsentinel`, `toolproxy`
  active; 0 failed; 0 BrainOS units;
- GPU: only desktop processes (Xorg/gnome-shell/firefox); main backend running
  `smollm2-360m-instruct-q8_0.gguf` on the unix socket, CPU-safe
  (`--device none --n-gpu-layers 0`);
- manager units re-checked after install: `noemaforge-safe-start-after-manager-units.log`,
  `noemaforge-smoke-after-manager-units.log`.

## Findings

- The `import re` prestart failure was found and fixed during this run
  (now regression-checked on every later UAT — closed).
- No other blocking issues; desktop session never blanked.

## Verdict

**PASS.** The cutover is complete and reversible: BrainOS is fully masked with
a restorable backup, NoemaForge 0.32.2 from `main` owns the host runtime, and
display safety behaved as designed during real first-start.

## Evidence

Freeze directory root (see [README.md](README.md) for locations):
`ai-processes-before.txt`, `brainos-*.{txt,log,tgz}`, `host-before.txt`,
`noemaforge-host-install.log`, `noemaforge-vm-dry-run-selftest.log`,
`noemaforge-safe-start*.log`, `noemaforge-smoke*.log`,
`noemaforge-first-start-*.log`, `status-after-first-start-130.txt`,
`noemaforge-trixie-preflight-after-chmod.json`,
`noemaforge-success-status.txt`, `noemaforge-final-working-status.txt`,
`noemaforge-main-commit.txt`.
