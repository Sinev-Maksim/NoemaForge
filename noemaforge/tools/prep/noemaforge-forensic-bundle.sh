#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/prep/noemaforge-forensic-bundle.sh
# Zone: prep/forensics
# Purpose: Create a small no-weights operator support bundle for MVP/MWP troubleshooting.
# Safety: Read-only against runtime state; intentionally excludes model weights and Vault content.
# === End NoemaForge File Header ===
set -euo pipefail

OUT_ROOT="${1:-/var/lib/noemaforge/forensics}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BASE="$OUT_ROOT/noemaforge-forensics-$STAMP"
mkdir -p "$BASE"

copy_if_exists() {
  local src="$1" dst="$2"
  if [[ -e "$src" ]]; then
    mkdir -p "$(dirname "$BASE/$dst")"
    cp -a "$src" "$BASE/$dst" 2>/dev/null || true
  fi
}

run_capture() {
  local name="$1"; shift
  ( "$@" ) > "$BASE/$name.txt" 2>&1 || true
}

{
  printf '# NoemaForge forensic bundle — %s\n\n' "$STAMP"
  cat <<'EOF'
Read-only operator support bundle. It should not include GGUF model weights or
Vault documents. Use it to debug launcher, firstboot, service, mount and pipeline
state.
EOF
} > "$BASE/README.md"

copy_if_exists /etc/os-release etc/os-release
copy_if_exists /var/lib/noemaforge/bootstrap/firstboot-status.json bootstrap/firstboot-status.json
copy_if_exists /var/lib/noemaforge/bootstrap/modelstore-validation.safe.json bootstrap/modelstore-validation.safe.json
copy_if_exists /var/lib/noemaforge/bootstrap/model-inventory.json bootstrap/model-inventory.json
copy_if_exists /var/lib/noemaforge/bootstrap/dataset-inventory.json bootstrap/dataset-inventory.json
copy_if_exists /var/lib/noemaforge/bootstrap/role-tournament-results.json bootstrap/role-tournament-results.json
copy_if_exists /var/lib/modelstore/model_registry.json modelstore/model_registry.json

run_capture systemctl-failed systemctl --failed --no-pager
run_capture systemctl-core systemctl status noemaforge-llm-gateway noemaforge-toolproxy noemaforge-llama@main --no-pager
run_capture timers systemctl list-timers 'noemaforge-*' --no-pager
run_capture findmnt findmnt
run_capture noemaforge-run ls -lah /run/noemaforge /run/noemaforge/llm /run/noemaforge/llm/backends
run_capture memory free -h
run_capture uname uname -a
if command -v nvidia-smi >/dev/null 2>&1; then
  run_capture nvidia-smi nvidia-smi
fi
if command -v noemaforge >/dev/null 2>&1; then
  run_capture noemaforge-status noemaforge status --json
  run_capture noemaforge-trixie-preflight noemaforge trixie-preflight --json
fi

(
  cd "$OUT_ROOT"
  tar -czf "noemaforge-forensics-$STAMP.tar.gz" "noemaforge-forensics-$STAMP"
  sha256sum "noemaforge-forensics-$STAMP.tar.gz" > "noemaforge-forensics-$STAMP.tar.gz.sha256"
)

echo "$OUT_ROOT/noemaforge-forensics-$STAMP.tar.gz"
