#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-persona-gui.sh
# Zone: release/package
# Version: 0.31.13.alpha
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Manage NoemaForge personas, portraits and activation state.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
set -euo pipefail
ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
exec python3 "$ROOT/src/multimodal_runtime.py" --root "$ROOT" persona-gui "$@"
