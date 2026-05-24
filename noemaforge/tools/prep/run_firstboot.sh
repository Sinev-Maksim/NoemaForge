#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/run_firstboot.sh
# Zone: prep
# Version: 0.32.1
# Purpose: Linux/macOS wrapper matching tools/windows/run_firstboot.cmd through the Python prep core.
# Inputs: Optional lab root plus --model-profile through environment MODEL_PROFILE.
# Outputs: JSON firstboot staging plan.
# Side effects: Writes Lab prep and staging artifacts under the requested Lab root.
# Tests: noemaforge/tests/test_cross_platform_prep_core_runtime.py
# === End NoemaForge File Header ===
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LAB_ROOT="${1:-$(cd "$REPO_ROOT/.." && pwd)/noemaforge-lab}"
MODEL_PROFILE="${MODEL_PROFILE:-minimal}"
PYTHON="${NOEMAFORGE_PYTHON:-python3}"
exec "$PYTHON" "$REPO_ROOT/tools/prep/noemaforge_prep_core.py" firstboot --repo-root "$REPO_ROOT" --lab-root "$LAB_ROOT" --model-profile "$MODEL_PROFILE" --auto-manifest
