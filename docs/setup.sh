#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: setup.sh
# Zone: release/package
# Version: 0.32.1
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Validate and install the NoemaForge release package on the host.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
# NoemaForge 0.32.1 setup front door.
# Safe by default: dry-run friendly, one active LLM invariant, no heavy backend autostart.
set -euo pipefail

# 0.32.1 guard: setup may delegate to the real installer, but it must
# never be re-entered by that installer. This catches the 0.32.1 loop
# class (setup.sh -> install_* -> setup.sh -> ...).
if [[ "${NOEMAFORGE_SETUP_DEPTH:-0}" -ge 1 ]]; then
  echo "[setup][ERROR] recursive setup invocation detected; use the real installer directly or clear the loop" >&2
  exit 70
fi
export NOEMAFORGE_SETUP_DEPTH=$(( ${NOEMAFORGE_SETUP_DEPTH:-0} + 1 ))

PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="vm"
INSTALL_ROOT="/"
DATA_ROOT="/var/lib/noemaforge"
MODEL_PROFILE="minimal"
WITH_SHARE=""
OFFLINE_AFTER_SETUP=0
DRY_RUN=0
SELFTEST=0
APPLY_VM=0

usage(){ cat <<'USAGE'
Usage:
  ./setup.sh [--mode vm|host|docker-dev|macos-dev] [options]

Common options:
  --dry-run                    Validate package and print planned actions only.
  --selftest                   Run shell/python sanity checks before planning/installing.
  --install-root DIR           Alternate rootfs target for packaging tests.
  --data-root DIR              NoemaForge data root; default /var/lib/noemaforge.
  --model-profile NAME         minimal|balanced|writer|research|gpu-heavy.
  --with-share PATH            Existing shared/Vault mount path to normalize later.
  --offline-after-setup        Record intent; no network work is performed by this script.
  --apply-vm                   Allow VM mode to install; otherwise VM mode is plan/selftest only.

Recommended first public MWP path:
  ./setup.sh --mode vm --dry-run --selftest
  sudo ./setup.sh --mode host --model-profile minimal --with-share /mnt/noemaforge-share

Notes:
  - setup never enables parallel LLM runtime.
  - setup never enables ungated heavy GPU backend autostart.
  - GUI autostart uses delayed timer, not direct graphical.target service.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --install-root|--rootfs) INSTALL_ROOT="$2"; shift 2 ;;
    --data-root) DATA_ROOT="$2"; shift 2 ;;
    --model-profile) MODEL_PROFILE="$2"; shift 2 ;;
    --with-share) WITH_SHARE="$2"; shift 2 ;;
    --offline-after-setup) OFFLINE_AFTER_SETUP=1; shift ;;
    --dry-run|--plan) DRY_RUN=1; shift ;;
    --selftest) SELFTEST=1; shift ;;
    --apply-vm) APPLY_VM=1; shift ;;
    -h|--help|help) usage; exit 0 ;;
    *) echo "[setup][ERROR] unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

case "$MODE" in vm|host|docker-dev|macos-dev) : ;; *) echo "[setup][ERROR] unsupported mode: $MODE" >&2; exit 2 ;; esac
case "$MODEL_PROFILE" in minimal|balanced|writer|research|gpu-heavy) : ;; *) echo "[setup][ERROR] unsupported model profile: $MODEL_PROFILE" >&2; exit 2 ;; esac

if [[ "$SELFTEST" == 1 ]]; then
  echo "[setup] selftest: shell syntax"
  bash -n "$PKG_DIR/setup.sh"
  bash -n "$PKG_DIR/install_noemaforge_0.32.1_mvp.sh"
  if grep -Eq '^[[:space:]]*exec[[:space:]]+.*setup\.sh' "$PKG_DIR/install_noemaforge_0.32.1_mvp.sh"; then
    echo "[setup][ERROR] installer must not exec setup.sh; recursion risk" >&2
    exit 71
  fi
  bash -n "$PKG_DIR/uninstall_noemaforge_0.32.1_mvp.sh"
  bash -n "$PKG_DIR/noemaforge/bin/noemaforge"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-version-audit.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-first-run-audit.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-first-launch.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-headless.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-av-readiness.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-multimodal.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-consistency-audit.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-persona-gui.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-trixie-preflight.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-mvp-smoke.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-dashboard.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-autostart-safe.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-boot-mode.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-gui-diagnose.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-gui-start.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-gui-recover-minimal.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-recursion-audit.sh"
  echo "[setup] selftest: critical python syntax"
  PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
    "$PKG_DIR/noemaforge/src/admin_runtime.py" \
    "$PKG_DIR/noemaforge/src/admin_gui_server.py" \
    "$PKG_DIR/noemaforge/src/dev_team_runtime.py" \
    "$PKG_DIR/noemaforge/src/model_evolution_runtime.py"
  find "$PKG_DIR/noemaforge/src" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
  echo "[setup] selftest: CLI/API surfaces are covered by targeted verification; package syntax validation passed"
fi
cat <<PLAN
NoemaForge 0.32.1 setup plan
  mode:                  $MODE
  install_root:          $INSTALL_ROOT
  data_root:             $DATA_ROOT
  model_profile:         $MODEL_PROFILE
  with_share:            ${WITH_SHARE:-not-set}
  offline_after_setup:   $OFFLINE_AFTER_SETUP
  dry_run:               $DRY_RUN
  invariant:             max_active_llms=1, gui_llm_profile=runtime_only, wogui_llm_profile=bootstrap_cpu_llm, heavy_llm_autostart=manual_only
PLAN

case "$MODE" in
  macos-dev)
    echo "[setup] macOS dev mode: validates repo and writes no privileged system files."
    DRY_RUN=1 ;;
  docker-dev)
    echo "[setup] Docker/dev mode: package validation only unless --install-root points to a test rootfs." ;;
  vm)
    echo "[setup] VM mode: recommended first success path. Non-destructive unless --apply-vm is provided."
    [[ "$APPLY_VM" == 1 ]] || DRY_RUN=1 ;;
  host)
    echo "[setup] Host mode: installs operator CLI and safe recovery helpers." ;;
esac

if [[ "$DRY_RUN" == 1 ]]; then
  echo "[setup] dry-run complete. To install on host: sudo ./setup.sh --mode host --model-profile $MODEL_PROFILE --with-share ${WITH_SHARE:-/mnt/noemaforge-share}"
  exit 0
fi

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "[setup][ERROR] non-dry-run install requires sudo/root." >&2
  exit 1
fi

install_args=(--rootfs "$INSTALL_ROOT" --data-root "$DATA_ROOT" --model-profile "$MODEL_PROFILE")
if [[ -n "$WITH_SHARE" ]]; then install_args+=(--with-share "$WITH_SHARE"); fi
exec "$PKG_DIR/install_noemaforge_0.32.1_mvp.sh" "${install_args[@]}"
