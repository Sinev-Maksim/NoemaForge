#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: prelaunch/tools/trixie/run_unified_manifest_downloader_trixie.sh
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
python -m pip install huggingface_hub hf_xet requests tqdm pyyaml >/dev/null
export HF_HOME="${HF_HOME:-$ROOT/.hf-home}"
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HF_HOME/hub}"
export HF_XET_CACHE="${HF_XET_CACHE:-$HF_HOME/xet}"
mkdir -p "$HF_HOME" "$HF_HUB_CACHE" "$HF_XET_CACHE"
cd "$COMMON"
python unified_manifest_downloader.py "${@}"
