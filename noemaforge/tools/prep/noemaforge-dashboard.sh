#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-dashboard.sh
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
# NoemaForge local dashboard launcher. Foreground serve plus background start/stop/status.
set -euo pipefail
ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
STATE_FROM_ENV="${NOEMAFORGE_PIPELINE_STATE+x}"
PERSONA_FROM_ENV="${NOEMAFORGE_PERSONA_STATE+x}"
EVOLUTION_FROM_ENV="${NOEMAFORGE_MODEL_EVOLUTION_STATE+x}"
STATE="${NOEMAFORGE_PIPELINE_STATE:-/var/lib/noemaforge/pipelines}"
PERSONA_STATE="${NOEMAFORGE_PERSONA_STATE:-/var/lib/noemaforge/personas}"
EVOLUTION_STATE="${NOEMAFORGE_MODEL_EVOLUTION_STATE:-/var/lib/noemaforge/model-evolution}"
PORT=8765
MODE="path"
OUT=""
usage(){ cat <<'USAGE'
Usage:
  noemaforge dashboard path
  noemaforge dashboard state [--out FILE]
  noemaforge dashboard serve [--port 8765]
  noemaforge dashboard start [--port 8765]
  noemaforge dashboard stop
  noemaforge dashboard status
  noemaforge dashboard autostart-enable [--port 8765] [--now] [--dry-run]
  noemaforge dashboard autostart-disable [--now] [--dry-run]
  noemaforge dashboard autostart-status

Writes dashboard-state JSON only to an operator-writable cache/output path and
serves the Admin GUI with a localhost JSON API. It does not start an LLM,
camera, microphone or media backend. Autostart commands use user-level systemd
units under XDG_CONFIG_HOME and never require root.
USAGE
}
action="${1:-path}"; shift || true
case "$action" in path|state|serve|start|stop|status|autostart-enable|autostart-disable|autostart-status) MODE="$action" ;; -h|--help|help) usage; exit 0 ;; *) echo "unknown dashboard action: $action" >&2; usage; exit 2 ;; esac
NOW=0
DRY_RUN=0
USER_UNIT_DIR="${NOEMAFORGE_SYSTEMD_USER_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --state) STATE="$2"; STATE_FROM_ENV=1; shift 2 ;;
    --persona-state) PERSONA_STATE="$2"; PERSONA_FROM_ENV=1; shift 2 ;;
    --evolution-state) EVOLUTION_STATE="$2"; EVOLUTION_FROM_ENV=1; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --unit-dir) USER_UNIT_DIR="$2"; shift 2 ;;
    --now) NOW=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
UI="$ROOT/templates/pipeline-dashboard"
[[ -d "$UI" ]] || { echo "missing dashboard UI: $UI" >&2; exit 1; }
RUNDIR="${XDG_STATE_HOME:-$HOME/.local/state}/noemaforge"
mkdir -p "$RUNDIR"
# For user-started GUI consoles, avoid failing on root-owned /var/lib/noemaforge.
# Explicit --state/env keeps its value; otherwise use an operator-writable cache.
if [[ -z "$STATE_FROM_ENV" && ! -w "$(dirname "$STATE")" ]]; then STATE="$RUNDIR/pipelines"; fi
if [[ -z "$PERSONA_FROM_ENV" && ! -w "$(dirname "$PERSONA_STATE")" ]]; then PERSONA_STATE="$RUNDIR/personas"; fi
if [[ -z "$EVOLUTION_FROM_ENV" && ! -w "$(dirname "$EVOLUTION_STATE")" ]]; then EVOLUTION_STATE="$RUNDIR/model-evolution"; fi
mkdir -p "$STATE" "$PERSONA_STATE" "$EVOLUTION_STATE"
DASHBOARD_AUTOSTART_SH="$RUNDIR/dashboard-autostart.sh"
DASHBOARD_SERVICE="$USER_UNIT_DIR/noemaforge-dashboard.service"
DASHBOARD_TIMER="$USER_UNIT_DIR/noemaforge-dashboard.timer"
write_user_autostart_units() {
  mkdir -p "$USER_UNIT_DIR" "$RUNDIR"
  {
    echo '#!/usr/bin/env bash'
    echo 'set -euo pipefail'
    printf 'exec %q serve --root %q --state %q --persona-state %q --evolution-state %q --port %q\n' \
      "$ROOT/tools/prep/noemaforge-dashboard.sh" "$ROOT" "$STATE" "$PERSONA_STATE" "$EVOLUTION_STATE" "$PORT"
  } > "$DASHBOARD_AUTOSTART_SH"
  chmod 700 "$DASHBOARD_AUTOSTART_SH"
  cat > "$DASHBOARD_SERVICE" <<SERVICE
[Unit]
Description=NoemaForge local Admin GUI dashboard (user)
Documentation=file://$ROOT/docs/operations/OPERATOR_GUIDE.md
After=default.target network-online.target

[Service]
Type=simple
ExecStart=$DASHBOARD_AUTOSTART_SH
Restart=on-failure
RestartSec=5

SERVICE
  cat > "$DASHBOARD_TIMER" <<TIMER
[Unit]
Description=Delay NoemaForge local Admin GUI dashboard autostart (user)

[Timer]
OnBootSec=30s
Unit=noemaforge-dashboard.service
Persistent=false

[Install]
WantedBy=timers.target

TIMER
}
systemctl_user_available() {
  command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1
}
case "$MODE" in
  path) echo "$UI" ;;
  state)
    [[ -n "$OUT" ]] || OUT="$RUNDIR/dashboard-state.json"
    python3 "$ROOT/src/pipeline_runtime.py" --root "$ROOT" --state "$STATE" dashboard-state --persona-state "$PERSONA_STATE" --out "$OUT" >/dev/null
    echo "$OUT"
    ;;
  serve)
    # Generate a cache snapshot for debugging when possible, but the browser uses
    # /api/state dynamically and does not require writes into the packaged UI dir.
    python3 "$ROOT/src/pipeline_runtime.py" --root "$ROOT" --state "$STATE" dashboard-state --persona-state "$PERSONA_STATE" --out "$RUNDIR/dashboard-state.json" >/dev/null || true
    exec python3 "$ROOT/src/admin_gui_server.py" --root "$ROOT" --state "$STATE" --persona-state "$PERSONA_STATE" --evolution-state "$EVOLUTION_STATE" --port "$PORT"
    ;;
  start)
    PIDFILE="$RUNDIR/dashboard.pid"
    LOGFILE="$RUNDIR/dashboard.log"
    if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "NoemaForge dashboard already running: pid=$(cat "$PIDFILE") http://127.0.0.1:$PORT/"
      exit 0
    fi
    nohup "$ROOT/tools/prep/noemaforge-dashboard.sh" serve --root "$ROOT" --state "$STATE" --persona-state "$PERSONA_STATE" --evolution-state "$EVOLUTION_STATE" --port "$PORT" >"$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"
    echo "NoemaForge dashboard started: pid=$(cat "$PIDFILE") http://127.0.0.1:$PORT/ log=$LOGFILE"
    ;;
  stop)
    PIDFILE="$RUNDIR/dashboard.pid"
    if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      kill "$(cat "$PIDFILE")" 2>/dev/null || true
      rm -f "$PIDFILE"
      echo "NoemaForge dashboard stopped"
    else
      pkill -f 'admin_gui_server.py .*--port' 2>/dev/null || true
      echo "NoemaForge dashboard not running"
    fi
    ;;
  status)
    PIDFILE="$RUNDIR/dashboard.pid"
    if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "NoemaForge dashboard running: pid=$(cat "$PIDFILE")"
    else
      echo "NoemaForge dashboard not running"
    fi
    ;;
  autostart-enable)
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "NoemaForge dashboard autostart dry-run: would write $DASHBOARD_SERVICE and $DASHBOARD_TIMER"
      echo "NoemaForge dashboard autostart dry-run: would run systemctl --user enable$([[ "$NOW" -eq 1 ]] && printf ' --now') noemaforge-dashboard.timer"
      exit 0
    fi
    write_user_autostart_units
    if systemctl_user_available; then
      systemctl --user daemon-reload
      cmd=(systemctl --user enable)
      [[ "$NOW" -eq 1 ]] && cmd+=(--now)
      cmd+=(noemaforge-dashboard.timer)
      "${cmd[@]}"
      echo "NoemaForge dashboard user autostart enabled: noemaforge-dashboard.timer"
    else
      echo "NoemaForge dashboard user units written: $USER_UNIT_DIR"
      echo "User systemd is not available in this shell; run: systemctl --user enable noemaforge-dashboard.timer"
    fi
    ;;
  autostart-disable)
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "NoemaForge dashboard autostart dry-run: would run systemctl --user disable$([[ "$NOW" -eq 1 ]] && printf ' --now') noemaforge-dashboard.timer"
      exit 0
    fi
    if systemctl_user_available; then
      cmd=(systemctl --user disable)
      [[ "$NOW" -eq 1 ]] && cmd+=(--now)
      cmd+=(noemaforge-dashboard.timer)
      "${cmd[@]}" 2>/dev/null || true
      systemctl --user daemon-reload || true
      echo "NoemaForge dashboard user autostart disabled: noemaforge-dashboard.timer"
    else
      echo "User systemd is not available in this shell; run: systemctl --user disable noemaforge-dashboard.timer"
    fi
    ;;
  autostart-status)
    if [[ -f "$DASHBOARD_TIMER" ]]; then
      echo "NoemaForge dashboard user timer file: $DASHBOARD_TIMER"
    else
      echo "NoemaForge dashboard user timer file not installed"
    fi
    if systemctl_user_available; then
      systemctl --user is-enabled noemaforge-dashboard.timer 2>/dev/null || true
      systemctl --user is-active noemaforge-dashboard.timer 2>/dev/null || true
    else
      echo "User systemd is not available in this shell"
    fi
    ;;
esac
