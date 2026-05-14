#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/prep/noemaforge-headless.sh
# Zone: prep/runtime
# Purpose: Softly switch the Debian host between graphical and headless NoemaForge runtime modes.
# Callers: bin/noemaforge, tools/prep/noemaforge-first-launch.sh, operator shell.
# Inputs: on|off|status, optional --reason, optional --no-stop-display-manager.
# Outputs: human-readable status and /var/lib/noemaforge/bootstrap/headless-mode.json.
# Safety notes:
#   - Does not uninstall GNOME or display-manager packages.
#   - Uses systemctl set-default multi-user.target plus display-manager stop for soft headless mode.
#   - Restores the previously saved default target, falling back to graphical.target.
# === End NoemaForge File Header ===
set -euo pipefail

STATE_DIR="/var/lib/noemaforge/bootstrap"
SAVED_DEFAULT="$STATE_DIR/display-default-target.before-headless"
STATE_JSON="$STATE_DIR/headless-mode.json"
REASON="manual"
STOP_DISPLAY_MANAGER="1"

usage() {
  cat <<'EOF'
Usage:
  noemaforge-headless.sh on [--reason TEXT] [--no-stop-display-manager]
  noemaforge-headless.sh off
  noemaforge-headless.sh status

Soft headless mode means: keep GNOME installed, set the default boot target to
multi-user.target, and stop display-manager.service for the current boot.
EOF
}

log(){ printf '[noemaforge-headless] %s\n' "$*"; }
fail(){ printf '[noemaforge-headless][ERROR] %s\n' "$*" >&2; exit 1; }
require_root(){ [[ $EUID -eq 0 ]] || fail "Run with sudo."; }

write_state() {
  local mode="$1"
  local default_target=""
  local dm_state=""
  default_target="$(systemctl get-default 2>/dev/null || true)"
  dm_state="$(systemctl is-active display-manager.service 2>/dev/null || systemctl is-active gdm.service 2>/dev/null || true)"
  install -d -m 0755 "$STATE_DIR"
  python3 - "$STATE_JSON" "$mode" "$REASON" "$default_target" "$dm_state" <<'PY'
import json, sys, datetime
path, mode, reason, default_target, dm_state = sys.argv[1:]
obj = {
  "mode": mode,
  "reason": reason,
  "default_target": default_target,
  "display_manager_state": dm_state,
  "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(obj, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY
}

cmd_status() {
  echo "default_target=$(systemctl get-default 2>/dev/null || true)"
  echo "display_manager=$(systemctl is-active display-manager.service 2>/dev/null || systemctl is-active gdm.service 2>/dev/null || true)"
  if [[ -f "$SAVED_DEFAULT" ]]; then
    echo "saved_default=$(cat "$SAVED_DEFAULT")"
  else
    echo "saved_default="
  fi
  if [[ -f "$STATE_JSON" ]]; then
    cat "$STATE_JSON"
  fi
}

cmd_on() {
  require_root
  install -d -m 0755 "$STATE_DIR"
  local current_default=""
  current_default="$(systemctl get-default 2>/dev/null || echo graphical.target)"
  if [[ ! -s "$SAVED_DEFAULT" && "$current_default" != "multi-user.target" ]]; then
    printf '%s\n' "$current_default" >"$SAVED_DEFAULT"
  fi

  log "Saving previous default target: $(cat "$SAVED_DEFAULT" 2>/dev/null || echo "$current_default")"
  log "Setting default boot target to multi-user.target. GNOME remains installed."
  systemctl set-default multi-user.target >/dev/null

  if [[ "$STOP_DISPLAY_MANAGER" == "1" ]]; then
    if systemctl list-unit-files display-manager.service >/dev/null 2>&1 || systemctl status display-manager.service >/dev/null 2>&1; then
      log "Stopping display-manager.service for this boot. Active SSH/TTY/system services continue."
      systemctl stop display-manager.service 2>/dev/null || true
    else
      log "display-manager.service not found; nothing to stop."
    fi
  else
    log "Leaving display-manager.service running because --no-stop-display-manager was used."
  fi
  write_state "headless"
  log "Soft headless mode is active. To restore GUI: sudo noemaforge headless off"
}

cmd_off() {
  require_root
  local target="graphical.target"
  if [[ -s "$SAVED_DEFAULT" ]]; then
    target="$(cat "$SAVED_DEFAULT")"
  fi
  if [[ -z "$target" || "$target" == "multi-user.target" ]]; then
    target="graphical.target"
  fi
  log "Restoring default boot target: $target"
  systemctl daemon-reload 2>/dev/null || true
  systemctl reset-failed 2>/dev/null || true
  systemctl set-default "$target" >/dev/null || systemctl set-default graphical.target >/dev/null
  log "Starting display-manager/GDM with non-blocking emergency-safe order."
  systemctl start --no-block systemd-user-sessions.service 2>/dev/null || true
  rm -f /run/nologin 2>/dev/null || true
  systemctl start --no-block display-manager.service 2>/dev/null || true
  systemctl start --no-block gdm.service 2>/dev/null || true
  systemctl start --no-block gdm3.service 2>/dev/null || true
  write_state "graphical"
  log "GUI restore requested. If GUI is not back in 30 seconds: systemctl reboot"
  cmd_status
}

[[ $# -ge 1 ]] || { usage; exit 2; }
cmd="$1"; shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reason) REASON="$2"; shift 2 ;;
    --no-stop-display-manager) STOP_DISPLAY_MANAGER="0"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

case "$cmd" in
  on) cmd_on ;;
  off) cmd_off ;;
  status) cmd_status ;;
  *) usage; exit 2 ;;
esac
