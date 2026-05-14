#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/ops/noemaforge-op-common.sh
# Zone: operator/runtime-safety
# Purpose: Shared lock/idempotency helpers for mutating NoemaForge operator commands.
# Callers: noemaforge-op-llm-stop.sh, noemaforge-op-gui-rescue.sh, future ops scripts.
# Safety: Uses /run/noemaforge/locks plus flock; repeat invocations either wait or exit 0 with current state.
# === End NoemaForge File Header ===

noemaforge_ops_init_dirs() {
  install -d -m 0755 /run/noemaforge /run/noemaforge/locks 2>/dev/null || mkdir -p /run/noemaforge/locks
}

noemaforge_ops_lock_acquire() {
  # Usage: noemaforge_ops_lock_acquire <name> [skip|wait|fail] [wait_seconds]
  local name="${1:?missing lock name}"
  local mode="${2:-skip}"
  local wait_seconds="${3:-300}"
  local lock_dir="/run/noemaforge/locks"
  local lock_file="$lock_dir/${name}.lock"
  local state_file="$lock_dir/${name}.state"

  noemaforge_ops_init_dirs

  # shellcheck disable=SC2034 # consumed by the open file descriptor held for process lifetime
  exec {NOEMAFORGE_OP_LOCK_FD}>"$lock_file"

  case "$mode" in
    wait)
      if ! flock -w "$wait_seconds" "$NOEMAFORGE_OP_LOCK_FD"; then
        echo "[noemaforge-lock] timeout waiting for operation lock: $name" >&2
        [[ -f "$state_file" ]] && sed 's/^/[noemaforge-lock] running: /' "$state_file" >&2 || true
        return 75
      fi
      ;;
    fail)
      if ! flock -n "$NOEMAFORGE_OP_LOCK_FD"; then
        echo "[noemaforge-lock] operation already running: $name" >&2
        [[ -f "$state_file" ]] && sed 's/^/[noemaforge-lock] running: /' "$state_file" >&2 || true
        return 75
      fi
      ;;
    skip|*)
      if ! flock -n "$NOEMAFORGE_OP_LOCK_FD"; then
        echo "[noemaforge-lock] operation already running, not starting another: $name"
        [[ -f "$state_file" ]] && sed 's/^/[noemaforge-lock] running: /' "$state_file" || true
        return 66
      fi
      ;;
  esac

  {
    echo "name=$name"
    echo "pid=$$"
    echo "user=$(id -un 2>/dev/null || echo unknown)"
    echo "started_at=$(date -Is)"
    echo "cmdline=$0 $*"
  } >"$state_file"

  export NOEMAFORGE_OP_LOCK_NAME="$name"
  export NOEMAFORGE_OP_LOCK_STATE="$state_file"
  trap 'noemaforge_ops_lock_release' EXIT INT TERM
  return 0
}

noemaforge_ops_lock_release() {
  local state_file="${NOEMAFORGE_OP_LOCK_STATE:-}"
  if [[ -n "$state_file" && -f "$state_file" ]]; then
    {
      echo "name=${NOEMAFORGE_OP_LOCK_NAME:-unknown}"
      echo "pid=$$"
      echo "finished_at=$(date -Is)"
    } >"$state_file.done" 2>/dev/null || true
    rm -f "$state_file" 2>/dev/null || true
  fi
}

noemaforge_detect_display_manager_unit() {
  local u
  for u in display-manager.service gdm3.service gdm.service lightdm.service sddm.service; do
    if systemctl list-unit-files "$u" --no-legend 2>/dev/null | awk '{print $1}' | grep -qx "$u"; then
      echo "$u"
      return 0
    fi
    if systemctl list-units --all "$u" --no-legend 2>/dev/null | awk '{print $1}' | grep -qx "$u"; then
      echo "$u"
      return 0
    fi
  done
  return 1
}

noemaforge_list_llama_units() {
  systemctl list-units --all --type=service --no-legend 'noemaforge-llama@*.service' 2>/dev/null \
    | awk '{print $1}' \
    | grep -E '^noemaforge-llama@.+\.service$' \
    | sort -u || true
}
