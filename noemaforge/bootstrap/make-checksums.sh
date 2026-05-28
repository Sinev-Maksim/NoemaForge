#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/bootstrap/make-checksums.sh
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
# === NoemaForge Autodoc File Header ===
# File: bootstrap/make-checksums.sh
# Purpose: Provide the script 'make-checksums'.
# Invoked by: shell operators or wrapper scripts.
# Inputs: Positional arguments, environment variables, and files read below.
# Outputs: Console output and filesystem side effects.
# AutoDoc: refreshed 2026-04-09 (heuristic)
# === End NoemaForge Autodoc File Header ===




set -euo pipefail

ROOT="${1:-seed/noemaforge}"
OUT="${ROOT}/checksums/SHA256SUMS"
mkdir -p "$(dirname "$OUT")"

TMP="$(mktemp)"
# Exclude the checksum file itself to avoid self-referential hashes.
(
  cd "$ROOT"
  find . -type f \
    ! -path "./checksums/SHA256SUMS" \
    ! -path "*/__pycache__/*" \
    ! -name "*.pyc" \
    ! -path "./src/noemaforge-llm-gateway" \
    ! -path "./src/noemaforge-llm-gateway.exe" \
    -print0 | sort -z | xargs -0 sha256sum
) >"$TMP"

mv -f "$TMP" "$OUT"
echo "Wrote $OUT"
