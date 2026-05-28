#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-forensics-bundle.sh
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
# Collect a small NoemaForge support/forensics bundle without model weights or Vault data.
set -euo pipefail
OUT_DIR="/var/lib/noemaforge/forensics"
NAME="noemaforge-forensics-$(date -u +%Y%m%dT%H%M%SZ)"
DRY=0
usage(){ echo "Usage: sudo noemaforge forensics [--out-dir DIR] [--dry-run]"; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --dry-run|--plan) DRY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 2 ;;
  esac
done
TMP="${TMPDIR:-/tmp}/$NAME"
ARCHIVE="$OUT_DIR/$NAME.tar.gz"
if [[ "$DRY" == 1 ]]; then
  cat <<PLAN
Would collect safe diagnostics into: $ARCHIVE
Included: systemctl failed, NoemaForge service status, timers, free, nvidia-smi head, bootstrap reports, pipeline registry summaries, journal tails.
Excluded: model weights, Vault contents, browser profiles, secrets, cap_tokens.
PLAN
  exit 0
fi
mkdir -p "$TMP" "$OUT_DIR"
{
  echo "# NoemaForge forensics bundle"
  date -u +%Y-%m-%dT%H:%M:%SZ
  uname -a || true
  cat /etc/os-release 2>/dev/null || true
} > "$TMP/host.txt"
(systemctl --failed --no-pager || true) > "$TMP/systemctl-failed.txt" 2>&1
(systemctl status noemaforge-llm-gateway noemaforge-toolproxy 'noemaforge-llama@main.service' --no-pager || true) > "$TMP/noemaforge-services.txt" 2>&1
(systemctl list-timers 'noemaforge-*' --all --no-pager || true) > "$TMP/noemaforge-timers.txt" 2>&1
(free -h || true) > "$TMP/free.txt" 2>&1
(nvidia-smi 2>&1 | head -80 || true) > "$TMP/nvidia-smi.txt"
(findmnt /mnt/noemaforge-share || true) > "$TMP/share-mount.txt" 2>&1
(pgrep -a -f '[l]lama-server' || true) > "$TMP/llama-processes.txt" 2>&1
(journalctl -p 3 -S '2 hours ago' --no-pager || true) > "$TMP/journal-errors-2h.txt" 2>&1
(journalctl -u noemaforge-llm-gateway -u noemaforge-toolproxy -u 'noemaforge-llama@main.service' -S '2 hours ago' --no-pager || true) > "$TMP/journal-noemaforge-2h.txt" 2>&1
mkdir -p "$TMP/bootstrap"
for f in \
  /var/lib/noemaforge/bootstrap/*.json \
  /var/lib/noemaforge/bootstrap/*.txt \
  /var/lib/noemaforge/bootstrap/*.log \
  /workspace/outbox/bootreports/*.txt \
  /workspace/outbox/bootreports/*.json; do
  [[ -f "$f" ]] || continue
  case "$f" in
    *cap_tokens*|*token*|*secret*|*key*) continue ;;
  esac
  cp -a "$f" "$TMP/bootstrap/" 2>/dev/null || true
done
if command -v noemaforge >/dev/null 2>&1; then
  (noemaforge pipeline dashboard-state 2>/dev/null || true) > "$TMP/pipeline-dashboard-state.json"
  (noemaforge profiles recommend --json 2>/dev/null || true) > "$TMP/model-profile-recommendation.json"
fi
# Redact obvious paths that may include usernames only lightly; do not touch JSON structure.
find "$TMP" -type f -size -2M -print0 | while IFS= read -r -d '' f; do
  sed -i -E 's/(token|secret|password|api_key)[^[:space:]",}]*/\1=[REDACTED]/Ig' "$f" 2>/dev/null || true
done
tar -C "$(dirname "$TMP")" -czf "$ARCHIVE" "$(basename "$TMP")"
sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
rm -rf "$TMP"
echo "$ARCHIVE"
