#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-autostart-safe.sh
# Zone: release/package
# Version: 0.32.1
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Provide NoemaForge release functionality for the packaged local runtime.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
# NoemaForge 0.32.1 conditional safe autostart gate.
# GUI mode is timer-driven and non-blocking: if GUI is not ready, record skip and exit 0 by default.
# GUI default profile: runtime/toolproxy only, no automatic LLM. Heavy LLM is manual-only.
set -euo pipefail

MODE="auto"
PROFILE="auto"
DRY_RUN=0
JSON=0
WAIT_GUI_SECONDS="${NOEMAFORGE_AUTOSTART_WAIT_GUI_SECONDS:-90}"
MIN_AVAILABLE_GB="${NOEMAFORGE_MIN_AVAILABLE_GB:-4}"
ALLOW_GUI_RUNNING=0
SKIP_HEALTH_WAIT=0
RESTART=0
STRICT_GUI_WAIT="${NOEMAFORGE_AUTOSTART_STRICT_GUI_WAIT:-0}"
CONFIG="${NOEMAFORGE_BOOT_MODE_FILE:-/etc/noemaforge/boot-mode}"
PROFILE_DIR="${NOEMAFORGE_AUTOSTART_PROFILE_DIR:-/etc/noemaforge}"
RUNTIME_DIR="${NOEMAFORGE_RUNTIME_DIR:-/var/lib/noemaforge/runtime}"
NOEMAFORGE_CLI="${NOEMAFORGE_CLI:-/opt/noemaforge/bin/noemaforge}"
[[ -x "$NOEMAFORGE_CLI" ]] || NOEMAFORGE_CLI="/usr/local/sbin/noemaforge"

usage(){ cat <<'USAGE'
Usage: sudo noemaforge-autostart-safe.sh [--mode gui|wogui|auto] [options]

Options:
  --mode MODE                 gui, wogui, auto. auto reads /etc/noemaforge/boot-mode.
  --profile PROFILE           auto|runtime_only|bootstrap_cpu_llm.
  --llm-profile PROFILE       Alias for --profile.
  --runtime-only|--no-llm     Alias for --profile runtime_only.
  --bootstrap-cpu-llm         Alias for --profile bootstrap_cpu_llm.
  --wait-gui-seconds N        GUI wait window after timer fires; default 90.
  --strict-gui-wait           Fail if GUI/display-manager is not ready after wait.
  --nonfatal-gui-wait         Record skip and exit 0 if GUI is not ready. Default.
  --min-available-gb N        Passed to safe-start memory gate; default 4.
  --restart                   Force safe-start restart of allowed main backend.
  --no-health-wait            Do not wait for backend health in safe-start.
  --allow-gui-running         In wogui mode, do not block if display-manager is active.
  --dry-run                   Show plan only.
  --json                      Emit JSON result/plan.

Mode/profile semantics:
  manual -> no autostart.
  gui    -> default runtime_only: UI/runtime + ToolProxy, no LLM.
            GUI service is intended to be run by timer, not as graphical.target dependency.
  wogui  -> default bootstrap_cpu_llm: CPU bootstrap LLM allowed.
  heavy  -> never auto; start manually with explicit operator command.
USAGE
}

json_escape(){ python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'; }
emit_json(){
  local ok="$1" msg="$2" mode="$3" profile="$4" status="${5:-ok}"
  printf '{"ok":%s,"mode":"%s","profile":"%s","status":"%s","message":%s}\n' "$ok" "$mode" "$profile" "$status" "$(printf '%s' "$msg" | json_escape)"
}
log(){ [[ "$JSON" == 1 ]] || printf '[noemaforge-autostart] %s\n' "$*"; }
fail(){ local msg="$1" rc="${2:-1}"; if [[ "$JSON" == 1 ]]; then emit_json false "$msg" "$MODE" "$PROFILE" fail; else printf '[noemaforge-autostart][ERROR] %s\n' "$msg" >&2; fi; exit "$rc"; }

write_status(){
  local status="$1" msg="$2"
  mkdir -p "$RUNTIME_DIR" 2>/dev/null || true
  python3 - "$RUNTIME_DIR/autostart-${MODE}-last.json" "$status" "$MODE" "$PROFILE" "$msg" <<'PY' 2>/dev/null || true
import json, sys, datetime
path, status, mode, profile, msg = sys.argv[1:]
with open(path, 'w', encoding='utf-8') as f:
    json.dump({"apiVersion":"noemaforge/v1","kind":"AutostartAttempt","ts":datetime.datetime.now(datetime.UTC).isoformat(),"status":status,"mode":mode,"profile":profile,"message":msg}, f, ensure_ascii=False, indent=2)
    f.write('\n')
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --mode=*) MODE="${1#*=}"; shift ;;
    --profile|--llm-profile) PROFILE="$2"; shift 2 ;;
    --profile=*|--llm-profile=*) PROFILE="${1#*=}"; shift ;;
    --runtime-only|--no-llm) PROFILE="runtime_only"; shift ;;
    --bootstrap-cpu-llm|--cpu-bootstrap) PROFILE="bootstrap_cpu_llm"; shift ;;
    --wait-gui-seconds) WAIT_GUI_SECONDS="$2"; shift 2 ;;
    --wait-gui-seconds=*) WAIT_GUI_SECONDS="${1#*=}"; shift ;;
    --strict-gui-wait) STRICT_GUI_WAIT=1; shift ;;
    --nonfatal-gui-wait) STRICT_GUI_WAIT=0; shift ;;
    --min-available-gb) MIN_AVAILABLE_GB="$2"; shift 2 ;;
    --min-available-gb=*) MIN_AVAILABLE_GB="${1#*=}"; shift ;;
    --restart) RESTART=1; shift ;;
    --no-health-wait) SKIP_HEALTH_WAIT=1; shift ;;
    --allow-gui-running) ALLOW_GUI_RUNNING=1; shift ;;
    --dry-run|--plan) DRY_RUN=1; shift ;;
    --json) JSON=1; shift ;;
    -h|--help|help|"?") usage; exit 0 ;;
    *) fail "unknown option: $1" 2 ;;
  esac
done

if [[ "$MODE" == "auto" ]]; then
  if [[ -r "$CONFIG" ]]; then MODE="$(tr -d '[:space:]' < "$CONFIG")"; else MODE="manual"; fi
fi
case "$MODE" in
  manual|off|disabled) log "mode=manual; no autostart"; write_status skipped "manual mode; no autostart"; [[ "$JSON" == 1 ]] && emit_json true "manual mode; no autostart" manual none skipped; exit 0 ;;
  gui|wogui) : ;;
  *) fail "unsupported boot mode: $MODE" 2 ;;
esac

default_profile(){ case "$1" in gui) printf 'runtime_only' ;; wogui) printf 'bootstrap_cpu_llm' ;; *) printf 'runtime_only' ;; esac; }
read_profile(){
  local mode="$1"
  local f="$PROFILE_DIR/autostart-${mode}-profile"
  if [[ -r "$f" ]]; then tr -d '[:space:]' < "$f"; else default_profile "$mode"; fi
}

if [[ "$PROFILE" == "auto" ]]; then PROFILE="$(read_profile "$MODE")"; fi
case "$PROFILE" in
  runtime_only|bootstrap_cpu_llm) : ;;
  heavy|gpu_heavy|heavy_llm|heavy_manual)
    fail "heavy LLM autostart is disabled; start heavy backends manually" 1 ;;
  *) fail "unsupported autostart profile: $PROFILE" 2 ;;
esac

safe_args=(safe-start --wait --skip-if-running "--min-available-gb=${MIN_AVAILABLE_GB}")
case "$PROFILE" in
  runtime_only) safe_args+=(--llm-profile=runtime_only --no-health-wait) ;;
  bootstrap_cpu_llm) safe_args+=(--llm-profile=bootstrap_cpu_llm) ;;
esac
[[ "$RESTART" == 1 ]] && safe_args+=(--restart)
[[ "$SKIP_HEALTH_WAIT" == 1 ]] && safe_args+=(--no-health-wait)

if [[ "$DRY_RUN" == 1 ]]; then
  log "dry-run plan: mode=$MODE profile=$PROFILE noemaforge ${safe_args[*]}"
  [[ "$JSON" == 1 ]] && emit_json true "dry-run: safe-start not executed" "$MODE" "$PROFILE" dry_run
  exit 0
fi

is_active(){ systemctl is-active --quiet "$1" 2>/dev/null; }
proc_exists(){ pgrep -x "$1" >/dev/null 2>&1; }
any_display_active(){
  is_active display-manager.service || is_active gdm.service || is_active gdm3.service || proc_exists gdm || proc_exists gdm3 || proc_exists Xorg || proc_exists gnome-shell
}
gui_probe_text(){
  printf 'display-manager=%s gdm=%s gdm3=%s Xorg=%s gnome-shell=%s' \
    "$(systemctl is-active display-manager.service 2>/dev/null || true)" \
    "$(systemctl is-active gdm.service 2>/dev/null || true)" \
    "$(systemctl is-active gdm3.service 2>/dev/null || true)" \
    "$(pgrep -x Xorg >/dev/null 2>&1 && echo yes || echo no)" \
    "$(pgrep -x gnome-shell >/dev/null 2>&1 && echo yes || echo no)"
}

if [[ "$MODE" == "gui" ]]; then
  log "GUI mode: timer-driven wait for GUI readiness before safe-start. profile=$PROFILE"
  deadline=$((SECONDS + WAIT_GUI_SECONDS))
  until any_display_active || [[ "$SECONDS" -ge "$deadline" ]]; do sleep 2; done
  if ! any_display_active; then
    msg="GUI mode requested but GUI/display-manager is not ready after ${WAIT_GUI_SECONDS}s; $(gui_probe_text). Skipping NoemaForge runtime autostart for this boot. Run 'noemaforge gui-diagnose' and start manually if needed."
    if [[ "$STRICT_GUI_WAIT" == 1 ]]; then
      fail "$msg" 1
    else
      log "WARN: $msg"
      write_status skipped "$msg"
      [[ "$JSON" == 1 ]] && emit_json true "$msg" "$MODE" "$PROFILE" skipped
      exit 0
    fi
  fi
elif [[ "$MODE" == "wogui" ]]; then
  log "woGUI mode: safe-start under multi-user/headless runtime. profile=$PROFILE"
  if any_display_active && [[ "$ALLOW_GUI_RUNNING" != 1 ]]; then
    fail "woGUI mode requested but GUI/display-manager is active; use 'noemaforge boot-mode set wogui --apply-systemd' then reboot, or pass --allow-gui-running for a manual exception" 1
  fi
fi

log "policy: mode=$MODE llm_profile=$PROFILE heavy_llm=manual_only max_active_llms=1"
log "plan: noemaforge ${safe_args[*]}"
write_status starting "starting safe-start"
"$NOEMAFORGE_CLI" "${safe_args[@]}"
rc=$?
if [[ "$rc" == 0 ]]; then write_status success "safe-start completed"; else write_status failed "safe-start failed rc=$rc"; fi
exit "$rc"
