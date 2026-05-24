#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/run_lab.sh
# Zone: prep
# Version: 0.31.21.alpha
# Purpose: Linux/macOS wrapper matching tools/windows/run_lab.cmd through the Python prep core.
# Inputs: Optional lab root and Python from NOEMAFORGE_PYTHON.
# Outputs: JSON Lab prep run.
# Side effects: Writes Lab prep artifacts under the requested Lab root.
# Tests: noemaforge/tests/test_cross_platform_prep_core_runtime.py
# === End NoemaForge File Header ===
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LAB_ROOT="${1:-$(cd "$REPO_ROOT/.." && pwd)/noemaforge-lab}"
PYTHON="${NOEMAFORGE_PYTHON:-python3}"
exec "$PYTHON" "$REPO_ROOT/tools/prep/noemaforge_prep_core.py" lab --repo-root "$REPO_ROOT" --lab-root "$LAB_ROOT" --auto-manifest
