#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/uat/run-self-improvement-uat-preflight.sh
# Zone: release/package
# Version: 0.33.0
# Created: 2026-07-24
# Modified: 2026-07-24
# Purpose: Run the self-improvement pipeline immediately before and at the start of target-host UAT through the real authenticated Admin GUI boundary.
# Inputs: Exact clean repository checkout, optional expected head, free loopback port and local curl/python/git tools.
# Outputs: Redacted UAT evidence bundle under an operator-owned state directory.
# Side effects: Starts and stops one isolated loopback Admin GUI process; writes only under the evidence directory.
# Tests: bash -n in premerge; full execution is target-host UAT only.
# Notes: Never applies/commits/pushes/releases; bootstrap token and cookie jar are deleted or redacted before completion.
# === End NoemaForge File Header ===
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
EXPECTED_HEAD=""
PORT=8876
OUT=""

usage() {
  cat <<'USAGE'
Usage:
  run-self-improvement-uat-preflight.sh [--repo-root PATH] [--expected-head SHA] [--port 8876] [--out DIR]

The repository must be a clean exact checkout. The script runs:
  A. CLI proposal/test-only self-improvement preflight.
  B. Real isolated dashboard bootstrap and authenticated GUI preflight.
  C. Negative owner-session, cross-origin and unlisted-route checks.

No source apply, commit, push, merge or release action is permitted.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    --expected-head) EXPECTED_HEAD="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    -h|--help|help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

[[ -n "$REPO_ROOT" ]] || { echo "not inside a git checkout; pass --repo-root" >&2; exit 2; }
REPO_ROOT="$(cd "$REPO_ROOT" && pwd -P)"
PACKAGE_ROOT="$REPO_ROOT/noemaforge"
[[ -f "$PACKAGE_ROOT/src/code_evolution_uat_preflight.py" ]] || { echo "missing UAT preflight runtime" >&2; exit 2; }
[[ -x "$PACKAGE_ROOT/tools/prep/noemaforge-dashboard.sh" || -f "$PACKAGE_ROOT/tools/prep/noemaforge-dashboard.sh" ]] || { echo "missing dashboard launcher" >&2; exit 2; }
command -v git >/dev/null
command -v python3 >/dev/null
command -v curl >/dev/null

HEAD_BEFORE="$(git -C "$REPO_ROOT" rev-parse HEAD)"
if [[ -n "$EXPECTED_HEAD" && "$HEAD_BEFORE" != "$EXPECTED_HEAD" ]]; then
  echo "exact-head mismatch: actual=$HEAD_BEFORE expected=$EXPECTED_HEAD" >&2
  exit 3
fi
if [[ -n "$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "repository must be clean before target-host UAT" >&2
  exit 3
fi

if [[ -z "$OUT" ]]; then
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  OUT="${XDG_STATE_HOME:-$HOME/.local/state}/noemaforge-uat/self-improvement-$stamp"
fi
mkdir -p "$OUT"
chmod 700 "$OUT"
OUT="$(cd "$OUT" && pwd -P)"
DATA_ROOT="$OUT/data"
XDG_UAT_STATE="$OUT/xdg-state"
CONF="$OUT/noemaforge-uat.conf"
COOKIE_JAR="$OUT/.owner-cookie.jar"
DASHBOARD_CAPTURE="$OUT/.dashboard-start.raw"
DASHBOARD_LOG="$XDG_UAT_STATE/noemaforge/dashboard.log"
SUMMARY="$OUT/summary.json"
mkdir -p "$DATA_ROOT" "$XDG_UAT_STATE"
chmod 700 "$DATA_ROOT" "$XDG_UAT_STATE"

cleanup() {
  set +e
  env \
    XDG_STATE_HOME="$XDG_UAT_STATE" \
    NOEMAFORGE_CONFIG_FILE="$CONF" \
    NOEMAFORGE_ROOT="$PACKAGE_ROOT" \
    bash "$PACKAGE_ROOT/tools/prep/noemaforge-dashboard.sh" stop --root "$PACKAGE_ROOT" --port "$PORT" \
    >/dev/null 2>&1
  rm -f "$COOKIE_JAR" "$DASHBOARD_CAPTURE" "$XDG_UAT_STATE/noemaforge/owner-bootstrap.token"
}
trap cleanup EXIT INT TERM

cat > "$CONF" <<CONFEOF
[noemaforge]
install_root = $PACKAGE_ROOT
data_root = $DATA_ROOT
version = 0.33.0

[paths]
gui_state_dir = $DATA_ROOT/gui
sessions_dir = $DATA_ROOT/gui/sessions
jobs_dir = $DATA_ROOT/jobs
event_log_dir = $DATA_ROOT/events
pipelines_dir = $DATA_ROOT/pipelines
model_selection_state_dir = $DATA_ROOT/model-selection
model_evolution_state_dir = $DATA_ROOT/model-evolution
dev_team_state_dir = $DATA_ROOT/dev-team
code_evolution_state_dir = $DATA_ROOT/code-evolution
runtime_dir = $DATA_ROOT/runtime
bootstrap_dir = $DATA_ROOT/bootstrap
share_dir = $DATA_ROOT/share
modelstore_dir = $DATA_ROOT/modelstore
vault_dir = $DATA_ROOT/vault
epoch_dir = $DATA_ROOT/epochs
persona_state_dir = $DATA_ROOT/personas
log_dir = $DATA_ROOT/logs

[gui]
host = 127.0.0.1
port = $PORT
CONFEOF
chmod 600 "$CONF"

python3 - "$PORT" <<'PY'
import socket
import sys
port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", port))
PY

STATUS_BEFORE="$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all | sha256sum | awk '{print $1}')"
TREE_BEFORE="$(git -C "$REPO_ROOT" ls-files -z | xargs -0 -r sha256sum | sha256sum | awk '{print $1}')"

# Phase A: exact checked-out tree, before the Admin GUI UAT.
PHASE_A_STATE="$OUT/phase-a-state"
mkdir -p "$PHASE_A_STATE"
python3 "$PACKAGE_ROOT/src/code_evolution_uat_preflight.py" \
  --root "$REPO_ROOT" \
  --state-dir "$PHASE_A_STATE" \
  --json > "$OUT/phase-a-preflight.json"
python3 - "$OUT/phase-a-preflight.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report.get("ok") is True, report
assert report.get("status") == "pass", report
assert report.get("apply") is False and report.get("commit") is False and report.get("publish") is False, report
assert all((report.get("invariants") or {}).values()), report
PY

# Start isolated dashboard. Capture the raw bootstrap URL only in a mode-0600 temporary file.
env \
  XDG_STATE_HOME="$XDG_UAT_STATE" \
  NOEMAFORGE_CONFIG_FILE="$CONF" \
  NOEMAFORGE_ROOT="$PACKAGE_ROOT" \
  bash "$PACKAGE_ROOT/tools/prep/noemaforge-dashboard.sh" start \
    --root "$PACKAGE_ROOT" \
    --state "$DATA_ROOT/pipelines" \
    --persona-state "$DATA_ROOT/personas" \
    --evolution-state "$DATA_ROOT/model-evolution" \
    --port "$PORT" > "$DASHBOARD_CAPTURE"
chmod 600 "$DASHBOARD_CAPTURE"

BOOTSTRAP_URL="$(sed -n 's/^NoemaForge owner bootstrap: //p' "$DASHBOARD_CAPTURE" | tail -n1)"
[[ "$BOOTSTRAP_URL" == http://127.0.0.1:"$PORT"/owner-bootstrap.html#* ]] || { echo "launcher did not produce bootstrap URL" >&2; exit 4; }
BOOTSTRAP_TOKEN="${BOOTSTRAP_URL#*#}"
[[ ${#BOOTSTRAP_TOKEN} -ge 32 ]] || { echo "bootstrap token too short" >&2; exit 4; }

# Redact every persisted copy before making HTTP requests.
python3 - "$DASHBOARD_CAPTURE" "$DASHBOARD_LOG" <<'PY'
from pathlib import Path
import re, sys
for raw in sys.argv[1:]:
    path = Path(raw)
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"(owner-bootstrap\.html)#[A-Za-z0-9_-]+", r"\1#<redacted>", text)
    path.write_text(text, encoding="utf-8")
PY

BASE_URL="http://127.0.0.1:$PORT"
for _ in $(seq 1 100); do
  if curl --silent --fail --max-time 1 "$BASE_URL/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.05
done
curl --silent --fail --max-time 2 "$BASE_URL/api/health" > "$OUT/health.json"

# Negative path before bootstrap: no proposal/test pipeline side effect.
PROPOSALS_BEFORE="$(find "$DATA_ROOT/code-evolution" -maxdepth 1 -name 'prop_*.json' 2>/dev/null | wc -l)"
UNAUTH_CODE="$(curl --silent --show-error --max-time 5 \
  -o "$OUT/negative-unauthenticated.json" -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -H "Origin: $BASE_URL" \
  -X POST "$BASE_URL/api/code-evolution/uat-preflight" \
  --data '{}')"
[[ "$UNAUTH_CODE" == "403" ]] || { echo "unauthenticated preflight was not denied: HTTP $UNAUTH_CODE" >&2; exit 5; }
PROPOSALS_AFTER_UNAUTH="$(find "$DATA_ROOT/code-evolution" -maxdepth 1 -name 'prop_*.json' 2>/dev/null | wc -l)"
[[ "$PROPOSALS_BEFORE" == "$PROPOSALS_AFTER_UNAUTH" ]] || { echo "unauthenticated request created proposal" >&2; exit 5; }

# One-time bootstrap exchange.
BOOTSTRAP_BODY="$(python3 - "$BOOTSTRAP_TOKEN" <<'PY'
import json, sys
print(json.dumps({"token": sys.argv[1]}))
PY
)"
BOOTSTRAP_CODE="$(curl --silent --show-error --max-time 5 \
  -c "$COOKIE_JAR" \
  -o "$OUT/bootstrap-response.json" -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -H "Origin: $BASE_URL" \
  -X POST "$BASE_URL/api/session/owner-bootstrap" \
  --data "$BOOTSTRAP_BODY")"
unset BOOTSTRAP_TOKEN BOOTSTRAP_BODY BOOTSTRAP_URL
[[ "$BOOTSTRAP_CODE" == "200" ]] || { echo "owner bootstrap failed: HTTP $BOOTSTRAP_CODE" >&2; exit 5; }
chmod 600 "$COOKIE_JAR"

# Cross-origin must fail before running the pipeline.
CROSS_CODE="$(curl --silent --show-error --max-time 5 \
  -b "$COOKIE_JAR" \
  -o "$OUT/negative-cross-origin.json" -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://attacker.example' \
  -X POST "$BASE_URL/api/code-evolution/uat-preflight" \
  --data '{}')"
[[ "$CROSS_CODE" == "403" ]] || { echo "cross-origin preflight was not denied: HTTP $CROSS_CODE" >&2; exit 5; }

# Valid authenticated phase B: same real pipeline through the Admin GUI boundary.
GUI_CODE="$(curl --silent --show-error --max-time 300 \
  -b "$COOKIE_JAR" \
  -o "$OUT/phase-b-gui-preflight.json" -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -H "Origin: $BASE_URL" \
  -X POST "$BASE_URL/api/code-evolution/uat-preflight" \
  --data '{}')"
[[ "$GUI_CODE" == "200" ]] || { echo "authenticated GUI preflight failed: HTTP $GUI_CODE" >&2; exit 6; }
python3 - "$OUT/phase-b-gui-preflight.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report.get("ok") is True, report
assert report.get("status") == "pass", report
assert report.get("mode") == "proposal_test_only", report
assert report.get("apply") is False and report.get("commit") is False and report.get("publish") is False, report
assert all((report.get("invariants") or {}).values()), report
PY

# Valid session still cannot reach a POST route absent from the inventory.
UNLISTED_CODE="$(curl --silent --show-error --max-time 5 \
  -b "$COOKIE_JAR" \
  -o "$OUT/negative-unlisted-route.json" -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -H "Origin: $BASE_URL" \
  -X POST "$BASE_URL/api/uat-unlisted-mutation" \
  --data '{}')"
[[ "$UNLISTED_CODE" == "403" ]] || { echo "unlisted mutation was not denied: HTTP $UNLISTED_CODE" >&2; exit 6; }

# Stop before final snapshots and remove secrets.
cleanup
trap - EXIT INT TERM
HEAD_AFTER="$(git -C "$REPO_ROOT" rev-parse HEAD)"
STATUS_AFTER="$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all | sha256sum | awk '{print $1}')"
TREE_AFTER="$(git -C "$REPO_ROOT" ls-files -z | xargs -0 -r sha256sum | sha256sum | awk '{print $1}')"
[[ "$HEAD_BEFORE" == "$HEAD_AFTER" ]] || { echo "git head changed during UAT" >&2; exit 7; }
[[ "$STATUS_BEFORE" == "$STATUS_AFTER" ]] || { echo "git worktree status changed during UAT" >&2; exit 7; }
[[ "$TREE_BEFORE" == "$TREE_AFTER" ]] || { echo "tracked source fingerprint changed during UAT" >&2; exit 7; }

python3 - "$SUMMARY" "$HEAD_BEFORE" "$STATUS_BEFORE" "$TREE_BEFORE" "$UNAUTH_CODE" "$BOOTSTRAP_CODE" "$CROSS_CODE" "$GUI_CODE" "$UNLISTED_CODE" "$OUT" <<'PY'
import json, sys
path, head, status_hash, tree_hash, unauth, bootstrap, cross, gui, unlisted, out = sys.argv[1:]
summary = {
    "apiVersion": "noemaforge.self-improvement-target-uat/v1",
    "kind": "SelfImprovementTargetUatSummary",
    "ok": True,
    "exact_head": head,
    "repository_status_sha256": status_hash,
    "tracked_tree_sha256": tree_hash,
    "phase_a_cli_preflight": "pass",
    "phase_b_gui_preflight": "pass",
    "http": {
        "unauthenticated_preflight": int(unauth),
        "owner_bootstrap": int(bootstrap),
        "cross_origin_preflight": int(cross),
        "authenticated_preflight": int(gui),
        "unlisted_mutation": int(unlisted),
    },
    "secrets_retained": False,
    "evidence_root": out,
}
open(path, "w", encoding="utf-8").write(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, sort_keys=True))
PY

echo "PASS: self-improvement target-host UAT preflight"
echo "evidence: $OUT"
