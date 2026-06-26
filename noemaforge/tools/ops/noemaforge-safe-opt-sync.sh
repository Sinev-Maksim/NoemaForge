#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SOURCE="${NOEMAFORGE_SYNC_SOURCE:-${PACKAGE_ROOT}}"
TARGET="${NOEMAFORGE_SYNC_TARGET:-/opt/noemaforge}"

PYTHON_BIN="${PYTHON:-python3}"

exec "${PYTHON_BIN}" "${PACKAGE_ROOT}/src/opt_sync_guard.py" \
  --source "${SOURCE}" \
  --target "${TARGET}" \
  "$@"
