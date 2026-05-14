#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-boot-mode.sh
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
# NoemaForge 0.31.13.alpha boot/autostart mode and profile manager.
set -euo pipefail
MODE_FILE="${NOEMAFORGE_BOOT_MODE_FILE:-/etc/noemaforge/boot-mode}"
PROFILE_DIR="${NOEMAFORGE_AUTOSTART_PROFILE_DIR:-/etc/noemaforge}"
ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
ACTION="${1:-show}"; shift || true
JSON=0
APPLY=0
DRY_RUN=0
MODE=""
PROFILE=""

usage(){ cat <<'USAGE'
Usage:
  noemaforge boot-mode show [--json]
  noemaforge boot-mode status [--json]
  sudo noemaforge boot-mode set manual|gui|wogui [--apply-systemd] [--dry-run]
  sudo noemaforge boot-mode set-profile gui|wogui runtime_only|bootstrap_cpu_llm
  sudo noemaforge boot-mode install-units [--dry-run]

Semantics:
  manual: no runtime autostart.
  gui:    Debian GUI remains normal; NoemaForge runtime starts later via timer.
          Default profile: runtime_only = gateway/toolproxy/dashboard support, no LLM.
          Optional profile: bootstrap_cpu_llm.
  wogui:  NoemaForge runtime starts under multi-user target instead of GUI.
          Default profile: bootstrap_cpu_llm.
  heavy:  Heavy LLM autostart is disabled; start manually/explicitly.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) JSON=1; shift ;;
    --apply-systemd|--enable-autostart|--enable) APPLY=1; shift ;;
    --dry-run|--plan) DRY_RUN=1; shift ;;
    -h|--help|help|"?") usage; exit 0 ;;
    manual|gui|wogui) [[ -z "$MODE" ]] && MODE="$1" || PROFILE="$1"; shift ;;
    runtime_only|runtime-only|no_llm|no-llm) PROFILE="runtime_only"; shift ;;
    bootstrap_cpu_llm|bootstrap-cpu-llm|bootstrap|cpu) PROFILE="bootstrap_cpu_llm"; shift ;;
    heavy|heavy_llm|gpu-heavy) echo "[noemaforge-boot-mode][ERROR] heavy LLM autostart is disabled; use manual start" >&2; exit 2 ;;
    *) echo "[noemaforge-boot-mode][ERROR] unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

read_mode(){ [[ -r "$MODE_FILE" ]] && tr -d '[:space:]' < "$MODE_FILE" || printf 'manual'; }
default_profile(){ case "$1" in gui) printf 'runtime_only' ;; wogui) printf 'bootstrap_cpu_llm' ;; *) printf 'none' ;; esac; }
profile_file(){ printf '%s/autostart-%s-profile' "$PROFILE_DIR" "$1"; }
read_profile(){ local m="$1" f; f="$(profile_file "$m")"; [[ -r "$f" ]] && tr -d '[:space:]' < "$f" || default_profile "$m"; }
unit_enabled(){ local out; out="$(systemctl is-enabled "$1" 2>/dev/null || true)"; case "$out" in enabled|disabled|static|masked|indirect|generated|linked|alias) printf '%s\n' "$out" ;; *) printf 'disabled\n' ;; esac; }

json_msg(){ python3 - "$@" <<'PY'
import json, sys
print(json.dumps({"ok": sys.argv[1] == "true", "mode": sys.argv[2], "message": sys.argv[3]}, ensure_ascii=False, indent=2))
PY
}
write_mode(){
  local mode="$1"
  case "$mode" in manual|gui|wogui) : ;; *) echo "bad mode: $mode" >&2; exit 2 ;; esac
  if [[ "$DRY_RUN" == 1 ]]; then echo "write $MODE_FILE = $mode"; else install -d -m 0755 "$(dirname "$MODE_FILE")"; printf '%s\n' "$mode" > "$MODE_FILE"; chmod 0644 "$MODE_FILE"; fi
}
write_profile(){
  local mode="$1" profile="$2" f
  case "$mode" in gui|wogui) : ;; *) echo "profile mode must be gui|wogui" >&2; exit 2 ;; esac
  case "$profile" in runtime_only|bootstrap_cpu_llm) : ;; *) echo "bad profile: $profile" >&2; exit 2 ;; esac
  f="$(profile_file "$mode")"
  if [[ "$DRY_RUN" == 1 ]]; then echo "write $f = $profile"; else install -d -m 0755 "$PROFILE_DIR"; printf '%s\n' "$profile" > "$f"; chmod 0644 "$f"; fi
}
install_units(){
  local srcdir="$ROOT/../systemd"
  [[ -d "$srcdir" ]] || srcdir="$ROOT/systemd"
  [[ -d "$srcdir" ]] || srcdir="/opt/systemd"
  [[ -d "$srcdir" ]] || srcdir="$(cd "$(dirname "$0")/../../.." 2>/dev/null && pwd)/systemd"
  for u in noemaforge-autostart-gui.service noemaforge-autostart-gui.timer noemaforge-autostart-wogui.service; do
    [[ -f "$srcdir/$u" ]] || continue
    if [[ "$DRY_RUN" == 1 ]]; then echo "install systemd/$u -> /etc/systemd/system/$u"; else install -D -m 0644 "$srcdir/$u" "/etc/systemd/system/$u"; fi
  done
  if [[ "$DRY_RUN" != 1 ]]; then systemctl daemon-reload || true; fi
}
apply_systemd(){
  local mode="$1"
  install_units
  case "$mode" in
    gui)
      if [[ "$DRY_RUN" == 1 ]]; then
        echo "systemctl set-default graphical.target"
        echo "systemctl disable noemaforge-autostart-gui.service noemaforge-autostart-wogui.service"
        echo "systemctl enable --now noemaforge-autostart-gui.timer"
      else
        systemctl set-default graphical.target || true
        systemctl disable noemaforge-autostart-gui.service noemaforge-autostart-wogui.service 2>/dev/null || true
        systemctl disable noemaforge-autostart-wogui.timer 2>/dev/null || true
        systemctl enable --now noemaforge-autostart-gui.timer || true
      fi ;;
    wogui)
      if [[ "$DRY_RUN" == 1 ]]; then
        echo "systemctl set-default multi-user.target"
        echo "systemctl enable noemaforge-autostart-wogui.service"
        echo "systemctl disable noemaforge-autostart-gui.service noemaforge-autostart-gui.timer"
      else
        systemctl set-default multi-user.target || true
        systemctl disable --now noemaforge-autostart-gui.timer 2>/dev/null || true
        systemctl disable noemaforge-autostart-gui.service 2>/dev/null || true
        systemctl enable noemaforge-autostart-wogui.service || true
      fi ;;
    manual)
      if [[ "$DRY_RUN" == 1 ]]; then
        echo "systemctl disable --now noemaforge-autostart-gui.timer"
        echo "systemctl disable noemaforge-autostart-gui.service noemaforge-autostart-wogui.service"
      else
        systemctl disable --now noemaforge-autostart-gui.timer 2>/dev/null || true
        systemctl disable noemaforge-autostart-gui.service noemaforge-autostart-wogui.service 2>/dev/null || true
      fi ;;
  esac
}
status(){
  local mode; mode="$(read_mode)"
  local gui_service gui_timer wogui_service target
  gui_service="$(unit_enabled noemaforge-autostart-gui.service)"
  gui_timer="$(unit_enabled noemaforge-autostart-gui.timer)"
  wogui_service="$(unit_enabled noemaforge-autostart-wogui.service)"
  target="$(systemctl get-default 2>/dev/null || true)"
  if [[ "$JSON" == 1 ]]; then
    python3 - "$mode" "$gui_service" "$gui_timer" "$wogui_service" "$target" "$(read_profile gui)" "$(read_profile wogui)" <<'PY'
import json, sys
print(json.dumps({
  "ok": True,
  "mode": sys.argv[1],
  "mode_file": "/etc/noemaforge/boot-mode",
  "units": {"gui_service": sys.argv[2], "gui_timer": sys.argv[3], "wogui": sys.argv[4]},
  "default_target": sys.argv[5],
  "profiles": {"gui": sys.argv[6], "wogui": sys.argv[7]},
  "policy": {"gui_default": "runtime_only", "gui_start": "delayed_timer_nonblocking", "wogui_default": "bootstrap_cpu_llm", "heavy_llm_autostart": "manual_only"}
}, ensure_ascii=False, indent=2))
PY
  else
    echo "NoemaForge boot mode: $mode"
    echo
    echo "Systemd autostart:"
    printf '  gui timer:    '; printf '%s\n' "$gui_timer"
    printf '  gui service:  '; printf '%s\n' "$gui_service"
    printf '  wogui:        '; printf '%s\n' "$wogui_service"
    echo
    echo "Autostart profiles:"
    printf '  gui:   '; read_profile gui; echo
    printf '  wogui: '; read_profile wogui; echo
    echo
    echo "Default target:"
    printf '  '; printf '%s\n' "$target"
    echo
    echo "Policy:"
    echo "  GUI mode: delayed timer after boot; runtime/toolproxy allowed; no LLM by default."
    echo "  GUI timer skip is diagnostic/non-fatal if GDM is not ready."
    echo "  woGUI mode: CPU bootstrap LLM allowed; heavy LLM manual-only."
  fi
}

case "$ACTION" in
  show|status) status ;;
  set)
    [[ -n "$MODE" ]] || { echo "mode required: manual|gui|wogui" >&2; exit 2; }
    write_mode "$MODE"
    [[ "$APPLY" == 1 ]] && apply_systemd "$MODE"
    [[ "$JSON" == 1 ]] && json_msg true "$MODE" "mode set" || echo "NoemaForge boot mode set: $MODE" ;;
  set-profile|profile)
    [[ -n "$MODE" && -n "$PROFILE" ]] || { echo "usage: noemaforge boot-mode set-profile gui|wogui runtime_only|bootstrap_cpu_llm" >&2; exit 2; }
    write_profile "$MODE" "$PROFILE"
    [[ "$JSON" == 1 ]] && json_msg true "$MODE" "profile set: $PROFILE" || echo "NoemaForge $MODE autostart profile set: $PROFILE" ;;
  install-units)
    install_units
    [[ "$JSON" == 1 ]] && json_msg true "$(read_mode)" "units installed" || echo "NoemaForge autostart units installed" ;;
  -h|--help|help|"?") usage ;;
  *) echo "[noemaforge-boot-mode][ERROR] unknown action: $ACTION" >&2; usage; exit 2 ;;
esac
