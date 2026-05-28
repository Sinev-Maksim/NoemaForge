#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/bootstrap/build-driver-vault-wsl.sh
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
# File: bootstrap/build-driver-vault-wsl.sh
# Purpose: Provide the script 'build-driver-vault-wsl'.
# Invoked by: shell operators or wrapper scripts.
# Inputs: Positional arguments, environment variables, and files read below.
# Outputs: Console output and filesystem side effects.
# AutoDoc: refreshed 2026-04-09 (heuristic)
# === End NoemaForge Autodoc File Header ===




set -euo pipefail

# build-driver-vault-wsl.sh
#
# Purpose:
#   Build a local "driver vault" (firmware/microcode debs) inside the seed-kit:
#     <seed/noemaforge>/driver-vault/debs/
#
# This is meant as an offline safety net for hardware enablement when:
# - the target has no network
# - you move the NoemaForge disk to new hardware
# - you need a firmware/microcode package that wasn't installed initially
#
# Usage:
#   build-driver-vault-wsl.sh /mnt/c/noemaforge/seed/noemaforge
#   build-driver-vault-wsl.sh /mnt/c/noemaforge/seed/noemaforge --include-nvidia
#
# Notes:
# - Must run inside WSL/Linux with network access.
# - By default, we avoid downloading nvidia-driver (large) unless requested.

ROOT="${1:-}"
if [[ -z "$ROOT" ]]; then
  echo "usage: $0 <seed/noemaforge root> [--include-nvidia] [--no-apt-update]" >&2
  exit 2
fi
shift || true

INCLUDE_NVIDIA="0"
NO_APT_UPDATE="0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --include-nvidia) INCLUDE_NVIDIA="1"; shift;;
    --no-apt-update) NO_APT_UPDATE="1"; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

if [[ ! -d "$ROOT" ]] || [[ ! -d "$ROOT/configs" ]]; then
  echo "ERROR: ROOT does not look like seed/noemaforge: $ROOT" >&2
  exit 2
fi

POLICY="$ROOT/configs/installer-policy.yaml"
VAULT_DIR="$ROOT/driver-vault/debs"
mkdir -p "$VAULT_DIR"

if [[ "$NO_APT_UPDATE" != "1" ]]; then
  sudo apt-get update -y
fi
sudo apt-get install -y python3 python3-yaml >/dev/null

PKG_LIST_FILE="$(mktemp)"
export POLICY INCLUDE_NVIDIA
python3 - <<'PY' >"$PKG_LIST_FILE"
import os, sys

policy = os.environ.get('POLICY','')
include_nvidia = os.environ.get('INCLUDE_NVIDIA','0') == '1'

pkgs = set()
try:
    import yaml
    pol = yaml.safe_load(open(policy,'r',encoding='utf-8')) or {}
    cat = pol.get('bundle_catalog') or {}
    for bid, b in (cat.items() if isinstance(cat, dict) else []):
        if not isinstance(b, dict):
            continue
        if str(b.get('kind') or '').strip() != 'apt-packages':
            continue
        if (not include_nvidia) and ('nvidia' in str(bid).lower()):
            continue
        for p in (b.get('packages') or []):
            if p:
                pkgs.add(str(p).strip())
except Exception as e:
    print(f"#WARN policy parse failed: {e!r}", file=sys.stderr)

for p in sorted([x for x in pkgs if x and isinstance(x,str)]):
    print(p)
PY

mapfile -t PKGS < <(grep -v '^#' "$PKG_LIST_FILE" | sed '/^\s*$/d')

echo "[driver-vault-wsl] Packages to fetch: ${#PKGS[@]}" >&2

if [[ "$NO_APT_UPDATE" != "1" ]]; then
  sudo apt-get update -y
fi

# Download-only into the vault dir (as cache).
sudo apt-get -y \
  -o Dir::Cache::archives="$VAULT_DIR" \
  --download-only \
  install --no-install-recommends \
  "${PKGS[@]}"

# Build a tiny manifest for audit.
MAN="$ROOT/driver-vault/manifest.json"
export VAULT_DIR MAN
python3 - <<'PY'
import hashlib, json, os, time

vault = os.environ.get('VAULT_DIR','')
out = os.environ.get('MAN','')

files = []
for fn in sorted(os.listdir(vault)):
    if fn.endswith('.deb'):
        p = os.path.join(vault, fn)
        h = hashlib.sha256(open(p,'rb').read()).hexdigest()
        files.append({'file': fn, 'sha256': h, 'bytes': os.path.getsize(p)})

obj = {
  'schema': 'noemaforge.driver_vault/v1',
  'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
  'count': len(files),
  'files': files,
}
open(out,'w',encoding='utf-8').write(json.dumps(obj, ensure_ascii=False, indent=2))
print(out)
PY

rm -f "$PKG_LIST_FILE"

echo "[driver-vault-wsl] Vault ready at: $VAULT_DIR" >&2
