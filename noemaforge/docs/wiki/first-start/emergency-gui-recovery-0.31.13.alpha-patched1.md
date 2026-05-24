# NoemaForge 0.31.13.alpha-patched1 — emergency GUI recovery

## Purpose

This page records the legacy live-validation host recovery fixes added after real `first-start --full_composite` runs could leave the operator in an emergency/login state with share unmount warnings.

## Rules

1. Emergency recovery must not start with `noemaforge headless off`.
2. Recovery must use minimal systemd actions first.
3. `display-manager.service` is started before explicit `gdm.service`.
4. All recovery starts use `--no-block` or must be bounded by a timeout.
5. `/run/nologin` is cleared only after `systemd-user-sessions.service` is requested.
6. `/mnt/brainos-share` and `/mnt/noemaforge-share` must be `nofail` automounts, not boot blockers.

## Manual recovery

From root/emergency shell:

```bash
mount -o remount,rw / 2>/dev/null || true
loadkeys us 2>/dev/null || true

systemctl stop noemaforge-first-start.service 2>/dev/null || true
pkill -TERM -f 'firstboot_orchestrator.py|role_tournament.py|noemaforge-first-launch|llama-server|noemaforge-llama-start' 2>/dev/null || true
sleep 5
pkill -KILL -f 'firstboot_orchestrator.py|role_tournament.py|noemaforge-first-launch|llama-server|noemaforge-llama-start' 2>/dev/null || true

systemctl daemon-reload
systemctl reset-failed
systemctl set-default graphical.target
systemctl start --no-block systemd-user-sessions.service 2>/dev/null || true
rm -f /run/nologin 2>/dev/null || true
systemctl start --no-block display-manager.service 2>/dev/null || true
systemctl start --no-block gdm.service 2>/dev/null || true
systemctl isolate --no-block graphical.target 2>/dev/null || true
```

If GUI is not back after about 30 seconds:

```bash
sync
systemctl reboot
```

## NoemaForge command

```bash
sudo noemaforge first-start abort
```

This command now uses the same minimal GUI recovery path.

