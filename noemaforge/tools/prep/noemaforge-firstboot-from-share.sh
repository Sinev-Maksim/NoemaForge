#!/usr/bin/env bash

# === NoemaForge Autodoc File Header ===
# File: tools/prep/noemaforge-firstboot-from-share.sh
# Purpose: Helper / validation script 'noemaforge-firstboot-from-share.sh'.
# Invoked by / imported from:
#   - direct operator invocation or test discovery
# Public API / entry functions:
#   - module-level helpers / CLI entrypoint
# Inputs:
#   - local filesystem paths, command-line arguments, and NoemaForge runtime/install state
# Output formats / side effects:
#   - local JSON/YAML/text artifacts or process exit status
# AutoDoc: refreshed 2026-04-13 (manual)
# === End NoemaForge Autodoc File Header ===


# === NoemaForge File Header ===
# File: tools/prep/noemaforge-firstboot-from-share.sh
# Zone: prep
# Purpose: Minimal host-side entrypoint for first-boot model staffing from a mounted NOEMAFORGE share.
# Callers: install runbook, bootstrap hints, operator shell.
# Inputs: --share-root, --vault-root, --shortlist-file, --candidate-limit, --top-k, --no-reboot.
# Outputs: firstboot status/events under /var/lib/noemaforge/bootstrap and orchestrator YAML result on stdout.
# Side effects: stages models, runs scorecards, emits/applies first model epoch, may reboot host unless --no-reboot is passed.
# Security notes:
#   - Uses the allowlisted firstboot orchestrator path only.
#   - Does not bypass runtime tool policy; this is install-time orchestration.
# === End NoemaForge File Header ===
set -euo pipefail

SHARE_ROOT="/mnt/noemaforge-share"
VAULT_ROOT=""
SHORTLIST_FILE=""
CANDIDATE_LIMIT="0"
TOP_K="0"
NO_REBOOT="0"
INCLUDE_DOWNLOAD_MIRROR="0"
ALLOW_INCOMPLETE_SHARDS="0"
SELECTION_MODE="normal"
COMPOSITE_TOP_N="-1"
DRY_RUN="0"
SHOW_CANDIDATES="0"
SHOW_COMPOSITIONS="0"
PER_MODEL_TIMEOUT="0"
TOTAL_TIMEOUT="0"
INCLUDE_UNVERIFIED="0"
YES_UNVERIFIED_RISK="0"
RETRY_FAILED_MODELS="0"
CLEAR_MODEL_HEALTH="0"
STRICT_ANY_FAIL="0"
ALLOW_FAILED_SELECTION="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --share-root) SHARE_ROOT="$2"; shift 2 ;;
    --vault-root) VAULT_ROOT="$2"; shift 2 ;;
    --shortlist-file) SHORTLIST_FILE="$2"; shift 2 ;;
    --candidate-limit) CANDIDATE_LIMIT="$2"; shift 2 ;;
    --top-k) TOP_K="$2"; shift 2 ;;
    --include-download-mirror) INCLUDE_DOWNLOAD_MIRROR="1"; shift ;;
    --allow-incomplete-shards) ALLOW_INCOMPLETE_SHARDS="1"; shift ;;
    --no-reboot) NO_REBOOT="1"; shift ;;
    --selection-mode) SELECTION_MODE="$2"; shift 2 ;;
    --composite-top-n) COMPOSITE_TOP_N="$2"; shift 2 ;;
    --fast) SELECTION_MODE="fast"; shift ;;
    --normal) SELECTION_MODE="normal"; shift ;;
    --full) SELECTION_MODE="full"; shift ;;
    --full_composite) SELECTION_MODE="full_composite"; if [[ $# -gt 1 && "$2" =~ ^[0-9]+$ ]]; then COMPOSITE_TOP_N="$2"; shift 2; else COMPOSITE_TOP_N="0"; shift; fi ;;
    --dry-run) DRY_RUN="1"; shift ;;
    --show-candidates) SHOW_CANDIDATES="1"; shift ;;
    --show-compositions) SHOW_COMPOSITIONS="1"; shift ;;
    --per-model-timeout) PER_MODEL_TIMEOUT="$2"; shift 2 ;;
    --total-timeout) TOTAL_TIMEOUT="$2"; shift 2 ;;
    --include-unverified) INCLUDE_UNVERIFIED="1"; shift ;;
    --yes-i-understand-unverified-risk) YES_UNVERIFIED_RISK="1"; shift ;;
    --retry-failed-models) RETRY_FAILED_MODELS="1"; shift ;;
    --clear-model-health) CLEAR_MODEL_HEALTH="1"; shift ;;
    --strict-any-fail) STRICT_ANY_FAIL="1"; shift ;;
    --allow-failed-selection) ALLOW_FAILED_SELECTION="1"; shift ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
    *) echo "[noemaforge-firstboot][ERROR] Unknown argument: $1" >&2; exit 1 ;;
  esac
done

PY_ARGS=(--share-root "$SHARE_ROOT")
[[ -n "$VAULT_ROOT" ]] && PY_ARGS+=(--vault-root "$VAULT_ROOT")
[[ -n "$SHORTLIST_FILE" ]] && PY_ARGS+=(--shortlist-file "$SHORTLIST_FILE")
[[ "$CANDIDATE_LIMIT" != "0" ]] && PY_ARGS+=(--candidate-limit "$CANDIDATE_LIMIT")
[[ "$TOP_K" != "0" ]] && PY_ARGS+=(--top-k "$TOP_K")
[[ "$NO_REBOOT" == "1" ]] && PY_ARGS+=(--no-reboot)
[[ "$INCLUDE_DOWNLOAD_MIRROR" == "1" ]] && PY_ARGS+=(--include-download-mirror)
[[ "$ALLOW_INCOMPLETE_SHARDS" == "1" ]] && PY_ARGS+=(--allow-incomplete-shards)
PY_ARGS+=(--selection-mode "$SELECTION_MODE" --composite-top-n "$COMPOSITE_TOP_N")
[[ "$DRY_RUN" == "1" ]] && PY_ARGS+=(--dry-run)
[[ "$SHOW_CANDIDATES" == "1" ]] && PY_ARGS+=(--show-candidates)
[[ "$SHOW_COMPOSITIONS" == "1" ]] && PY_ARGS+=(--show-compositions)
[[ "$PER_MODEL_TIMEOUT" != "0" ]] && PY_ARGS+=(--per-model-timeout "$PER_MODEL_TIMEOUT")
[[ "$TOTAL_TIMEOUT" != "0" ]] && PY_ARGS+=(--total-timeout "$TOTAL_TIMEOUT")
[[ "$INCLUDE_UNVERIFIED" == "1" ]] && PY_ARGS+=(--include-unverified)
[[ "$YES_UNVERIFIED_RISK" == "1" ]] && PY_ARGS+=(--yes-i-understand-unverified-risk)
[[ "$RETRY_FAILED_MODELS" == "1" ]] && PY_ARGS+=(--retry-failed-models)
[[ "$CLEAR_MODEL_HEALTH" == "1" ]] && PY_ARGS+=(--clear-model-health)
[[ "$STRICT_ANY_FAIL" == "1" ]] && PY_ARGS+=(--strict-any-fail)
[[ "$ALLOW_FAILED_SELECTION" == "1" ]] && PY_ARGS+=(--allow-failed-selection)

exec /usr/bin/python3 /opt/noemaforge/src/firstboot_orchestrator.py "${PY_ARGS[@]}"
