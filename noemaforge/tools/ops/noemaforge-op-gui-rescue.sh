#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/ops/noemaforge-op-gui-rescue.sh
# Zone: operator/gui-recovery
# Purpose: Idempotently rescue/restart graphical session and NVIDIA/display-manager wiring without stopping LLM by default.
# Callers: sudo noemaforge gui-rescue, systemd transient jobs, legacy wrapper gui-rescue.
# Safety: Locked with flock; detects real display manager; only stops LLM when --stop-llm is explicitly supplied.
# === End NoemaForge File Header ===
set -euo pipefail

ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
# shellcheck source=/opt/noemaforge/tools/ops/noemaforge-op-common.sh
source "$ROOT/tools/ops/noemaforge-op-common.sh"

LOCK_MODE="skip"
LOCK_WAIT_SECONDS="300"
STOP_LLM="0"
RESTART_DM="1"
DRY_RUN="0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --stop-llm|--with-llm-stop)
      STOP_LLM="1"; shift ;;
    --no-stop-llm|--preserve-llm)
      STOP_LLM="0"; shift ;;
    --no-restart-dm)
      RESTART_DM="0"; shift ;;
    --dry-run)
      DRY_RUN="1"; shift ;;
    --lock-wait|--wait-lock)
      LOCK_MODE="wait"; shift ;;
    --lock-wait=*)
      LOCK_MODE="wait"; LOCK_WAIT_SECONDS="${1#*=}"; shift ;;
    --lock-fail|--fail-if-running)
      LOCK_MODE="fail"; shift ;;
    --skip-if-running)
      LOCK_MODE="skip"; shift ;;
    -h|--help|help)
      cat <<'EOH'
Usage:
  sudo noemaforge gui-rescue [--wait|--direct] [--stop-llm] [--no-restart-dm]

Default behavior:
  - preserve NoemaForge LLM runtime;
  - reload NVIDIA modules / GLX preflight;
  - restart detected display manager if present.

Explicitly disruptive mode:
  sudo noemaforge gui-rescue --stop-llm
EOH
      exit 0 ;;
    *)
      echo "[gui-rescue][ERROR] unknown option: $1" >&2
      exit 2 ;;
  esac
done

if ! noemaforge_ops_lock_acquire "gui-rescue" "$LOCK_MODE" "$LOCK_WAIT_SECONDS"; then
  rc=$?
  [[ "$rc" == "66" ]] && exit 0
  exit "$rc"
fi

if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
  echo "[gui-rescue] WARNING: graphical session environment detected."
  echo "[gui-rescue] Display manager restart may kill the current graphical session."
  sleep "${NOEMAFORGE_GUI_RESCUE_COUNTDOWN:-3}"
fi

if [[ "$STOP_LLM" == "1" ]]; then
  echo "[gui-rescue] --stop-llm requested: stopping NoemaForge LLM first..."
  if [[ "$DRY_RUN" != "1" ]]; then
    "$ROOT/tools/ops/noemaforge-op-llm-stop.sh" --lock-wait=300 2>/dev/null || true
  fi
else
  echo "[gui-rescue] preserving NoemaForge LLM runtime. Use --stop-llm to stop it explicitly."
fi

DM_UNIT="$(noemaforge_detect_display_manager_unit || true)"
if [[ -z "$DM_UNIT" ]]; then
  echo "[gui-rescue][WARN] No display manager unit found among: display-manager, gdm3, gdm, lightdm, sddm"
  echo "[gui-rescue][WARN] Install/enable one, e.g.: sudo apt install gdm3 && sudo systemctl enable --now gdm3.service"
else
  echo "[gui-rescue] detected display manager: $DM_UNIT"
  if [[ "$RESTART_DM" == "1" ]]; then
    echo "[gui-rescue] stopping display manager..."
    [[ "$DRY_RUN" == "1" ]] || systemctl stop "$DM_UNIT" 2>/dev/null || true
    [[ "$DRY_RUN" == "1" ]] || systemctl reset-failed "$DM_UNIT" 2>/dev/null || true
  else
    echo "[gui-rescue] --no-restart-dm requested: display manager will not be restarted."
  fi
fi

echo "[gui-rescue] loading NVIDIA modules..."
if [[ "$DRY_RUN" != "1" ]]; then
  modprobe nvidia-current 2>/dev/null || modprobe nvidia 2>/dev/null || true
  modprobe nvidia-current-modeset 2>/dev/null || modprobe nvidia_modeset 2>/dev/null || true
  modprobe nvidia-current-uvm 2>/dev/null || modprobe nvidia_uvm 2>/dev/null || true
  modprobe nvidia-current-drm modeset=1 2>/dev/null || modprobe nvidia_drm modeset=1 2>/dev/null || true
fi

echo "[gui-rescue] checking nvidia_drm modeset..."
cat /sys/module/nvidia_drm/parameters/modeset 2>/dev/null || echo "nvidia_drm not loaded"

echo "[gui-rescue] forcing GLX to NVIDIA if available..."
if [[ "$DRY_RUN" != "1" ]]; then
  update-alternatives --set glx /usr/lib/nvidia 2>/dev/null || true
  ldconfig || true
fi

echo "[gui-rescue] daemon reload..."
if [[ "$DRY_RUN" != "1" ]]; then
  systemctl daemon-reload
  systemctl reset-failed || true
  systemctl set-default graphical.target 2>/dev/null || true
fi

if [[ -n "$DM_UNIT" && "$RESTART_DM" == "1" ]]; then
  echo "[gui-rescue] starting display manager non-blocking: $DM_UNIT"
  if [[ "$DRY_RUN" != "1" ]]; then
    systemctl enable "$DM_UNIT" 2>/dev/null || true
    systemctl start --no-block "$DM_UNIT"
  fi
  echo "[gui-rescue] done"
else
  echo "[gui-rescue] done"
fi
