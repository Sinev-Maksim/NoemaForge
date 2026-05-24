#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: install_noemaforge_0.29.11_full.sh
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
set -euo pipefail

VERSION="0.29.11"
PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOTFS="/"
VERIFY=0
SELFTEST=0
PRESERVE_TIMERS=0

usage(){ cat <<'USAGE'
Usage: sudo ./install_noemaforge_0.29.11_full.sh [--verify] [--selftest] [--rootfs DIR] [--preserve-timers]

Installs NoemaForge 0.29.11 recovery/stability full verified package.
Default behavior disables manager/modelscan timers for safe public MWP startup.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verify) VERIFY=1; shift ;;
    --selftest) SELFTEST=1; shift ;;
    --rootfs) ROOTFS="$2"; shift 2 ;;
    --preserve-timers) PRESERVE_TIMERS=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ "$ROOTFS" == "/" && ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "ERROR: run live install as root" >&2
  exit 1
fi

target(){ local p="$1"; printf '%s/%s' "${ROOTFS%/}" "${p#/}"; }
backup_one(){
  local p="$1" t; t="$(target "$p")"
  if [[ "$ROOTFS" == "/" && ( -e "$t" || -L "$t" ) ]]; then
    mkdir -p "$BACKUP/backup-root/$(dirname "${p#/}")"
    cp -a "$t" "$BACKUP/backup-root/${p#/}" 2>/dev/null || true
  fi
}
install_file(){ local src="$1" rel="$2" mode="${3:-0755}"; mkdir -p "$(dirname "$(target "$rel")")"; install -m "$mode" "$src" "$(target "$rel")"; }
install_symlink(){ local src="$1" dst="$2"; mkdir -p "$(dirname "$(target "$dst")")"; ln -sfn "$src" "$(target "$dst")"; }

if [[ "$VERIFY" == 1 && -f "$PKG_DIR/SHA256SUMS" ]]; then
  (cd "$PKG_DIR" && sha256sum -c SHA256SUMS)
fi

if [[ "$SELFTEST" == 1 ]]; then
  bash -n "$PKG_DIR/install_noemaforge_0.29.11_full.sh"
  bash -n "$PKG_DIR/uninstall_noemaforge_0.29.11_full.sh"
  find "$PKG_DIR/helpers" -maxdepth 1 -type f -perm -111 -print0 | while IFS= read -r -d '' f; do
    case "$(basename "$f")" in noemaforge-model-advisor|noemaforge-chat) python3 -B -m py_compile "$f" ;; *) bash -n "$f" ;; esac
  done
fi

BACKUP="/var/backups/noemaforge-${VERSION}-full-$(date +%Y%m%d-%H%M%S)"
if [[ "$ROOTFS" == "/" ]]; then install -d -m 0750 "$BACKUP"; echo "[noemaforge-${VERSION}] backup: $BACKUP"; else echo "[noemaforge-${VERSION}] rootfs install: $ROOTFS"; fi

# Back up known targets. This package intentionally does not remove Vault or model data.
for p in \
  /opt/noemaforge \
  /usr/local/sbin/noemaforge /usr/local/bin/noemaforge /usr/bin/noemaforge \
  /usr/local/sbin/noemaforge-stop /usr/local/sbin/noemaforge-reboot-safe /usr/local/sbin/noemaforge-sel-fix \
  /usr/local/sbin/noemaforge-vault-mount-ro /usr/local/sbin/noemaforge-model-advisor \
  /etc/default/noemaforge-recovery \
  /etc/systemd/system/noemaforge-shutdown-stop.service \
  /etc/systemd/system/noemaforge-toolproxy.service.d/05-sel-perms.conf \
  /etc/systemd/system/noemaforge-llama@.service.d/40-socket-perms.conf \
  /etc/systemd/system/noemaforge-llm-backends-manager.service.d/50-single-active-manager.conf \
  /var/lib/noemaforge/.sys/noemaforge-stop-policy.json /var/lib/noemaforge/.sys/runtime-invariants.json; do
  backup_one "$p"
done

# Full NoemaForge tree: no --delete, to avoid erasing site-local additions during recovery/stability install.
mkdir -p "$(target /opt/noemaforge)"
if command -v rsync >/dev/null 2>&1; then
  rsync -a "$PKG_DIR/noemaforge/" "$(target /opt/noemaforge)/"
else
  cp -a "$PKG_DIR/noemaforge/." "$(target /opt/noemaforge)/"
fi

# Recovery helper surface.
for h in noemaforge noemaforge-stop noemaforge-reboot-safe noemaforge-sel-fix noemaforge-vault-mount-ro noemaforge-model-advisor noemaforge-safe-start noemaforge-smoke noemaforge-manager noemaforge-monitor noemaforge-chat noemaforge-interpret noemaforge-toolproxy-diag gui-status gui-rescue noemaforge-health noemaforge-safe-mode noemaforge-llm-memory-override noemaforge-start-llm-safe noemaforge-llm-stop noemaforge-service-stop; do
  if [[ -f "$PKG_DIR/helpers/$h" ]]; then install_file "$PKG_DIR/helpers/$h" "/usr/local/sbin/$h" 0755; fi
done
install_file "$PKG_DIR/lib/noemaforge-common.sh" /usr/local/lib/noemaforge-common.sh 0644
install_symlink /usr/local/sbin/noemaforge /usr/local/bin/noemaforge
install_symlink /usr/local/sbin/noemaforge /usr/bin/noemaforge
for h in noemaforge-stop noemaforge-reboot-safe noemaforge-sel-fix noemaforge-vault-mount-ro noemaforge-model-advisor noemaforge-safe-start noemaforge-smoke noemaforge-manager noemaforge-monitor noemaforge-chat noemaforge-interpret noemaforge-toolproxy-diag; do
  [[ -f "$PKG_DIR/helpers/$h" ]] && install_symlink "/usr/local/sbin/$h" "/usr/local/bin/$h"
done
install_symlink /usr/local/sbin/noemaforge-chat /usr/local/bin/chatgpt-light

# Defaults and policies.
install_file "$PKG_DIR/policies/noemaforge-recovery.example" /etc/default/noemaforge-recovery.example 0644
if [[ ! -e "$(target /etc/default/noemaforge-recovery)" ]]; then
  install_file "$PKG_DIR/policies/noemaforge-recovery.example" /etc/default/noemaforge-recovery 0644
fi
install_file "$PKG_DIR/policies/noemaforge-stop-policy.json" /var/lib/noemaforge/.sys/noemaforge-stop-policy.json 0640
install_file "$PKG_DIR/policies/runtime-invariants.json" /var/lib/noemaforge/.sys/runtime-invariants.json 0640

# Systemd units/drop-ins.
install_file "$PKG_DIR/systemd/noemaforge-shutdown-stop.service" /etc/systemd/system/noemaforge-shutdown-stop.service 0644
install_file "$PKG_DIR/systemd/dropins/noemaforge-toolproxy.service.d/05-sel-perms.conf" /etc/systemd/system/noemaforge-toolproxy.service.d/05-sel-perms.conf 0644
install_file "$PKG_DIR/systemd/dropins/noemaforge-llama@.service.d/40-socket-perms.conf" /etc/systemd/system/noemaforge-llama@.service.d/40-socket-perms.conf 0644
install_file "$PKG_DIR/systemd/dropins/noemaforge-llm-backends-manager.service.d/50-single-active-manager.conf" /etc/systemd/system/noemaforge-llm-backends-manager.service.d/50-single-active-manager.conf 0644

# Docs.
DOCROOT="/usr/local/share/noemaforge"
mkdir -p "$(target "$DOCROOT/docs")"
install_file "$PKG_DIR/context.md" "$DOCROOT/context.md" 0644
install_file "$PKG_DIR/README.md" "$DOCROOT/README-0.29.11.md" 0644
install_file "$PKG_DIR/CHANGELOG.md" "$DOCROOT/CHANGELOG-0.29.11.md" 0644
if command -v rsync >/dev/null 2>&1; then rsync -a "$PKG_DIR/docs/" "$(target "$DOCROOT/docs/")"; else cp -a "$PKG_DIR/docs/." "$(target "$DOCROOT/docs/")"; fi

if [[ "$ROOTFS" == "/" ]]; then
  GROUP="$(getent group noemaforge >/dev/null && echo noemaforge || echo root)"
  install -d -o root -g "$GROUP" -m 0750 /var/lib/noemaforge /var/lib/noemaforge/.sys /var/lib/noemaforge/bootstrap 2>/dev/null || true
  install -d -o noemaforge -g "$GROUP" -m 2770 /var/lib/noemaforge/sel /var/lib/noemaforge/sel/segments 2>/dev/null || true
  chgrp "$GROUP" /var/lib/noemaforge/.sys/noemaforge-stop-policy.json /var/lib/noemaforge/.sys/runtime-invariants.json 2>/dev/null || true
  systemctl daemon-reload || true
  systemctl enable noemaforge-shutdown-stop.service 2>/dev/null || true
  if [[ "$PRESERVE_TIMERS" != 1 ]]; then
    systemctl disable --now noemaforge-llm-backends-manager.timer noemaforge-modelscan.timer 2>/dev/null || true
  fi
  /usr/local/sbin/noemaforge-sel-fix --repair-only 2>/dev/null || /usr/local/sbin/noemaforge-sel-fix 2>/dev/null || true
  if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze verify /etc/systemd/system/noemaforge-shutdown-stop.service 2>/dev/null || true
  fi
fi

cat <<EOM
NoemaForge ${VERSION} recovery/stability full verified package installed.
Backup: ${BACKUP:-none-rootfs}

Recommended next:
  hash -r
  command -v noemaforge
  sudo sh -lc 'command -v noemaforge; noemaforge vault-path'
  sudo noemaforge stop --dry-run
  noemaforge recommend-model
  sudo noemaforge safe-start --wait --restart
  noemaforge smoke --debug

Context:
  /usr/local/share/noemaforge/context.md
EOM
