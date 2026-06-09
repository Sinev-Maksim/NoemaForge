#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: ci/run_acceptance.sh
# Zone: ci/acceptance
# Version: 0.33.0
# Purpose: Entry point for the artifact-driven acceptance suite (AAT). Thin wrapper
#   that delegates to the cross-platform Python runner so the suite is testable on
#   any host and produces a verifiable results/ outputs bundle.
# Inputs: $1 = results directory (default: results)
# Outputs: <results>/ bundle (per-tier artifacts + summary.json + junit.xml + manifest.sha256)
# Side effects: writes only under the results directory.
# Tests: bash -n syntax check; the runner is exercised by ci/acceptance/test_acceptance.py.
# Notes: Code comments are English-only.
# === End NoemaForge File Header ===
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
results="${1:-results}"
exec python3 "$here/acceptance_runner.py" "$results"
