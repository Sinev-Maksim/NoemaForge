#!/usr/bin/env sh
# === NoemaForge File Header ===
# File: noemaforge/tools/start.sh
# Zone: tools
# Version: 0.33.0
# Created: 2026-06-07
# Modified: 2026-06-07
# Purpose: One-button start for POSIX hosts (Linux/macOS). Resolves python3 and runs
#   `noema start` (readiness check -> ensure data dirs -> launch the localhost Admin GUI ->
#   open the browser). Display-safe: starts only the localhost control plane; no GPU/model/
#   privileged actions (the privileged first-start stays operator-gated, always --keep-display).
# Inputs: optional pass-through flags for `noema start` (--port N, --no-browser, --check-only,
#   --no-doctor, --background, --force). Honors $NOEMAFORGE_PYTHON to override the interpreter.
# Outputs: launches the Admin GUI; prints the dashboard URL.
# Side effects: creates user-writable data dirs; spawns the Admin GUI server process.
# Notes: Code comments are English-only. POSIX sh; validated with `bash -n`.
# === End NoemaForge File Header ===
set -eu

# Package root, derived from this script's location (noemaforge/tools/).
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
pkg_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
cli="$pkg_root/src/noema_cli.py"

if [ ! -f "$cli" ]; then
    echo "FAIL: cannot find $cli — run this script from a NoemaForge checkout." >&2
    exit 1
fi

# Resolve Python: $NOEMAFORGE_PYTHON override -> python3 -> python.
if [ -n "${NOEMAFORGE_PYTHON:-}" ]; then
    py="$NOEMAFORGE_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
    py="python3"
elif command -v python >/dev/null 2>&1; then
    py="python"
else
    echo "FAIL: no Python found. Install Python 3.10+ and re-run." >&2
    exit 1
fi

echo "NoemaForge: starting via $py $cli start $*"
exec "$py" "$cli" start "$@"
