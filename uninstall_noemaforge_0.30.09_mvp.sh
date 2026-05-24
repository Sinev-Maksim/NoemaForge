#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: uninstall_noemaforge_0.30.09_mvp.sh
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
DRY=0
KEEP_OPT=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run|--plan) DRY=1; shift ;;
    --remove-opt) KEEP_OPT=0; shift ;;
    -h|--help) echo "Usage: sudo ./uninstall_noemaforge_0.30.09_mvp.sh [--dry-run] [--remove-opt]"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
FILES=(
/etc/systemd/system/noemaforge-shutdown-stop.service
/etc/systemd/system/noemaforge-toolproxy.service.d/05-sel-perms.conf
/etc/systemd/system/noemaforge-llama@.service.d/40-socket-perms.conf
/etc/systemd/system/noemaforge-llm-backends-manager.service.d/50-single-active-manager.conf
/usr/local/sbin/noemaforge /usr/local/bin/noemaforge /usr/bin/noemaforge
/usr/local/sbin/noemaforge-stop /usr/local/sbin/noemaforge-reboot-safe /usr/local/sbin/noemaforge-sel-fix /usr/local/sbin/noemaforge-vault-mount-ro /usr/local/sbin/noemaforge-model-advisor
/usr/local/sbin/noemaforge-safe-start /usr/local/sbin/noemaforge-smoke /usr/local/sbin/noemaforge-manager /usr/local/sbin/noemaforge-monitor /usr/local/sbin/noemaforge-chat /usr/local/sbin/noemaforge-interpret /usr/local/sbin/noemaforge-toolproxy-diag
/usr/local/sbin/gui-status /usr/local/sbin/gui-rescue /usr/local/sbin/noemaforge-health /usr/local/sbin/noemaforge-safe-mode /usr/local/sbin/noemaforge-llm-memory-override /usr/local/sbin/noemaforge-start-llm-safe /usr/local/sbin/noemaforge-llm-stop /usr/local/sbin/noemaforge-service-stop
/usr/local/lib/noemaforge-common.sh
)
echo "NoemaForge 0.30.0 MVP/MWP uninstall"
for f in "${FILES[@]}"; do
  if [[ "$DRY" == 1 ]]; then echo "would remove $f"; else rm -f "$f" 2>/dev/null || true; fi
done
if [[ "$KEEP_OPT" == 0 ]]; then
  if [[ "$DRY" == 1 ]]; then echo "would remove /opt/noemaforge"; else rm -rf /opt/noemaforge 2>/dev/null || true; fi
fi
if [[ "$DRY" != 1 ]]; then systemctl daemon-reload 2>/dev/null || true; fi
cat <<'NOTE'
Data is preserved by default:
  /var/lib/noemaforge
  /var/lib/modelstore
  /mnt/noemaforge-share or external Vaults
Use manual backups before removing data.
NOTE
