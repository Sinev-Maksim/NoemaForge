#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-recursion-audit.sh
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
# NoemaForge 0.32.1 release/installed recursion audit.
# Static checks for setup/installer/wrapper/systemd self-call loops.
set -euo pipefail

TARGET="${1:-}"
JSON=0
if [[ "${TARGET:-}" == "--json" ]]; then JSON=1; TARGET="${2:-}"; fi
if [[ -z "$TARGET" ]]; then TARGET="$(pwd)"; fi
TARGET="$(cd "$TARGET" && pwd)"
PROBLEMS=()
WARNINGS=()
add_problem(){ PROBLEMS+=("$*"); }
add_warning(){ WARNINGS+=("$*"); }

# Detect package layout vs installed /opt/noemaforge layout.
LAYOUT="unknown"
if [[ -e "$TARGET/noemaforge/bin/noemaforge" ]]; then
  LAYOUT="package"
  CLI_REL="noemaforge/bin/noemaforge"
  PREP_REL="noemaforge/tools/prep"
  SYS_DIR="$TARGET/noemaforge/systemd"
  GUI_SERVICE="$SYS_DIR/noemaforge-autostart-gui.service"
  GUI_TIMER="$SYS_DIR/noemaforge-autostart-gui.timer"
  VERSION_FILE="$TARGET/VERSION"
elif [[ -e "$TARGET/bin/noemaforge" ]]; then
  LAYOUT="installed"
  CLI_REL="bin/noemaforge"
  PREP_REL="tools/prep"
  GUI_SERVICE="/etc/systemd/system/noemaforge-autostart-gui.service"
  GUI_TIMER="/etc/systemd/system/noemaforge-autostart-gui.timer"
  VERSION_FILE="$TARGET/VERSION"
else
  LAYOUT="unknown"
  CLI_REL="noemaforge/bin/noemaforge"
  PREP_REL="noemaforge/tools/prep"
  GUI_SERVICE="$TARGET/noemaforge/systemd/noemaforge-autostart-gui.service"
  GUI_TIMER="$TARGET/noemaforge/systemd/noemaforge-autostart-gui.timer"
  VERSION_FILE="$TARGET/VERSION"
fi

have(){ [[ -e "$TARGET/$1" || -L "$TARGET/$1" ]]; }
file_contains(){ local f="$1" pat="$2"; [[ -f "$f" ]] && grep -Eq "$pat" "$f"; }

CUR_VER="unknown"
[[ -r "$VERSION_FILE" ]] && CUR_VER="$(tr -d '[:space:]' < "$VERSION_FILE")"

# Layout-specific required files.
if [[ "$LAYOUT" == "package" ]]; then
  for f in setup.sh "$CLI_REL" noemaforge/systemd/noemaforge-autostart-gui.service noemaforge/systemd/noemaforge-autostart-gui.timer; do
    have "$f" || add_problem "missing required package file: $f"
  done
  installer="$TARGET/install_noemaforge_${CUR_VER}_mvp.sh"
  if [[ ! -f "$installer" ]]; then
    add_problem "missing current installer: install_noemaforge_${CUR_VER}_mvp.sh"
    installer="$(find "$TARGET" -maxdepth 1 -type f -name 'install_noemaforge_*_mvp.sh' | sort | tail -1 || true)"
  fi
  installer_rel="${installer#$TARGET/}"
  if have setup.sh; then
    grep -q 'NOEMAFORGE_SETUP_DEPTH' "$TARGET/setup.sh" || add_problem "setup.sh lacks NOEMAFORGE_SETUP_DEPTH recursion guard"
    grep -Eq 'exec[[:space:]]+"?\$PKG_DIR/install_noemaforge_.*_mvp\.sh' "$TARGET/setup.sh" || add_warning "setup.sh does not exec the real installer in the expected form"
  fi
  if [[ -n "$installer" && -f "$installer" ]]; then
    if grep -En '(^|[[:space:]])exec[[:space:]]+.*setup\.sh|setup\.sh.*\$@|setup\.sh.*"\$@"|setup\.sh.*"\$@"' "$installer" >/dev/null; then
      add_problem "$installer_rel contains setup.sh exec/wrapper pattern"
    fi
    if awk '/for h in / && / noemaforge( |$)/ { found=1 } END { exit found?0:1 }' "$installer"; then
      add_problem "$installer_rel installs helpers/noemaforge before symlink; public noemaforge wrapper recursion risk"
    fi
    grep -q '/opt/noemaforge/bin/noemaforge /usr/local/sbin/noemaforge' "$installer" || add_warning "$installer_rel does not explicitly symlink /usr/local/sbin/noemaforge to /opt/noemaforge/bin/noemaforge"
    grep -q '/opt/noemaforge/bin/noemaforge /usr/local/bin/noemaforge' "$installer" || add_warning "$installer_rel does not explicitly symlink /usr/local/bin/noemaforge to /opt/noemaforge/bin/noemaforge"
  fi
else
  # Installed layout: setup/installer may not exist under /opt/noemaforge. Public paths must resolve to canonical CLI.
  [[ -e "$TARGET/$CLI_REL" ]] || add_problem "missing installed canonical CLI: $TARGET/$CLI_REL"
  for p in /usr/local/bin/noemaforge /usr/local/sbin/noemaforge /usr/bin/noemaforge /bin/noemaforge; do
    if [[ -e "$p" || -L "$p" ]]; then
      r="$(readlink -f "$p" 2>/dev/null || true)"
      [[ "$r" == "$TARGET/$CLI_REL" ]] || add_problem "public noemaforge path $p resolves to $r, expected $TARGET/$CLI_REL"
    fi
  done
fi

# Canonical CLI must be implementation, not wrapper to public noemaforge.
CLI="$TARGET/$CLI_REL"
if [[ -f "$CLI" ]]; then
  if grep -Eq 'exec[[:space:]]+/usr/local/(sbin|bin)/noemaforge([[:space:]]|$)|exec[[:space:]]+noemaforge([[:space:]]|$)' "$CLI"; then
    add_problem "$CLI_REL appears to delegate to public noemaforge wrapper"
  fi
  grep -q 'cmd_gui_start' "$CLI" || add_problem "$CLI_REL lacks native cmd_gui_start"
  grep -q 'NOEMAFORGE_SELF_CANDIDATE' "$CLI" || add_warning "$CLI_REL lacks canonical NOEMAFORGE_SELF_CANDIDATE guard"
fi

# GUI service should be timer-triggered only: no Install/WantedBy=graphical.target.
if [[ -f "$GUI_SERVICE" ]]; then
  if grep -Eq '^\[Install\]|WantedBy=graphical\.target|WantedBy=multi-user\.target' "$GUI_SERVICE"; then
    add_problem "noemaforge-autostart-gui.service has direct install target; GUI autostart must be timer-based/static"
  fi
  grep -q -- '--nonfatal-gui-wait' "$GUI_SERVICE" || add_warning "GUI autostart service does not use --nonfatal-gui-wait"
else
  add_warning "GUI autostart service not found at $GUI_SERVICE"
fi
if [[ -f "$GUI_TIMER" ]]; then
  grep -q 'WantedBy=timers.target' "$GUI_TIMER" || add_problem "GUI timer is not enabled via timers.target"
  grep -q 'Unit=noemaforge-autostart-gui.service' "$GUI_TIMER" || add_problem "GUI timer does not trigger noemaforge-autostart-gui.service"
else
  add_warning "GUI timer not found at $GUI_TIMER"
fi

# Drop-in strict ExecStartPre is unsafe in GUI mode.
for drop in "$TARGET/systemd/dropins/noemaforge-autostart-gui.service.d/10-safe-gui-delay.conf" "/etc/systemd/system/noemaforge-autostart-gui.service.d/10-safe-gui-delay.conf"; do
  if [[ -f "$drop" ]]; then
    if grep -Eq 'ExecStartPre=.*(nvidia-smi|nvidia_drm|display-manager|gdm3|gdm)' "$drop"; then
      add_problem "GUI autostart drop-in contains strict readiness ExecStartPre: $drop"
    fi
  fi
done

BOOT_MODE="$TARGET/$PREP_REL/noemaforge-boot-mode.sh"
if [[ -f "$BOOT_MODE" ]]; then
  if grep -En 'enable[[:space:]]+noemaforge-autostart-gui\.service|graphical\.target\.wants/noemaforge-autostart-gui\.service' "$BOOT_MODE" >/dev/null; then
    add_problem "noemaforge-boot-mode.sh can enable direct GUI service; must enable timer only"
  fi
  grep -q 'noemaforge-autostart-gui.timer' "$BOOT_MODE" || add_problem "noemaforge-boot-mode.sh does not manage GUI timer"
else
  add_warning "boot-mode helper missing at $BOOT_MODE"
fi

AUTOSTART="$TARGET/$PREP_REL/noemaforge-autostart-safe.sh"
if [[ -f "$AUTOSTART" ]]; then
  grep -q 'runtime_only' "$AUTOSTART" || add_problem "autostart-safe lacks runtime_only profile"
  grep -q 'heavy LLM autostart is disabled' "$AUTOSTART" || add_warning "autostart-safe does not explicitly reject heavy LLM profile"
  grep -q -- '--llm-profile=runtime_only' "$AUTOSTART" || add_problem "GUI runtime_only profile may not be passed to safe-start"
else
  add_warning "autostart-safe helper missing at $AUTOSTART"
fi

if [[ "$JSON" == 1 ]]; then
  python3 - "$TARGET" "$LAYOUT" "${#PROBLEMS[@]}" "${#WARNINGS[@]}" "${PROBLEMS[@]}" -- "${WARNINGS[@]}" <<'PY'
import json, sys
target=sys.argv[1]; layout=sys.argv[2]
items=sys.argv[5:]
sep=items.index('--') if '--' in items else len(items)
problems=items[:sep]; warnings=items[sep+1:]
print(json.dumps({"ok": not problems, "target": target, "layout": layout, "problems": problems, "warnings": warnings}, ensure_ascii=False, indent=2))
PY
else
  echo "[recursion-audit] target: $TARGET layout=$LAYOUT"
  if ((${#WARNINGS[@]})); then
    echo "[recursion-audit] warnings:"
    for w in "${WARNINGS[@]}"; do echo "  - $w"; done
  fi
  if ((${#PROBLEMS[@]})); then
    echo "[recursion-audit] problems:"
    for p in "${PROBLEMS[@]}"; do echo "  - $p"; done
    exit 1
  fi
  echo "[recursion-audit] ok"
fi
