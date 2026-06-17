#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: ci/apply_rulesets.sh
# Zone: ci/security
# Purpose: Apply (idempotently) the branch-protection rulesets stored as code under
#   .github/rulesets/ to the GitHub repository via the REST API. This is the
#   re-apply / disaster-recovery path so the protection posture is reproducible and
#   reviewable, not click-only state that can silently drift or be removed.
# Inputs: gh CLI authenticated as a repo admin; .github/rulesets/*.json.
# Outputs: Creates or updates the named rulesets on the repo.
# Side effects: Mutates repository ruleset configuration (requires admin).
# Notes: Code comments are English-only. Run from the repo root.
# === End NoemaForge File Header ===
set -euo pipefail

# Syntax self-check: `bash ci/apply_rulesets.sh --selftest` validates the script
# without contacting GitHub (also enforced by the premerge bash -n gate).
if [ "${1:-}" = "--selftest" ]; then
  bash -n "$0" && echo "apply_rulesets: syntax OK"
  exit $?
fi

REPO="${1:-Sinev-Maksim/NoemaForge}"
RULESET_DIR=".github/rulesets"

command -v gh >/dev/null 2>&1 || { echo "gh CLI is required" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "jq is required" >&2; exit 1; }

# Map of existing ruleset name -> id, so re-runs UPDATE in place instead of
# creating duplicates. --paginate so rulesets beyond the first API page
# (per_page=30) are included; otherwise a later-page ruleset would be wrongly
# POST-created as a duplicate instead of PUT-updated.
# Emit one {name,id} object per line (a stream, not a single array): with
# --paginate each page is processed separately, so a per-page array wrapper
# would yield several arrays. A stream concatenates cleanly across pages.
existing="$(gh api --paginate "repos/$REPO/rulesets" --jq '.[] | {name, id}')"

for f in "$RULESET_DIR"/*.json; do
  [ -e "$f" ] || { echo "No ruleset files under $RULESET_DIR" >&2; exit 1; }
  name="$(jq -r '.name' "$f")"
  id="$(printf '%s\n' "$existing" | jq -r --arg n "$name" 'select(.name==$n) | .id' | head -n1)"
  if [ -n "$id" ] && [ "$id" != "null" ]; then
    echo "Updating ruleset '$name' (id $id) from $f"
    gh api -X PUT "repos/$REPO/rulesets/$id" --input "$f" \
      --jq '"  -> " + .name + " [" + .enforcement + "]: " + ([.rules[].type] | join(", "))'
  else
    echo "Creating ruleset '$name' from $f"
    gh api -X POST "repos/$REPO/rulesets" --input "$f" \
      --jq '"  -> " + .name + " [" + .enforcement + "]: " + ([.rules[].type] | join(", "))'
  fi
done

echo "Done. Current rulesets:"
gh api "repos/$REPO/rulesets" --jq '.[] | "  \(.id)  \(.name)  [\(.enforcement)]"'
