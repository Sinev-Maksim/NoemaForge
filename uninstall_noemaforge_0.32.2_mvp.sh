#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: uninstall_noemaforge_0.32.2_mvp.sh
# Zone: release/package
# Version: 0.32.2
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

DRY_RUN=0
SELFTEST=0

usage(){ cat <<'USAGE'
Usage:
  ./uninstall_noemaforge_0.32.2_mvp.sh [--dry-run] [--selftest]

Options:
  --dry-run, --plan   Print the uninstall handoff plan only.
  --selftest          Validate this script without changing the host.

Notes:
  - 0.32.2 is an installer-loop stabilization package.
  - The historical uninstall flow remains the authoritative apply path.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run|--plan) DRY_RUN=1; shift ;;
    --selftest) SELFTEST=1; shift ;;
    -h|--help|help) usage; exit 0 ;;
    *) echo "[uninstall][ERROR] unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ "$SELFTEST" == 1 ]]; then
  bash -n "$0"
  echo "[uninstall] selftest: syntax validation passed"
fi

cat <<PLAN
NoemaForge 0.32.2 uninstall plan
  dry_run: $DRY_RUN
  destructive_actions: none
  authoritative_apply_path: previous release uninstall flow
PLAN

if [[ "$DRY_RUN" == 1 ]]; then
  echo "[uninstall] dry-run complete. No services, files or systemd units were changed."
  exit 0
fi

echo "Use previous uninstall flow; 0.32.2 is an installer-loop stabilization package."

