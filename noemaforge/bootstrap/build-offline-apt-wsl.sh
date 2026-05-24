#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/bootstrap/build-offline-apt-wsl.sh
# Zone: release/package
# Version: 0.31.13.alpha-patched1
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
# File: bootstrap/build-offline-apt-wsl.sh
# Purpose: Provide the script 'build-offline-apt-wsl'.
# Invoked by: shell operators or wrapper scripts.
# Inputs: Positional arguments, environment variables, and files read below.
# Outputs: Console output and filesystem side effects.
# AutoDoc: refreshed 2026-04-09 (heuristic)
# === End NoemaForge Autodoc File Header ===




set -euo pipefail

# build-offline-apt-wsl.sh
#
# Purpose (Windows + WSL builder):
#   Build an **offline APT repo** and place it into the seed-kit at:
#     <seed/noemaforge>/offline-apt/aptrepo/
#
# Why:
#   The NoemaForge bootstrap can be fully offline. But to install its baseline
#   spine packages on a no-network target, you must ship a local file: apt repo.
#
# Usage:
#   build-offline-apt-wsl.sh /mnt/c/noemaforge/seed/noemaforge
#   build-offline-apt-wsl.sh /mnt/c/noemaforge/seed/noemaforge --emit-bundle
#   build-offline-apt-wsl.sh /mnt/c/noemaforge/seed/noemaforge --plan /path/to/offline-apt-plan.json
#   build-offline-apt-wsl.sh /mnt/c/noemaforge/seed/noemaforge --bundles driverpack-intel-wifi --extra ffmpeg
#
# Notes:
# - Must run inside WSL/Linux with network access.
# - Uses apt-get --download-only, and dpkg-scanpackages.

ROOT="${1:-}"
if [[ -z "$ROOT" ]]; then
  echo "usage: $0 <seed/noemaforge root> [--plan <json>] [--bundles <id...>] [--extra <pkg...>] [--repo-dir <path>] [--emit-bundle]" >&2
  exit 2
fi
shift || true

PLAN_JSON=""
REPO_DIR=""
EMIT_BUNDLE="0"
BUNDLES=()
EXTRA_PKGS=()
NO_APT_UPDATE="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan) PLAN_JSON="$2"; shift 2;;
    --repo-dir) REPO_DIR="$2"; shift 2;;
    --bundles)
      shift
      while [[ $# -gt 0 ]] && [[ ! "$1" =~ ^-- ]]; do
        BUNDLES+=("$1")
        shift
      done
      ;;
    --extra)
      shift
      while [[ $# -gt 0 ]] && [[ ! "$1" =~ ^-- ]]; do
        EXTRA_PKGS+=("$1")
        shift
      done
      ;;
    --emit-bundle) EMIT_BUNDLE="1"; shift;;
    --no-apt-update) NO_APT_UPDATE="1"; shift;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$REPO_DIR" ]]; then
  REPO_DIR="$ROOT/offline-apt/aptrepo"
fi

if [[ ! -d "$ROOT" ]] || [[ ! -d "$ROOT/bootstrap" ]] || [[ ! -d "$ROOT/configs" ]]; then
  echo "ERROR: ROOT does not look like seed/noemaforge: $ROOT" >&2
  exit 2
fi

BOOTSTRAP="$ROOT/bootstrap/noemaforge-bootstrap.sh"
POLICY="$ROOT/configs/installer-policy.yaml"

mkdir -p "$REPO_DIR/debs"

echo "[offline-apt-wsl] Ensuring builder deps" >&2
if [[ "$NO_APT_UPDATE" != "1" ]]; then
  sudo apt-get update -y
fi
sudo apt-get install -y python3 python3-yaml dpkg-dev >/dev/null

# Compute package list:
# - Always include bootstrap BASE_PKGS (spine bring-up).
# - If PLAN_JSON provided, merge its packages.
# - Else: include installer-policy defaults (apt_baseline + default bundles packages).
# - Add optional bundle ids + extra packages.
PKG_LIST_FILE="$(mktemp)"

export BOOTSTRAP POLICY PLAN_JSON
export BUNDLES_STR EXTRA_STR
BUNDLES_STR="$(printf "%s\n" "${BUNDLES[@]-}")"
EXTRA_STR="$(printf "%s\n" "${EXTRA_PKGS[@]-}")"

python3 - <<'PY' >"$PKG_LIST_FILE"
import json, os, re, sys

bootstrap = os.environ.get('BOOTSTRAP','')
policy = os.environ.get('POLICY','')
plan_json = os.environ.get('PLAN_JSON','')
bundles = [x for x in (os.environ.get('BUNDLES_STR','').split('\n')) if x.strip()]
extra = [x for x in (os.environ.get('EXTRA_STR','').split('\n')) if x.strip()]

pkgs = set()

# 1) Parse bootstrap BASE_PKGS
try:
    txt = open(bootstrap, 'r', encoding='utf-8', errors='ignore').read()
    m = re.search(r'^BASE_PKGS=\(([^)]*)\)', txt, flags=re.MULTILINE)
    if m:
        for t in m.group(1).split():
            t=t.strip().strip('"').strip("'")
            if t and not t.startswith('$') and '@' not in t:
                pkgs.add(t)
except Exception as e:
    print(f"#WARN bootstrap parse failed: {e!r}", file=sys.stderr)

# 2) If plan json, merge
if plan_json:
    try:
        obj = json.load(open(plan_json,'r',encoding='utf-8'))
        for p in (obj.get('packages') or []):
            if p:
                pkgs.add(str(p).strip())
    except Exception as e:
        print(f"#WARN plan json parse failed: {e!r}", file=sys.stderr)

# 3) Installer policy defaults (+ bundle_catalog for bundles)
try:
    import yaml
    pol = yaml.safe_load(open(policy,'r',encoding='utf-8')) or {}
    defaults = pol.get('defaults') or {}
    for p in (defaults.get('apt_baseline') or []):
        if p:
            pkgs.add(str(p).strip())

    bundle_catalog = pol.get('bundle_catalog') or {}

    # default bundles
    for b in (defaults.get('bundles') or []):
        if not isinstance(b, dict):
            continue
        bid = str(b.get('id') or '').strip()
        if not bid:
            continue
        bb = bundle_catalog.get(bid) or {}
        if str(bb.get('kind') or '').strip() != 'apt-packages':
            continue
        for p in (bb.get('packages') or []):
            if p:
                pkgs.add(str(p).strip())

    # user-requested bundles
    for bid in bundles:
        bb = bundle_catalog.get(bid) or {}
        if str(bb.get('kind') or '').strip() != 'apt-packages':
            continue
        for p in (bb.get('packages') or []):
            if p:
                pkgs.add(str(p).strip())
except Exception as e:
    print(f"#WARN installer policy parse failed: {e!r}", file=sys.stderr)

# 4) extras
for p in extra:
    pkgs.add(str(p).strip())

# Emit sorted list
for p in sorted([x for x in pkgs if x and isinstance(x,str)]):
    print(p)
PY

mapfile -t PKGS < <(grep -v '^#' "$PKG_LIST_FILE" | sed '/^\s*$/d')

echo "[offline-apt-wsl] Packages to fetch: ${#PKGS[@]}" >&2

# Download packages into repo cache
if [[ "$NO_APT_UPDATE" != "1" ]]; then
  sudo apt-get update -y
fi

sudo apt-get -y \
  -o Dir::Cache::archives="$REPO_DIR/debs" \
  --download-only \
  install --no-install-recommends \
  "${PKGS[@]}"

# Build Packages index
(
  cd "$REPO_DIR"
  dpkg-scanpackages debs /dev/null > Packages
  gzip -kf Packages
)

# Save the exact package list for audit
mkdir -p "$ROOT/offline-apt"
cp -f "$PKG_LIST_FILE" "$ROOT/offline-apt/packages.list"

echo "[offline-apt-wsl] Repo ready at: $REPO_DIR" >&2

if [[ "$EMIT_BUNDLE" == "1" ]]; then
  echo "[offline-apt-wsl] Emitting AptRepoBundle tar+manifest" >&2
  OUT_DIR="$ROOT/offline-apt/outbox"
  mkdir -p "$OUT_DIR"
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  BUNDLE_ID="aptrepo-${TS}"
  ART="$OUT_DIR/${BUNDLE_ID}.tar.gz"
  MF="$OUT_DIR/${BUNDLE_ID}.manifest.yaml"

  # IMPORTANT: tarball must extract with Packages at top-level (no nested aptrepo/ dir)
  tar -C "$REPO_DIR" -czf "$ART" .
  ASHA="$(sha256sum "$ART" | awk '{print $1}')"

  cat >"$MF" <<__YAML__
apiVersion: noemaforge.bundle/v1
kind: AptRepoBundle
bundle_id: ${BUNDLE_ID}
created_at: "${TS}"
artifact_format: tar.gz
artifact_sha256: ${ASHA}
notes:
  - "Built via WSL builder"
  - "Repo root contains Packages/Packages.gz and debs/"
__YAML__

  MSHA="$(sha256sum "$MF" | awk '{print $1}')"

  echo "[offline-apt-wsl] artifact_sha256=$ASHA" >&2
  echo "[offline-apt-wsl] manifest_sha256=$MSHA" >&2
  echo "[offline-apt-wsl] manifest=$MF" >&2
  echo "[offline-apt-wsl] artifact=$ART" >&2
fi

rm -f "$PKG_LIST_FILE"
