# NoemaForge 0.32.1 — TTY status, GUI restore and interrupt recovery

> **Status: historical snapshot (0.31.13.alpha era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

## Context

Live full-composite real launch on legacy live-validation host showed that a heavy `first-start` can make the local TTY look frozen or leave the host in emergency/safe-mode if GUI/headless and share bind-mount recovery are not handled explicitly.

## Changes

- Non-dry-run `first-start` now emits periodic status lines to stdout and `/dev/console`.
- Status lines include timestamp, stage, state, model, role, task index and remaining budget when available.
- `noemaforge first-start abort` stops first-start/orchestrator/tournament/model backends and restores Debian GUI.
- Direct TTY `Ctrl+C` is trapped by `noemaforge-first-launch.sh`; it stops first-start work and calls GUI recovery.
- At normal completion or error exit, `first-start` uses minimal non-blocking GUI recovery, resets default target to `graphical.target`, and starts display-manager before GDM.
- Installer writes a `nofail,x-systemd.automount` NoemaForge bind-mount line to avoid boot-blocking emergency mode when `/mnt/noemaforge-share` is unavailable or busy.

## Operator recovery command

```bash
sudo noemaforge first-start abort
```

## TTY status examples

```text
[NoemaForge first-start][2026-05-13T23:59:00+01:00] step=role_tournament state=running model=qwen2-5-3b role=system.guard/surgeon task=4/10 left=180s | abort: Ctrl+C on direct TTY or sudo noemaforge first-start abort
```

## Safety rule

`Ctrl+C` works for direct TTY execution. If first-start was rehomed into a systemd job, the safe equivalent is:

```bash
sudo noemaforge first-start abort
```

Both paths stop model backends and restore Debian GUI.
