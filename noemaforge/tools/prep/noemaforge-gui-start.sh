#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-gui-start.sh
# Zone: release/package
# Version: 0.31.13.alpha
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Provide NoemaForge release functionality for the packaged local runtime.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
# NoemaForge 0.31.13.alpha GUI start action.
# Starts Debian GUI through GDM/display-manager. Does not start NoemaForge LLM.
set -euo pipefail

usage() {
  cat <<'HELP'
Usage: sudo noemaforge gui_start [--wait] [--restart] [--dry-run] [--help]
       sudo noemaforge gui-start [--wait] [--restart] [--dry-run] [--help]
       sudo noemaforge gui start [--wait] [--restart] [--dry-run] [--help]
       sudo gui-start [--wait] [--restart] [--dry-run] [--help]

Start Debian GUI through GDM/display-manager.

Options:
  --wait      wait until GDM/Xorg/GNOME appears ready
  --restart   restart display-manager instead of only starting it
  --dry-run   print planned actions only
  --help      show this help

This command does not start NoemaForge LLM.
HELP
}

WAIT=0
RESTART=0
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    -h|--help|help|"?") usage; exit 0 ;;
    --wait) WAIT=1 ;;
    --restart) RESTART=1 ;;
    --dry-run|--plan) DRY_RUN=1 ;;
    *) echo "[gui-start][ERROR] unknown argument: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$DRY_RUN" == 1 ]]; then
  cat <<'PLAN'
[gui-start] policy: start GUI only; do not start NoemaForge LLM
[gui-start] dry-run actions:
  systemctl set-default graphical.target
  systemctl start graphical.target
  start/restart display-manager.service || gdm.service || gdm3.service
  optional wait for gdm/gnome-shell/Xorg
PLAN
  exit 0
fi

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "[gui-start][ERROR] Run with sudo/root." >&2
  echo "Try: sudo noemaforge gui_start --wait" >&2
  exit 1
fi

echo "[gui-start] policy: start GUI only; do not start NoemaForge LLM"

systemctl set-default graphical.target >/dev/null 2>&1 || true
systemctl start --no-block graphical.target >/dev/null 2>&1 || true

unit_exists() {
  systemctl cat "$1" >/dev/null 2>&1 || systemctl list-unit-files "$1" --no-legend --no-pager 2>/dev/null | grep -q .
}

start_or_restart_dm() {
  local action="$1"
  local tried=0
  local unit
  for unit in display-manager.service gdm.service gdm3.service; do
    if unit_exists "$unit"; then
      tried=1
      echo "[gui-start] ${action} ${unit}"
      if systemctl "$action" --no-block "$unit"; then
        return 0
      fi
    fi
  done
  if [[ "$tried" == 0 ]]; then
    echo "[gui-start][WARN] no known display-manager unit found; starting graphical.target"
    systemctl start --no-block graphical.target
    return 0
  fi
  return 1
}

if [[ "$RESTART" == 1 ]]; then
  start_or_restart_dm restart
else
  if systemctl is-active --quiet gdm3.service \
    || systemctl is-active --quiet gdm.service \
    || systemctl is-active --quiet display-manager.service; then
    echo "[gui-start] display-manager already active"
  else
    start_or_restart_dm start
  fi
fi

echo "[gui-start] NVIDIA/GDM quick status:"
cat /sys/module/nvidia_drm/parameters/modeset 2>/dev/null || echo "nvidia_drm modeset unavailable"
nvidia-smi >/dev/null 2>&1 && echo "nvidia-smi: ok" || echo "nvidia-smi: unavailable"

if [[ "$WAIT" == 1 ]]; then
  echo "[gui-start] waiting for GUI readiness..."
  for i in $(seq 1 120); do
    if systemctl is-active --quiet gdm3.service \
      || systemctl is-active --quiet gdm.service \
      || systemctl is-active --quiet display-manager.service \
      || pgrep -x gnome-shell >/dev/null 2>&1 \
      || pgrep -x Xorg >/dev/null 2>&1; then
      echo "[gui-start] GUI readiness detected after ${i}s"
      exit 0
    fi
    sleep 1
  done
  echo "[gui-start][ERROR] GUI readiness was not detected within 120s" >&2
  exit 1
fi
