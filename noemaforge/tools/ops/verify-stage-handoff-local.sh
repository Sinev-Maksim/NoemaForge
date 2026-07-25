#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PYTHON="${NOEMAFORGE_VERIFY_PYTHON:-python}"
BASE="/tmp/noemaforge_stage_handoff_v2_verify"
STATE="$BASE/pipelines"
DATA_ROOT="$BASE/data"
MODELSTORE="$BASE/modelstore"
BOOTSTRAP="$BASE/bootstrap"
LOG="$BASE/admin-gui.log"
PIDFILE="$BASE/admin-gui.pid"
RUN_JSON="$BASE/create-run.json"
ADVANCE_JSON="$BASE/advance.json"
STATUS_JSON="$BASE/status.json"
REPLY_JSON="$BASE/reply.json"
HOST="127.0.0.1"
PORT="18081"
URL="http://${HOST}:${PORT}"
REPLY_TEXT="Operator verifier reply for stage handoff v2"

cleanup() {
  if [[ -f "$PIDFILE" ]]; then
    local pid
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  fi
}

fail() {
  echo "verify-stage-handoff-local: FAIL: $*" >&2
  if [[ -f "$LOG" ]]; then
    echo "----- admin gui log -----" >&2
    cat "$LOG" >&2 || true
    echo "----- end admin gui log -----" >&2
  fi
  cleanup
  exit 1
}

trap cleanup EXIT
rm -rf "$BASE"
mkdir -p "$STATE" "$DATA_ROOT" "$MODELSTORE/models/main" "$BOOTSTRAP"
printf '{"model_id":"local-verifier-main"}\n' > "$MODELSTORE/models/main/noemaforge-model.json"
printf 'verifier model placeholder\n' > "$MODELSTORE/models/main/model.gguf"

export NOEMAFORGE_ROOT="$ROOT/noemaforge"
export NOEMAFORGE_DATA_ROOT="$DATA_ROOT"
export NOEMAFORGE_PIPELINE_STATE="$STATE"
export NOEMAFORGE_MODELSTORE_DIR="$MODELSTORE"
export NOEMAFORGE_BOOTSTRAP_DIR="$BOOTSTRAP"
export NOEMAFORGE_GUI_DISABLE_LLM_CHAT=1

"$PYTHON" "$ROOT/noemaforge/src/admin_gui_server.py" \
  --root "$ROOT/noemaforge" \
  --state "$STATE" \
  --persona-state "$BASE/persona" \
  --evolution-state "$BASE/model-evolution" \
  --model-selection-state "$BASE/model-selection" \
  --dev-state "$BASE/dev-team" \
  --host "$HOST" \
  --port "$PORT" >"$LOG" 2>&1 &
echo "$!" > "$PIDFILE"

for _ in $(seq 1 80); do
  if curl -fsS "$URL/api/health" > "$BASE/health.json" 2>/dev/null; then
    break
  fi
  sleep 0.25
done
[[ -s "$BASE/health.json" ]] || fail "Admin GUI did not become healthy on ${URL}"

curl -fsS -X POST "$URL/api/pipeline/run" \
  -H 'Content-Type: application/json' \
  --data '{"pipeline":"evolution","request":"stage handoff verifier","allow_degraded":true}' \
  > "$RUN_JSON" || fail "failed to create pipeline run"

RUN_ID="$("$PYTHON" - "$RUN_JSON" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
run_id = data.get("run_id") or (data.get("stdout") or {}).get("run_id")
if not run_id:
    print("")
    raise SystemExit(1)
print(run_id)
PY
)" || fail "run_id could not be extracted from /api/pipeline/run"
[[ -n "$RUN_ID" ]] || fail "empty run_id extracted from /api/pipeline/run"

curl -fsS -X POST "$URL/api/pipeline/advance" \
  -H 'Content-Type: application/json' \
  --data "{\"run_id\":\"$RUN_ID\",\"next\":true,\"allow_degraded\":true,\"note\":\"stage handoff verifier advance\"}" \
  > "$ADVANCE_JSON" || fail "failed to advance pipeline run"

curl -fsS "$URL/api/pipeline/run/$RUN_ID/status" > "$STATUS_JSON" || fail "failed to fetch run status"
"$PYTHON" - "$STATUS_JSON" <<'PY' || fail "status assertions failed"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data.get("current_stage") == "architecture_clarification", data
assert data.get("clarification_required") is True, data
assert data.get("waiting_reason") == "stage_handoff_required", data
handoff = data.get("stage_handoff") or {}
assert handoff.get("persona"), data
assert len(data.get("questions") or []) > 0, data
PY

curl -fsS -X POST "$URL/api/pipeline/run/$RUN_ID/reply" \
  -H 'Content-Type: application/json' \
  --data "{\"stage\":\"architecture_clarification\",\"message\":\"$REPLY_TEXT\",\"action\":\"reply\"}" \
  > "$REPLY_JSON" || fail "failed to post operator reply"

"$PYTHON" - "$REPLY_JSON" "$REPLY_TEXT" <<'PY' || fail "reply file assertions failed"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
reply = sys.argv[2]
decisions = data.get("decisions_path")
jsonl = data.get("stage_input_path")
assert decisions and reply in open(decisions, encoding="utf-8").read(), data
assert jsonl and reply in open(jsonl, encoding="utf-8").read(), data
PY

cleanup
trap - EXIT
echo "verify-stage-handoff-local: PASS run_id=$RUN_ID"
