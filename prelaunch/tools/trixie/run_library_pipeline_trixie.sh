#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: prelaunch/tools/trixie/run_library_pipeline_trixie.sh
# Zone: release/package
# Version: 0.31.13.alpha
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Manage NoemaForge pipeline catalog, runs, gates, artifacts and state.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${NOEMAFORGE_PRELAUNCH_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
COMMON="$ROOT/prelaunch/tools/common"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${NOEMAFORGE_PRELAUNCH_VENV:-$ROOT/.venv-prelaunch}"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip >/dev/null
python -m pip install requests tqdm pyyaml >/dev/null
cd "$COMMON"
python library_pipeline_orchestrator.py "${@}"
