#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/run_verify.sh
# Zone: prep
# Version: 0.32.1
# Purpose: Linux/macOS wrapper matching tools/windows/run_verify.cmd through the Python prep core.
# Inputs: Optional repo root argument.
# Outputs: JSON seed verification.
# Side effects: None.
# Tests: noemaforge/tests/test_cross_platform_prep_core_runtime.py
# === End NoemaForge File Header ===
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${1:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
PYTHON="${NOEMAFORGE_PYTHON:-python3}"
exec "$PYTHON" "$REPO_ROOT/tools/prep/noemaforge_prep_core.py" verify-seed --repo-root "$REPO_ROOT"
