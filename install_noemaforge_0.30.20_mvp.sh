#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: install_noemaforge_0.30.20_mvp.sh
# Zone: release/package
# Version: 0.31.13.alpha-patched1
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Install a historical or current NoemaForge release payload.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
# NoemaForge 0.30.20 public MVP/MWP installer.
# Installs the operator CLI, safe runtime helpers, docs, and config defaults.
# It does not auto-start heavy LLM backends and does not enable parallel runtime.
set -euo pipefail

VERSION="0.30.20"
PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOTFS="/"
DATA_ROOT="/var/lib/noemaforge"
MODEL_PROFILE="minimal"
WITH_SHARE=""
VERIFY=0
SELFTEST=0
PRESERVE_TIMERS=0
DRY_RUN=0

usage(){ cat <<'USAGE'
Usage: sudo ./install_noemaforge_0.30.20_mvp.sh [options]

Options:
  --verify                    Verify SHA256SUMS when present.
  --selftest                  Run installer/package syntax checks.
  --rootfs DIR                Alternate rootfs for test installs.
  --data-root DIR             NoemaForge data root; default /var/lib/noemaforge.
  --model-profile NAME        minimal|balanced|writer|research|gpu-heavy.
  --with-share PATH           Record/share path for later mount normalization.
  --preserve-timers           Do not disable existing NoemaForge timers.
  --dry-run                   Print plan only.

Safe defaults:
  - disables manager/modelscan timers unless --preserve-timers is passed;
  - installs runtime invariant max_active_llms=1;
  - never downloads models or starts heavy backends.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verify) VERIFY=1; shift ;;
    --selftest) SELFTEST=1; shift ;;
    --rootfs) ROOTFS="$2"; shift 2 ;;
    --data-root) DATA_ROOT="$2"; shift 2 ;;
    --model-profile) MODEL_PROFILE="$2"; shift 2 ;;
    --with-share) WITH_SHARE="$2"; shift 2 ;;
    --preserve-timers) PRESERVE_TIMERS=1; shift ;;
    --dry-run|--plan) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

case "$MODEL_PROFILE" in minimal|balanced|writer|research|gpu-heavy) : ;; *) echo "ERROR: unsupported model profile: $MODEL_PROFILE" >&2; exit 2 ;; esac
if [[ "$ROOTFS" == "/" && "$DRY_RUN" != 1 && ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "ERROR: run live install as root" >&2
  exit 1
fi

target(){ local p="$1"; printf '%s/%s' "${ROOTFS%/}" "${p#/}"; }
install_file(){ local src="$1" rel="$2" mode="${3:-0755}"; [[ "$DRY_RUN" == 1 ]] && { echo "install $rel mode=$mode"; return 0; }; mkdir -p "$(dirname "$(target "$rel")")"; install -m "$mode" "$src" "$(target "$rel")"; }
install_symlink(){ local src="$1" dst="$2"; [[ "$DRY_RUN" == 1 ]] && { echo "link $dst -> $src"; return 0; }; mkdir -p "$(dirname "$(target "$dst")")"; ln -sfn "$src" "$(target "$dst")"; }
backup_one(){ local p="$1" t; t="$(target "$p")"; if [[ "$ROOTFS" == "/" && "$DRY_RUN" != 1 && ( -e "$t" || -L "$t" ) ]]; then mkdir -p "$BACKUP/backup-root/$(dirname "${p#/}")"; cp -a "$t" "$BACKUP/backup-root/${p#/}" 2>/dev/null || true; fi; }

if [[ "$VERIFY" == 1 && -f "$PKG_DIR/SHA256SUMS_0.30.20" ]]; then
  (cd "$PKG_DIR" && sha256sum -c SHA256SUMS_0.30.20)
elif [[ "$VERIFY" == 1 && -f "$PKG_DIR/SHA256SUMS" ]]; then
  (cd "$PKG_DIR" && sha256sum -c SHA256SUMS)
fi

if [[ "$SELFTEST" == 1 ]]; then
  echo "[setup] selftest: shell syntax"
  bash -n "$PKG_DIR/setup.sh"
  bash -n "$PKG_DIR/install_noemaforge_0.30.20_mvp.sh"
  bash -n "$PKG_DIR/uninstall_noemaforge_0.30.20_mvp.sh"
  bash -n "$PKG_DIR/noemaforge/bin/noemaforge"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-trixie-preflight.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-mvp-smoke.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-autostart-safe.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-boot-mode.sh"
  echo "[setup] selftest: critical python syntax"
  python3 - "$PKG_DIR/noemaforge/src" <<'PYCOMPILE'
import pathlib, sys
root = pathlib.Path(sys.argv[1])
for name in ['pipeline_runtime.py','noemaforge_status.py','model_profiles.py','model_inventory_normalize.py','noemaforge_tasks.py']:
    p = root / name
    compile(p.read_text(encoding='utf-8', errors='replace'), str(p), 'exec')
PYCOMPILE
  NOEMAFORGE_ROOT="$PKG_DIR/noemaforge" python3 "$PKG_DIR/noemaforge/src/pipeline_runtime.py" --root "$PKG_DIR/noemaforge" --state "${TMPDIR:-/tmp}/noemaforge-setup-selftest-state" validate >/dev/null
fi
cat <<PLAN
NoemaForge ${VERSION} install plan
  rootfs:          $ROOTFS
  data_root:       $DATA_ROOT
  model_profile:   $MODEL_PROFILE
  with_share:      ${WITH_SHARE:-not-set}
  preserve_timers: $PRESERVE_TIMERS
  dry_run:         $DRY_RUN
  invariant:       max_active_llms=1, heavy_llm_autostart=conditional_safe_start_only
PLAN
[[ "$DRY_RUN" == 1 ]] && exit 0

BACKUP="/var/backups/noemaforge-${VERSION}-$(date +%Y%m%d-%H%M%S)"
if [[ "$ROOTFS" == "/" ]]; then install -d -m 0750 "$BACKUP"; echo "[noemaforge-${VERSION}] backup: $BACKUP"; else echo "[noemaforge-${VERSION}] rootfs install: $ROOTFS"; fi

for p in \
  /opt/noemaforge \
  /usr/local/sbin/noemaforge /usr/local/bin/noemaforge /usr/bin/noemaforge \
  /usr/local/sbin/noemaforge-stop /usr/local/sbin/noemaforge-reboot-safe /usr/local/sbin/noemaforge-vault-mount-ro /usr/local/sbin/noemaforge-model-advisor \
  /usr/local/lib/noemaforge-common.sh \
  /etc/default/noemaforge-recovery \
  /etc/noemaforge/boot-mode /etc/systemd/system/noemaforge-autostart-gui.service /etc/systemd/system/noemaforge-autostart-wogui.service \
  /var/lib/noemaforge/.sys/runtime-invariants.json; do
  backup_one "$p"
done

mkdir -p "$(target /opt/noemaforge)"
if command -v rsync >/dev/null 2>&1; then
  rsync -a "$PKG_DIR/noemaforge/" "$(target /opt/noemaforge)/"
else
  cp -a "$PKG_DIR/noemaforge/." "$(target /opt/noemaforge)/"
fi

for h in noemaforge noemaforge-stop noemaforge-reboot-safe noemaforge-sel-fix noemaforge-vault-mount-ro noemaforge-model-advisor noemaforge-safe-start noemaforge-smoke noemaforge-manager noemaforge-monitor noemaforge-chat noemaforge-interpret noemaforge-toolproxy-diag gui-status gui-rescue noemaforge-health noemaforge-safe-mode noemaforge-llm-memory-override noemaforge-start-llm-safe noemaforge-llm-stop noemaforge-service-stop; do
  [[ -f "$PKG_DIR/helpers/$h" ]] && install_file "$PKG_DIR/helpers/$h" "/usr/local/sbin/$h" 0755
done
install_file "$PKG_DIR/noemaforge/bin/noemaforge" /usr/local/sbin/noemaforge 0755
install_file "$PKG_DIR/lib/noemaforge-common.sh" /usr/local/lib/noemaforge-common.sh 0644
install_symlink /usr/local/sbin/noemaforge /usr/local/bin/noemaforge
install_symlink /usr/local/sbin/noemaforge /usr/bin/noemaforge
for h in noemaforge-stop noemaforge-reboot-safe noemaforge-sel-fix noemaforge-vault-mount-ro noemaforge-model-advisor noemaforge-safe-start noemaforge-smoke noemaforge-manager noemaforge-monitor noemaforge-chat noemaforge-interpret noemaforge-toolproxy-diag; do
  [[ -f "$PKG_DIR/helpers/$h" ]] && install_symlink "/usr/local/sbin/$h" "/usr/local/bin/$h"
done

install -d -m 0750 "$(target "$DATA_ROOT")" "$(target "$DATA_ROOT/.sys")" "$(target "$DATA_ROOT/bootstrap")"
if [[ -f "$PKG_DIR/policies/runtime-invariants.json" ]]; then
  install_file "$PKG_DIR/policies/runtime-invariants.json" "$DATA_ROOT/.sys/runtime-invariants.json" 0640
fi
if [[ -f "$PKG_DIR/policies/noemaforge-stop-policy.json" ]]; then
  install_file "$PKG_DIR/policies/noemaforge-stop-policy.json" "$DATA_ROOT/.sys/noemaforge-stop-policy.json" 0640
fi
cat > "$(target "$DATA_ROOT/.sys/setup-profile.json")" <<PROFILE
{
  "version": "${VERSION}",
  "model_profile": "${MODEL_PROFILE}",
  "with_share": "${WITH_SHARE}",
  "max_active_llms": 1,
  "heavy_llm_autostart": "conditional_safe_start_only",
  "boot_mode_default": "manual",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
PROFILE

DOCROOT="/usr/local/share/noemaforge"
mkdir -p "$(target "$DOCROOT/docs")"
install_file "$PKG_DIR/context.md" "$DOCROOT/context.md" 0644
install_file "$PKG_DIR/README.md" "$DOCROOT/README.md" 0644
if command -v rsync >/dev/null 2>&1; then rsync -a "$PKG_DIR/docs/" "$(target "$DOCROOT/docs/")"; else cp -a "$PKG_DIR/docs/." "$(target "$DOCROOT/docs/")"; fi

# Install optional conditional autostart units. They are not enabled by default.
install_file "$PKG_DIR/systemd/noemaforge-autostart-gui.service" /etc/systemd/system/noemaforge-autostart-gui.service 0644
install_file "$PKG_DIR/systemd/noemaforge-autostart-wogui.service" /etc/systemd/system/noemaforge-autostart-wogui.service 0644
if [[ ! -e "$(target /etc/noemaforge/boot-mode)" ]]; then
  mkdir -p "$(target /etc/noemaforge)"
  printf 'manual
' > "$(target /etc/noemaforge/boot-mode)"
  chmod 0644 "$(target /etc/noemaforge/boot-mode)"
fi

if [[ "$ROOTFS" == "/" ]]; then
  GROUP="$(getent group noemaforge >/dev/null && echo noemaforge || echo root)"
  chgrp "$GROUP" "$DATA_ROOT" "$DATA_ROOT/.sys" "$DATA_ROOT/bootstrap" 2>/dev/null || true
  chmod 0750 "$DATA_ROOT" "$DATA_ROOT/.sys" "$DATA_ROOT/bootstrap" 2>/dev/null || true
  systemctl daemon-reload 2>/dev/null || true
  systemctl disable noemaforge-autostart-gui.service noemaforge-autostart-wogui.service 2>/dev/null || true
  if [[ "$PRESERVE_TIMERS" != 1 ]]; then
    systemctl disable --now noemaforge-llm-backends-manager.timer noemaforge-modelscan.timer 2>/dev/null || true
  fi
fi

cat <<EOM
NoemaForge ${VERSION} MVP/MWP package installed.
Backup: ${BACKUP:-none-rootfs}

Next safe checks:
  hash -r
  noemaforge help
  noemaforge profiles recommend
  sudo noemaforge stop --dry-run
  noemaforge pipeline validate
  sudo noemaforge trixie-preflight --json

Conditional autostart is installed but disabled by default. To enable:
  sudo noemaforge boot-mode set gui --apply-systemd      # safe-start after GUI
  sudo noemaforge boot-mode set wogui --apply-systemd    # safe-start instead of GUI

Start runtime manually only when ready:
  sudo noemaforge safe-start --wait --restart
  noemaforge smoke --debug
EOM
