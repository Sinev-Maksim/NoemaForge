#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/prep/archive-firstboot-baseline.sh
# Zone: prep/forensics
# Purpose: Archive accepted degraded firstboot artifacts as a reproducible baseline reference.
# Safety: Read-only against runtime state; writes one timestamped tar.gz into /var/lib/noemaforge/bootstrap/baselines by default.
# === End NoemaForge File Header ===
set -euo pipefail

OUT_ROOT="${1:-/var/lib/noemaforge/bootstrap/baselines}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BASE="$OUT_ROOT/firstboot-baseline-$STAMP"
mkdir -p "$BASE"

copy_if_exists() {
  local src="$1" dst="$2"
  if [[ -e "$src" ]]; then
    mkdir -p "$(dirname "$BASE/$dst")"
    cp -a "$src" "$BASE/$dst"
  fi
}

copy_if_exists /var/lib/noemaforge/bootstrap/firstboot-status.json firstboot-status.json
copy_if_exists /var/lib/noemaforge/bootstrap/firstboot-events.jsonl firstboot-events.jsonl
copy_if_exists /var/lib/noemaforge/bootstrap/model-inventory.json model-inventory.json
copy_if_exists /var/lib/noemaforge/bootstrap/dataset-inventory.json dataset-inventory.json
copy_if_exists /var/lib/noemaforge/bootstrap/role-tournament-results.json role-tournament-results.json
copy_if_exists /var/lib/noemaforge/bootstrap/role-candidate-map.json role-candidate-map.json
copy_if_exists /var/lib/noemaforge/bootstrap/firstboot-staffing-summary.json firstboot-staffing-summary.json
copy_if_exists /var/lib/noemaforge/bootstrap/modelstore-validation.safe.json modelstore-validation.safe.json
copy_if_exists /var/lib/modelstore/model_registry.json model_registry.json

if [[ -d /var/lib/noemaforge/model_scorecards ]]; then
  mkdir -p "$BASE/model_scorecards"
  find /var/lib/noemaforge/model_scorecards -type f -name '*.json' -print0 2>/dev/null \
    | while IFS= read -r -d '' file; do
        rel="${file#/var/lib/noemaforge/model_scorecards/}"
        mkdir -p "$(dirname "$BASE/model_scorecards/$rel")"
        cp -a "$file" "$BASE/model_scorecards/$rel"
      done
fi

{
  printf '# NoemaForge firstboot baseline — %s\n\n' "$STAMP"
  cat <<'EOF2'
This bundle captures the accepted degraded firstboot state for regression checks.
It is safe to keep as local forensic/reference state and should not contain model weights.

Important fields to inspect:

- `firstboot-status.json`
- `firstboot-staffing-summary.json`
- `role-tournament-results.json`
- `role-candidate-map.json`
- `model_registry.json`
EOF2
} > "$BASE/README.md"

(
  cd "$OUT_ROOT"
  tar -czf "firstboot-baseline-$STAMP.tar.gz" "firstboot-baseline-$STAMP"
  sha256sum "firstboot-baseline-$STAMP.tar.gz" > "firstboot-baseline-$STAMP.tar.gz.sha256"
)

echo "$OUT_ROOT/firstboot-baseline-$STAMP.tar.gz"
