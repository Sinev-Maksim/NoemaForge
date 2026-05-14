#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/prep/noemaforge-gui-recover-minimal.sh
# Zone: prep/recovery
# Purpose: Minimal emergency-safe Debian GUI recovery path after first-start/headless/composite runs.
# Callers: noemaforge first-start abort, noemaforge-first-launch trap/exit, recovery shell.
# Safety: Does not call high-level headless wrappers first; uses non-blocking systemd actions.
# === End NoemaForge File Header ===
set -euo pipefail

REASON="manual"
DO_ISOLATE="1"
DRY_RUN="0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reason) REASON="${2:-manual}"; shift 2 ;;
    --no-isolate) DO_ISOLATE="0"; shift ;;
    --dry-run) DRY_RUN="1"; shift ;;
    -h|--help|help)
      cat <<'HELP'
Usage: sudo noemaforge-gui-recover-minimal.sh [--reason TEXT] [--no-isolate] [--dry-run]

Emergency-safe GUI recovery order:
  1. daemon-reload/reset-failed
  2. set-default graphical.target
  3. start --no-block systemd-user-sessions.service
  4. remove /run/nologin
  5. start --no-block display-manager.service
  6. start --no-block gdm.service and gdm3.service
  7. isolate --no-block graphical.target unless --no-isolate

This intentionally avoids using `noemaforge headless off` as the first recovery step.
HELP
      exit 0 ;;
    *) echo "[noemaforge-gui-recover][ERROR] unknown argument: $1" >&2; exit 2 ;;
  esac
done

log(){ printf '[noemaforge-gui-recover] %s\n' "$*"; }
need_root(){ [[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "[noemaforge-gui-recover][ERROR] Run as root." >&2; exit 1; }; }
run(){ log "run: $*"; [[ "$DRY_RUN" == "1" ]] || "$@"; }

need_root
log "reason=${REASON}; minimal non-blocking Debian GUI recovery"

# Best effort only; recovery must never hang on remount/loadkeys/systemd details.
mount -o remount,rw / 2>/dev/null || true
loadkeys us 2>/dev/null || true

run systemctl daemon-reload || true
run systemctl reset-failed || true
run systemctl set-default graphical.target || true
run systemctl start --no-block systemd-user-sessions.service || true
[[ "$DRY_RUN" == "1" ]] || rm -f /run/nologin 2>/dev/null || true

# Order matters in emergency mode: display-manager alias first, then explicit gdm.
run systemctl start --no-block display-manager.service || true
run systemctl start --no-block gdm.service || true
run systemctl start --no-block gdm3.service || true
run systemctl start --no-block graphical.target || true
if [[ "$DO_ISOLATE" == "1" ]]; then
  run systemctl isolate --no-block graphical.target || true
fi

install -d -m 0755 /var/lib/noemaforge/bootstrap 2>/dev/null || true
if [[ "$DRY_RUN" != "1" ]]; then
  python3 - "$REASON" <<'PY' 2>/dev/null || true
import json, datetime, sys
reason=sys.argv[1]
path='/var/lib/noemaforge/bootstrap/headless-mode.json'
obj={
  'mode':'graphical',
  'reason':reason,
  'default_target':'graphical.target',
  'display_manager_state':'start-requested-no-block',
  'updated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
  'recovery':'minimal-gui-recover',
}
with open(path,'w',encoding='utf-8') as f:
    json.dump(obj,f,ensure_ascii=False,indent=2); f.write('\n')
PY
fi

log "GUI recovery requested. If GUI is not back in ~30s, run: systemctl reboot"
log "status: default=$(systemctl get-default 2>/dev/null || true) dm=$(systemctl is-active display-manager.service 2>/dev/null || systemctl is-active gdm.service 2>/dev/null || true)"
