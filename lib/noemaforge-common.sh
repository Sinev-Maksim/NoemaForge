#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: lib/noemaforge-common.sh
# Zone: release/package
# Version: 0.31.13.alpha-patched1
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Provide NoemaForge release functionality for the packaged local runtime.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
# NoemaForge common helper defaults for recovery/MWP operator scripts.
# This file intentionally contains only shell-safe constants and helper
# functions used by the packaged helpers. It does not start services.

NOEMAFORGE_USER="${NOEMAFORGE_USER:-noemaforge}"
NOEMAFORGE_GROUP="${NOEMAFORGE_GROUP:-noemaforge}"
NOEMAFORGE_SHARE_MOUNT="${NOEMAFORGE_SHARE_MOUNT:-/mnt/noemaforge-share}"
NOEMAFORGE_VAULT_PATH="${NOEMAFORGE_VAULT_PATH:-$NOEMAFORGE_SHARE_MOUNT/noemaforge-lab/data/Vault}"
NOEMAFORGE_MODELSTORE="${NOEMAFORGE_MODELSTORE:-/var/lib/modelstore}"
NOEMAFORGE_RUNTIME_TIMERS="${NOEMAFORGE_RUNTIME_TIMERS:-noemaforge-llm-backends-manager.timer noemaforge-modelscan.timer}"
NOEMAFORGE_CORE_UNITS="${NOEMAFORGE_CORE_UNITS:-noemaforge-llm-backends-manager.service noemaforge-modelscan.service noemaforge-llm-gateway.service noemaforge-toolproxy.service}"
NOEMAFORGE_MAX_ACTIVE_LLMS="${NOEMAFORGE_MAX_ACTIVE_LLMS:-1}"

noemaforge_group(){
  printf '%s\n' "${NOEMAFORGE_GROUP:-noemaforge}"
}

noemaforge_require_root(){
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo "[noemaforge][ERROR] Run with sudo/root." >&2
    exit 1
  fi
}

noemaforge_print_runtime_policy(){
  cat <<POLICY
runtime_policy:
  max_active_llms=${NOEMAFORGE_MAX_ACTIVE_LLMS}
  gui_autostart_profile_default=runtime_only
  wogui_autostart_profile_default=bootstrap_cpu_llm
  heavy_llm_autostart=manual_only
  share_mount=${NOEMAFORGE_SHARE_MOUNT}
  vault=${NOEMAFORGE_VAULT_PATH}
POLICY
}

noemaforge_all_llama_units(){
  systemctl list-units --all --plain --no-legend 'noemaforge-llama@*.service' 2>/dev/null \
    | awk '{print $1}' \
    | grep -E '^noemaforge-llama@.*\.service$' || true
}

noemaforge_unit_control_group(){
  local unit="$1" cg
  command -v systemctl >/dev/null 2>&1 || return 1
  cg="$(systemctl show -p ControlGroup --value "$unit" 2>/dev/null || true)"
  [[ -n "$cg" && "$cg" != "/" ]] || return 1
  printf '%s\n' "$cg"
}

noemaforge_cgroup_pids(){
  local cg="$1" root
  [[ "$cg" == /* ]] || return 0
  root="/sys/fs/cgroup${cg}"
  [[ -d "$root" ]] || return 0
  find "$root" -type f \( -name cgroup.procs -o -name cgroup.threads \) -print0 2>/dev/null \
    | xargs -0 -r cat 2>/dev/null \
    | awk '/^[0-9]+$/ {print $1}' \
    | sort -u
}

noemaforge_drain_unit_cgroups(){
  local signal="${1:-TERM}" unit cg pid
  shift || true
  for unit in "$@"; do
    [[ -n "$unit" ]] || continue
    cg="$(noemaforge_unit_control_group "$unit" || true)"
    [[ -n "$cg" ]] || continue
    mapfile -t _noemaforge_cgroup_pids < <(noemaforge_cgroup_pids "$cg")
    [[ ${#_noemaforge_cgroup_pids[@]} -gt 0 ]] || continue
    _noemaforge_safe_pids=()
    for pid in "${_noemaforge_cgroup_pids[@]}"; do
      [[ "$pid" =~ ^[0-9]+$ ]] || continue
      [[ "$pid" != "$$" && "$pid" != "1" ]] || continue
      _noemaforge_safe_pids+=("$pid")
    done
    [[ ${#_noemaforge_safe_pids[@]} -gt 0 ]] || continue
    printf '[noemaforge-cgroup] %s %s pids: %s\n' "$signal" "$unit" "${_noemaforge_safe_pids[*]}"
    kill "-$signal" "${_noemaforge_safe_pids[@]}" 2>/dev/null || true
  done
}

noemaforge_print_unit_cgroups(){
  local unit cg
  for unit in "$@"; do
    [[ -n "$unit" ]] || continue
    cg="$(noemaforge_unit_control_group "$unit" || true)"
    [[ -n "$cg" ]] && printf '%s ControlGroup=%s\n' "$unit" "$cg"
  done
}

noemaforge_fuser_pids(){
  local path="$1"
  command -v fuser >/dev/null 2>&1 || return 0
  fuser -m "$path" 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+$' || true
}

noemaforge_gui_pid_holds_share(){
  local pid="$1" comm args
  [[ -r "/proc/$pid/comm" ]] || return 1
  comm="$(cat "/proc/$pid/comm" 2>/dev/null || true)"
  args="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
  case "$comm:$args" in
    *firefox*|*nautilus*|*Nautilus*|*org.gnome.Nautilus*|*Files*) return 0 ;;
    *) return 1 ;;
  esac
}
