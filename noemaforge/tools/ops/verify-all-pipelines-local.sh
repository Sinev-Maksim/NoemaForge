#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PYTHON="${NOEMAFORGE_VERIFY_PYTHON:-python}"
BASE="/tmp/noemaforge_pipeline_cycle_verify"
STATE="$BASE/pipelines"
DATA_ROOT="$BASE/data"
MODELSTORE="$BASE/modelstore"
BOOTSTRAP="$BASE/bootstrap"
LOG="$BASE/admin-gui.log"
PIDFILE="$BASE/admin-gui.pid"
HOST="127.0.0.1"
PORT="18082"
URL="http://${HOST}:${PORT}"
SELECTION_REFRESH_DIR="${NOEMAFORGE_SELECTION_REFRESH_DIR:-}"
SELECTION_REFRESH_PRESERVE=""

cleanup() {
  if [[ -n "${SELECTION_REFRESH_PRESERVE:-}" && -d "$SELECTION_REFRESH_PRESERVE" ]]; then
    rm -rf "$SELECTION_REFRESH_PRESERVE" 2>/dev/null || true
  fi
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
  echo "verify-all-pipelines-local: FAIL: $*" >&2
  if [[ ! -f "$BASE/pipeline-audit-report.json" ]]; then
    "$PYTHON" - "$BASE" "$*" <<'PY' || true
import json
import os
import sys
from pathlib import Path
base = Path(sys.argv[1])
message = sys.argv[2]
report = {
    "ok": False,
    "triage_ok": False,
    "acceptance_ok": False,
    "catalog_count": 0,
    "completed_real_count": 0,
    "completed_degraded_scope_count": 0,
    "fail_actionably_count": 0,
    "blocked_missing_worker_count": 0,
    "blocked_backend_required_count": 0,
    "blocked_worker_cannot_execute_count": 0,
    "excluded_from_prod_scope_count": 0,
    "incomplete_count": 0,
    "unknown_count": 0,
    "placeholder_count": 0,
    "hang_or_loop_count": 0,
    "acceptance_failure_count": 1,
    "pipeline_ids": [],
    "pipelines": [],
    "blocking_pipelines": [{"pipeline_id": "__verifier__", "verdict": "VERIFY_FAILURE", "reason": message}],
    "remediation_backlog": [{"pipeline_id": "__verifier__", "verdict": "VERIFY_FAILURE", "action": message}],
    "failures": [message],
    "blocked": True,
}
(base / "pipeline-audit-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
(base / "pipeline-audit-report.md").write_text(
    "# Pipeline Cycle Audit\n\n"
    "- ok: `false`\n"
    "- triage_ok: `false`\n"
    "- acceptance_ok: `false`\n"
    "- catalog_count: `0`\n"
    "- completed_real_count: `0`\n"
    "- completed_degraded_scope_count: `0`\n"
    "- fail_actionably_count: `0`\n"
    "- blocked_missing_worker_count: `0`\n"
    "- blocked_backend_required_count: `0`\n"
    "- blocked_worker_cannot_execute_count: `0`\n"
    "- excluded_from_prod_scope_count: `0`\n"
    "- incomplete_count: `0`\n"
    "- unknown_count: `0`\n"
    "- placeholder_count: `0`\n"
    "- hang_or_loop_count: `0`\n"
    "- acceptance_failure_count: `1`\n"
    "- blocked: `true`\n\n"
    "## Blocking pipelines\n"
    f"- `__verifier__`: VERIFY_FAILURE - {message}\n\n"
    "## Remediation backlog\n"
    f"- `__verifier__`: {message}\n\n"
    "## Failures\n"
    f"- {message}\n",
    encoding="utf-8",
)
PY
  fi
  if [[ -f "$LOG" ]]; then
    echo "----- admin gui log -----" >&2
    cat "$LOG" >&2 || true
    echo "----- end admin gui log -----" >&2
  fi
  cleanup
  exit 1
}

trap cleanup EXIT
if [[ -n "$SELECTION_REFRESH_DIR" && -d "$SELECTION_REFRESH_DIR" ]]; then
  SELECTION_REFRESH_PRESERVE="$(mktemp -d /tmp/noemaforge-selection-refresh-preserve.XXXXXX)"
  cp -a "$SELECTION_REFRESH_DIR"/. "$SELECTION_REFRESH_PRESERVE"/
fi
rm -rf "$BASE"
mkdir -p "$STATE" "$DATA_ROOT" "$MODELSTORE/models/main" "$BOOTSTRAP"
if [[ -n "$SELECTION_REFRESH_DIR" ]]; then
  export NOEMAFORGE_SELECTION_REFRESH_DIR="$SELECTION_REFRESH_DIR"
  if [[ -n "$SELECTION_REFRESH_PRESERVE" ]]; then
    mkdir -p "$SELECTION_REFRESH_DIR"
    cp -a "$SELECTION_REFRESH_PRESERVE"/. "$SELECTION_REFRESH_DIR"/
    rm -rf "$SELECTION_REFRESH_PRESERVE"
    SELECTION_REFRESH_PRESERVE=""
  fi
fi
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

for _ in $(seq 1 100); do
  if curl -fsS "$URL/api/health" > "$BASE/health.json" 2>/dev/null; then
    break
  fi
  sleep 0.25
done
[[ -s "$BASE/health.json" ]] || fail "Admin GUI did not become healthy on ${URL}"

audit_rc=0
if "$PYTHON" - "$URL" "$BASE" <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

url = sys.argv[1].rstrip("/")
base = Path(sys.argv[2])
report_json = base / "pipeline-audit-report.json"
report_md = base / "pipeline-audit-report.md"


def http_json(path, body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


verify_scope = str(os.environ.get("NOEMAFORGE_VERIFY_SCOPE") or "prod").strip().lower()
if verify_scope not in {"prod", "degraded"}:
    verify_scope = "prod"


def unwrap_runtime_payload(response):
    if isinstance(response, dict) and isinstance(response.get("stdout"), dict):
        wrapper_metadata = {key: value for key, value in response.items() if key != "stdout"}
        return response["stdout"], wrapper_metadata
    return response, {}


def fail(message, report):
    report["ok"] = False
    report["triage_ok"] = False
    report["acceptance_ok"] = False
    report.setdefault("failures", []).append(message)
    record_report_failure(report, message)
    write_reports(report)
    raise SystemExit(message)


def finish_triaged(report):
    finalize_report(report)
    write_reports(report)
    raise SystemExit(2)


def status_snapshot(status):
    payload, wrapper_metadata = unwrap_runtime_payload(status)
    if not isinstance(payload, dict):
        payload = {}
    progress = payload.get("stage_progress") if isinstance(payload.get("stage_progress"), dict) else {}
    worker_state = payload.get("last_worker_execution_state") if isinstance(payload.get("last_worker_execution_state"), dict) else {}
    blocker = payload.get("actionable_blocker") if isinstance(payload.get("actionable_blocker"), dict) else {}
    worker_resolution = payload.get("worker_resolution")
    if not isinstance(worker_resolution, dict):
        worker_resolution = worker_state.get("worker_resolution") if isinstance(worker_state.get("worker_resolution"), dict) else blocker.get("worker_resolution")
    snapshot = {
        "status": payload.get("status"),
        "current_stage": payload.get("current_stage"),
        "waiting_reason": payload.get("waiting_reason"),
        "stable_status_hash": payload.get("stable_status_hash"),
        "stage_progress": progress,
        "stage_progress_changed": payload.get("stage_progress_changed"),
        "last_worker_execution_state": worker_state,
        "worker_resolution": worker_resolution if isinstance(worker_resolution, dict) else {},
        "output_path": payload.get("output_path") or (payload.get("stage_output_quality") or {}).get("path"),
        "output_quality": payload.get("output_quality") or payload.get("stage_output_quality") or {},
        "produced_output": payload.get("produced_output"),
        "actionable_blocker": blocker,
        "handoff_version": (payload.get("stage_handoff") or {}).get("handoff_version"),
    }
    if wrapper_metadata:
        snapshot["wrapper_metadata"] = wrapper_metadata
    return snapshot


def mark_hang_or_loop(report, entry, reason, status=None):
    entry["verdict"] = "HANG_OR_LOOP"
    entry.setdefault("failures", []).append(reason)
    if status:
        snap = status_snapshot(status)
        entry.setdefault("status_history", []).append(snap)
        entry["current_stage"] = snap.get("current_stage")
        entry["worker_resolution"] = snap.get("worker_resolution") or entry.get("worker_resolution") or {}
        entry["output_quality"] = snap.get("output_quality") or entry.get("output_quality") or {}
    finish_triaged(report)


def output_real(quality):
    return bool(
        quality
        and quality.get("exists")
        and quality.get("quality") == "real"
        and not quality.get("looks_placeholder")
        and not quality.get("pending")
        and int(quality.get("size_bytes") or 0) >= 80
    )


def placeholder_output(path):
    p = Path(path)
    if not p.exists() or not p.is_file():
        return False
    text = p.read_text(encoding="utf-8", errors="replace")
    stripped = text.strip()
    return ("Status: pending" in text or "Decision:\n\nRisk:" in text or "Next handoff:" in text) and len(stripped) < 260


def completed_has_placeholder(status):
    if str(status.get("status") or "").lower() not in {"completed", "done"}:
        return []
    run_dir = Path(str(status.get("run_dir") or ""))
    outputs = run_dir / "outputs"
    if not outputs.exists():
        return []
    return [str(p) for p in sorted(outputs.glob("*.md")) if placeholder_output(p)]


def completed_has_real_output(status):
    if not status_is_complete(status):
        return False
    run_dir = Path(str(status.get("run_dir") or ""))
    outputs = run_dir / "outputs"
    if not outputs.exists():
        return False
    for path in sorted(outputs.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".md":
            if not placeholder_output(path) and path.stat().st_size >= 80:
                return True
        elif path.stat().st_size > 0:
            return True
    return False


def degraded_plan_package_real(entry):
    blocker = entry.get("actionable_blocker") if isinstance(entry.get("actionable_blocker"), dict) else {}
    package = entry.get("degraded_plan_package") if isinstance(entry.get("degraded_plan_package"), dict) else {}
    if not package:
        package = blocker.get("degraded_plan_package") if isinstance(blocker.get("degraded_plan_package"), dict) else {}
    path = Path(str(package.get("path") or ""))
    quality = package.get("quality") if isinstance(package.get("quality"), dict) else {}
    if not path.exists() or not path.is_file() or path.name != "final_degraded_plan_package.json":
        return False
    if placeholder_output(path) or path.stat().st_size < 80:
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return False
    if payload.get("scope") != "degraded_plan_only":
        return False
    if "does not claim that backend execute stages ran" not in str(payload.get("statement") or ""):
        return False
    entry["degraded_plan_package"] = {"path": str(path), "size": path.stat().st_size, "quality": quality}
    return True


def policy_only_verdict(policy, scope):
    pipeline_scope = str((policy or {}).get("scope") or "prod_launchable")
    if pipeline_scope == "out_of_prod_scope":
        return {
            "verdict": "OUT_OF_PROD_SCOPE",
            "reason": "pipeline explicitly excluded from production verifier scope",
        }
    if scope == "prod" and pipeline_scope == "degraded_plan_only":
        return {
            "verdict": "DEGRADED_PLAN_ONLY_DEFERRED",
            "reason": "degraded-plan-only pipeline is outside strict prod launchable acceptance; rerun with NOEMAFORGE_VERIFY_SCOPE=degraded to validate its final plan package",
        }
    if pipeline_scope == "adapter_required" and adapter_policy_requires_backend(policy or {}):
        required_adapter = str((policy or {}).get("required_adapter") or (((policy or {}).get("required_adapters") or ["explicit pipeline adapter/capability"])[0]))
        required_capability = str((policy or {}).get("required_capability") or (((policy or {}).get("required_capabilities") or (policy or {}).get("backend_required_capabilities") or ["unknown"])[0]))
        return {
            "verdict": "ADAPTER_REQUIRED_DEFERRED",
            "reason": f"adapter_required: configure {required_adapter} and grant {required_capability}",
            "actionable_blocker": {
                "state": "blocked_backend_required",
                "status": "blocked_backend_required",
                "code": "adapter_required_for_pipeline",
                "stage_capabilities": (policy or {}).get("stage_capabilities") or [],
                "backend_required_capabilities": (policy or {}).get("backend_required_capabilities") or [],
                "required_adapter": required_adapter,
                "required_capability": required_capability,
                "required_adapters": (policy or {}).get("required_adapters") or ["explicit pipeline adapter/capability"],
                "message": f"Pipeline is classified as adapter_required; configure {required_adapter} and grant {required_capability} before verifier can execute it.",
                "next_actions": (policy or {}).get("next_actions") or [f"configure {required_adapter}", f"grant {required_capability}", "rerun verifier"],
            },
        }
    return {}


def status_is_complete(status):
    return str(status.get("status") or "").lower() in {"completed", "done"}


def status_is_incomplete(status):
    return str(status.get("status") or "").lower() in {"in_progress", "ready_for_admin_approval", "needs_clarification"}


def blocker_code(payload):
    payload, _wrapper_metadata = unwrap_runtime_payload(payload)
    if not isinstance(payload, dict):
        return ""
    blocker = payload.get("actionable_blocker")
    if isinstance(blocker, dict):
        return str(blocker.get("code") or blocker.get("state") or "")
    return str(payload.get("code") or payload.get("state") or "")


def classify_actionable(payload):
    payload, _wrapper_metadata = unwrap_runtime_payload(payload)
    if not isinstance(payload, dict):
        return "FAIL_ACTIONABLY"
    code = blocker_code(payload)
    if code == "adapter_required_for_pipeline":
        return "BLOCKED_BACKEND_REQUIRED"
    if code == "blocked_worker_cannot_execute":
        return "BLOCKED_WORKER_CANNOT_EXECUTE"
    if code.startswith("backend_required_for_") or payload.get("status") == "blocked_backend_required":
        return "BLOCKED_BACKEND_REQUIRED"
    if code == "blocked_missing_worker" or payload.get("blocked_missing_worker") is True:
        return "BLOCKED_MISSING_WORKER"
    return "FAIL_ACTIONABLY"


def append_acceptance_failure(report, entry, reason):
    if entry.get("verdict") == "BLOCKED_BACKEND_REQUIRED":
        blocker = entry.get("actionable_blocker") if isinstance(entry.get("actionable_blocker"), dict) else {}
        policy = entry.get("pipeline_scope_policy") if isinstance(entry.get("pipeline_scope_policy"), dict) else {}
        required_adapter = str(blocker.get("required_adapter") or policy.get("required_adapter") or (((blocker.get("required_adapters") or policy.get("required_adapters") or ["explicit pipeline adapter/capability"])[0])))
        required_capability = str(blocker.get("required_capability") or policy.get("required_capability") or (((blocker.get("backend_required_capabilities") or policy.get("backend_required_capabilities") or ["unknown"])[0])))
        reason = f"backend required: configure {required_adapter} and grant {required_capability}"
    entry.setdefault("acceptance_failures", []).append(reason)
    report.setdefault("blocking_pipelines", []).append(
        {
            "pipeline_id": entry.get("pipeline_id"),
            "run_id": entry.get("run_id"),
            "verdict": entry.get("verdict"),
            "reason": reason,
            "current_stage": entry.get("current_stage"),
        }
    )
    report.setdefault("remediation_backlog", []).append(
        {
            "pipeline_id": entry.get("pipeline_id"),
            "verdict": entry.get("verdict"),
            "action": reason,
        }
    )


def append_remediation(report, entry, action):
    report.setdefault("remediation_backlog", []).append(
        {
            "pipeline_id": entry.get("pipeline_id"),
            "verdict": entry.get("verdict"),
            "action": action,
        }
    )


DETERMINISTIC_LOCAL_STAGE_CAPABILITIES = {
    "text_plan",
    "text_review",
    "text_status",
    "text_documentation",
    "audit",
    "handoff",
    "dev_plan",
    "media_plan",
}


def adapter_policy_requires_backend(policy):
    capabilities = [str(item) for item in (policy.get("stage_capabilities") or []) if str(item or "").strip()]
    backend_required = [str(item) for item in (policy.get("backend_required_capabilities") or []) if str(item or "").strip()]
    unknown_or_disallowed = [
        capability
        for capability in capabilities
        if capability not in DETERMINISTIC_LOCAL_STAGE_CAPABILITIES
    ]
    if backend_required:
        return True
    if unknown_or_disallowed:
        return True
    return not capabilities


def record_report_failure(report, reason):
    report["acceptance_failure_count"] = max(1, int(report.get("acceptance_failure_count") or 0))
    report.setdefault("blocking_pipelines", []).append(
        {
            "pipeline_id": "__verifier__",
            "verdict": "VERIFY_FAILURE",
            "reason": reason,
        }
    )
    report.setdefault("remediation_backlog", []).append(
        {
            "pipeline_id": "__verifier__",
            "verdict": "VERIFY_FAILURE",
            "action": reason,
        }
    )


def finalize_report(report):
    report["blocking_pipelines"] = []
    report["remediation_backlog"] = []
    counts = {
        "completed_real_count": 0,
        "completed_degraded_scope_count": 0,
        "fail_actionably_count": 0,
        "blocked_missing_worker_count": 0,
        "blocked_backend_required_count": 0,
        "blocked_worker_cannot_execute_count": 0,
        "excluded_from_prod_scope_count": 0,
        "incomplete_count": 0,
        "unknown_count": 0,
        "placeholder_count": 0,
        "hang_or_loop_count": 0,
    }
    for entry in report.get("pipelines", []):
        verdict = entry.get("verdict") or "UNKNOWN"
        policy = entry.get("pipeline_scope_policy") if isinstance(entry.get("pipeline_scope_policy"), dict) else {}
        pipeline_scope = str(policy.get("scope") or "prod_launchable")
        if verdict == "COMPLETED_REAL_OUTPUT":
            counts["completed_real_count"] += 1
        elif verdict == "COMPLETED_DEGRADED_PLAN_PACKAGE":
            counts["completed_degraded_scope_count"] += 1
            if report.get("verify_scope") != "degraded" or pipeline_scope != "degraded_plan_only":
                counts["fail_actionably_count"] += 1
                append_acceptance_failure(report, entry, "degraded plan package is not acceptable in strict prod scope")
            elif not degraded_plan_package_real(entry):
                counts["fail_actionably_count"] += 1
                append_acceptance_failure(report, entry, "degraded plan package verdict is missing a real final_degraded_plan_package.json artifact")
        elif verdict == "DEGRADED_PLAN_ONLY_DEFERRED":
            counts["excluded_from_prod_scope_count"] += 1
            if report.get("verify_scope") == "degraded" and pipeline_scope == "degraded_plan_only":
                counts["fail_actionably_count"] += 1
                append_acceptance_failure(report, entry, "degraded-plan-only pipeline did not produce a real final_degraded_plan_package.json artifact")
        elif verdict == "OUT_OF_PROD_SCOPE":
            counts["excluded_from_prod_scope_count"] += 1
        elif verdict == "ADAPTER_REQUIRED_DEFERRED":
            counts["excluded_from_prod_scope_count"] += 1
            counts["blocked_backend_required_count"] += 1
            blocker = entry.get("actionable_blocker") if isinstance(entry.get("actionable_blocker"), dict) else {}
            required_adapter = str(blocker.get("required_adapter") or "explicit pipeline adapter/capability")
            required_capability = str(blocker.get("required_capability") or "unknown")
            append_remediation(report, entry, f"adapter_required: configure {required_adapter} and grant {required_capability}")
        elif verdict in {"FAIL_ACTIONABLY", "BLOCKED_WORKER_CANNOT_EXECUTE", "BLOCKED_BACKEND_REQUIRED"}:
            counts["fail_actionably_count"] += 1
            if verdict == "BLOCKED_BACKEND_REQUIRED":
                counts["blocked_backend_required_count"] += 1
                append_acceptance_failure(report, entry, "")
                continue
            if verdict == "BLOCKED_WORKER_CANNOT_EXECUTE":
                counts["blocked_worker_cannot_execute_count"] += 1
            append_acceptance_failure(report, entry, "pipeline failed actionably; triage is mapped but prod acceptance failed")
        elif verdict == "BLOCKED_MISSING_WORKER":
            counts["blocked_missing_worker_count"] += 1
            append_acceptance_failure(report, entry, "pipeline is blocked by missing worker")
        elif verdict == "INCOMPLETE":
            counts["incomplete_count"] += 1
            append_acceptance_failure(report, entry, "pipeline did not complete before verifier loop ended")
        elif verdict == "HANG_OR_LOOP":
            counts["hang_or_loop_count"] += 1
            append_acceptance_failure(report, entry, "pipeline did not complete before verifier loop ended")
        elif verdict in {"COMPLETED_WITH_PLACEHOLDER", "PLACEHOLDER_OUTPUT"}:
            counts["placeholder_count"] += 1
            append_acceptance_failure(report, entry, "pipeline completed with placeholder or pending outputs")
        else:
            counts["unknown_count"] += 1
            append_acceptance_failure(report, entry, "pipeline ended with unknown verifier state")
    report.update(counts)
    report["acceptance_failure_count"] = (
        counts["fail_actionably_count"]
        + counts["placeholder_count"]
        + counts["incomplete_count"]
        + counts["unknown_count"]
        + counts["hang_or_loop_count"]
        + counts["blocked_missing_worker_count"]
    )
    if report.get("failures"):
        report["acceptance_failure_count"] += len(report.get("failures") or [])
    report["acceptance_ok"] = report["acceptance_failure_count"] == 0 and not report.get("failures")
    report["triage_ok"] = not report.get("failures") and counts["unknown_count"] == 0
    report["ok"] = report["acceptance_ok"]
    return report


def write_reports(report):
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Pipeline Cycle Audit",
        "",
        f"- verify_scope: `{report.get('verify_scope', 'prod')}`",
        f"- ok: `{str(report.get('ok')).lower()}`",
        f"- triage_ok: `{str(report.get('triage_ok')).lower()}`",
        f"- acceptance_ok: `{str(report.get('acceptance_ok')).lower()}`",
        f"- catalog_count: `{report.get('catalog_count', 0)}`",
        f"- completed_real_count: `{report.get('completed_real_count', 0)}`",
        f"- completed_degraded_scope_count: `{report.get('completed_degraded_scope_count', 0)}`",
        f"- fail_actionably_count: `{report.get('fail_actionably_count', 0)}`",
        f"- blocked_missing_worker_count: `{report.get('blocked_missing_worker_count', 0)}`",
        f"- blocked_backend_required_count: `{report.get('blocked_backend_required_count', 0)}`",
        f"- blocked_worker_cannot_execute_count: `{report.get('blocked_worker_cannot_execute_count', 0)}`",
        f"- excluded_from_prod_scope_count: `{report.get('excluded_from_prod_scope_count', 0)}`",
        f"- incomplete_count: `{report.get('incomplete_count', 0)}`",
        f"- unknown_count: `{report.get('unknown_count', 0)}`",
        f"- placeholder_count: `{report.get('placeholder_count', 0)}`",
        f"- hang_or_loop_count: `{report.get('hang_or_loop_count', 0)}`",
        f"- acceptance_failure_count: `{report.get('acceptance_failure_count', 0)}`",
        "",
    ]
    lines.append("## Pipelines")
    for item in report.get("pipelines", []):
        lines.append(f"- `{item.get('pipeline_id')}`: {item.get('verdict')} run=`{item.get('run_id','')}` stage=`{item.get('current_stage','')}`")
        if item.get("pipeline_scope_policy"):
            policy = item["pipeline_scope_policy"]
            lines.append(f"  - pipeline_scope: `{policy.get('scope')}` reason=`{policy.get('reason')}`")
        for failure in item.get("failures", []):
            lines.append(f"  - failure: {failure}")
        for failure in item.get("acceptance_failures", []):
            lines.append(f"  - acceptance_failure: {failure}")
        if item.get("worker_resolution"):
            wr = item["worker_resolution"]
            lines.append(f"  - worker_resolution: ok=`{wr.get('ok')}` status=`{wr.get('worker_status')}` role=`{wr.get('resolved_role')}`")
        if item.get("output_quality"):
            oq = item["output_quality"]
            lines.append(f"  - output_quality: quality=`{oq.get('quality')}` size=`{oq.get('size_bytes')}` path=`{oq.get('path')}`")
        if item.get("actionable_blocker"):
            blocker = item["actionable_blocker"]
            lines.append(f"  - actionable_blocker: code=`{blocker.get('code') or blocker.get('state')}` status=`{blocker.get('status')}`")
        if item.get("degraded_plan_package"):
            package = item["degraded_plan_package"]
            lines.append(f"  - degraded_plan_package: path=`{package.get('path')}` size=`{package.get('size')}`")
        if item.get("status_history"):
            lines.append(f"  - status_history_count: `{len(item.get('status_history') or [])}`")
    if report.get("blocking_pipelines"):
        lines.extend(["", "## Blocking pipelines"])
        for item in report["blocking_pipelines"]:
            lines.append(f"- `{item.get('pipeline_id')}`: {item.get('verdict')} - {item.get('reason')}")
    if report.get("remediation_backlog"):
        lines.extend(["", "## Remediation backlog"])
        for item in report["remediation_backlog"]:
            lines.append(f"- `{item.get('pipeline_id')}`: {item.get('action')}")
    if report.get("failures"):
        lines.extend(["", "## Failures"])
        lines.extend(f"- {msg}" for msg in report["failures"])
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


catalog = http_json("/api/pipelines/catalog")
raw_items = catalog.get("pipelines") if isinstance(catalog, dict) else []
if isinstance(raw_items, dict):
    items = [{"id": pid, **(spec if isinstance(spec, dict) else {})} for pid, spec in raw_items.items()]
else:
    items = [item for item in raw_items if isinstance(item, dict)]
pipeline_ids = [str(item.get("id") or item.get("pipeline_id") or "") for item in items if str(item.get("id") or item.get("pipeline_id") or "")]
known = {"public_mwp", "evolution", "book", "knowledge_graph", "release_prep", "persona_evolution"}
missing = sorted(known - set(pipeline_ids))
report = {
    "ok": False,
    "triage_ok": False,
    "acceptance_ok": False,
    "verify_scope": verify_scope,
    "catalog_count": len(pipeline_ids),
    "pipeline_ids": pipeline_ids,
    "pipelines": [],
    "failures": [],
    "blocking_pipelines": [],
    "remediation_backlog": [],
}
if missing:
    fail(f"catalog missing required pipeline ids: {', '.join(missing)}", report)

stage_counts = {str(item.get("id") or item.get("pipeline_id")): len(item.get("stages") or []) for item in items}
catalog_by_id = {str(item.get("id") or item.get("pipeline_id")): item for item in items}
for pipeline_id in pipeline_ids:
    catalog_item = catalog_by_id.get(pipeline_id) or {}
    policy = catalog_item.get("pipeline_scope_policy") if isinstance(catalog_item.get("pipeline_scope_policy"), dict) else {}
    entry = {"pipeline_id": pipeline_id, "verdict": "UNKNOWN", "failures": [], "pipeline_scope_policy": policy}
    report["pipelines"].append(entry)
    policy_decision = policy_only_verdict(policy, verify_scope)
    if policy_decision:
        entry.update(policy_decision)
        blocker = entry.get("actionable_blocker") if isinstance(entry.get("actionable_blocker"), dict) else {}
        if blocker:
            blocker["pipeline_id"] = pipeline_id
        continue
    created = http_json("/api/pipeline/run", {"pipeline": pipeline_id, "request": f"all-pipeline verifier for {pipeline_id}", "allow_degraded": True})
    entry["create_response"] = created
    run_id = created.get("run_id") or ((created.get("stdout") or {}) if isinstance(created.get("stdout"), dict) else {}).get("run_id")
    if not run_id:
        entry["failures"].append("run_id could not be extracted")
        fail(f"{pipeline_id}: run_id could not be extracted from /api/pipeline/run", report)
    entry["run_id"] = run_id
    status = http_json(f"/api/pipeline/run/{run_id}/status")
    entry.setdefault("status_history", []).append(status_snapshot(status))
    if status.get("status") == "ready_for_admin_approval":
        approval = http_json("/api/pipeline/advance", {"run_id": run_id, "next": True, "allow_degraded": True, "note": "all-pipeline verifier approval"})
        entry.setdefault("actions", []).append({"ready_for_admin_approval": approval})
        status = http_json(f"/api/pipeline/run/{run_id}/status")
        entry.setdefault("status_history", []).append(status_snapshot(status))
    max_iter = max(1, 2 * int(stage_counts.get(pipeline_id) or len(status.get("stages") or []) or 1) + 5)
    seen_after_reply = set()
    for _ in range(max_iter):
        entry["current_stage"] = status.get("current_stage")
        snap = status_snapshot(status)
        entry.setdefault("status_history", []).append(snap)
        entry["worker_resolution"] = snap.get("worker_resolution") or entry.get("worker_resolution") or {}
        entry["output_quality"] = snap.get("output_quality") or entry.get("output_quality") or {}
        bad_completed = completed_has_placeholder(status)
        if bad_completed:
            entry["placeholder_outputs"] = [f"completed pipeline has placeholder outputs: {path}" for path in bad_completed]
            entry["verdict"] = "COMPLETED_WITH_PLACEHOLDER"
            break
        handoff = status.get("stage_handoff") or {}
        if handoff:
            before_stage = status.get("current_stage")
            before_version = handoff.get("handoff_version")
            reply = http_json(
                f"/api/pipeline/run/{run_id}/reply",
                {"stage": before_stage, "message": f"Verifier operator decision for {pipeline_id}/{before_stage}", "action": "reply"},
            )
            entry.setdefault("actions", []).append({"reply": reply})
            after_reply = http_json(f"/api/pipeline/run/{run_id}/status")
            entry.setdefault("status_history", []).append(status_snapshot(after_reply))
            after_handoff = after_reply.get("stage_handoff") or {}
            after_version = after_handoff.get("handoff_version")
            loop_key = (run_id, before_stage, after_version)
            if after_version == before_version:
                mark_hang_or_loop(report, entry, "identical handoff repeated after reply", after_reply)
            if loop_key in seen_after_reply:
                mark_hang_or_loop(report, entry, "same replied handoff version repeated", after_reply)
            seen_after_reply.add(loop_key)
            continued = http_json(
                "/api/pipeline/advance",
                {"run_id": run_id, "next": False, "allow_degraded": True, "note": f"all-pipeline verifier continue {before_stage}"},
            )
            entry.setdefault("actions", []).append({"continue": continued})
            continued_payload, continued_wrapper_metadata = unwrap_runtime_payload(continued)
            if not isinstance(continued_payload, dict):
                continued_payload = {}
            if continued_wrapper_metadata:
                entry.setdefault("wrapper_metadata", []).append({"continue": continued_wrapper_metadata})
            continued_snapshot = status_snapshot(continued)
            entry.setdefault("status_history", []).append(continued_snapshot)
            if continued_snapshot.get("worker_resolution"):
                entry["worker_resolution"] = continued_snapshot.get("worker_resolution") or entry.get("worker_resolution") or {}
            if continued_snapshot.get("output_quality"):
                entry["output_quality"] = continued_snapshot.get("output_quality") or entry.get("output_quality") or {}
            if continued_payload.get("actionable_blocker"):
                entry["actionable_blocker"] = continued_payload.get("actionable_blocker")
                entry["verdict"] = classify_actionable(continued_payload)
                if verify_scope == "degraded" and str(policy.get("scope") or "") == "degraded_plan_only" and entry["verdict"] == "BLOCKED_BACKEND_REQUIRED" and degraded_plan_package_real(entry):
                    entry["verdict"] = "COMPLETED_DEGRADED_PLAN_PACKAGE"
                break
            if isinstance(continued.get("worker_resolution"), dict):
                entry["worker_resolution"] = continued.get("worker_resolution")
            if isinstance(continued.get("output_quality"), dict):
                entry["output_quality"] = continued.get("output_quality")
            elif isinstance(continued.get("stage_output_quality"), dict):
                entry["output_quality"] = continued.get("stage_output_quality")
            status2 = http_json(f"/api/pipeline/run/{run_id}/status")
            entry.setdefault("status_history", []).append(status_snapshot(status2))
            progressed = status2.get("current_stage") != before_stage
            changed_version = ((status2.get("stage_handoff") or {}).get("handoff_version") not in {"", None, before_version})
            became_real = output_real(status2.get("stage_output_quality") or {})
            explicit_skip = bool(continued_payload.get("skipped_by_operator") or ((status2.get("operator_reply_state") or {}).get("state") == "skipped_by_operator"))
            actionable = bool(continued_payload.get("actionable_blocker") or status2.get("actionable_blocker"))
            if not (progressed or changed_version or became_real or explicit_skip or actionable):
                mark_hang_or_loop(report, entry, "continue after reply did not progress, change handoff, produce output, skip, or block actionably", status2)
            status = status2
            if actionable:
                entry["actionable_blocker"] = continued_payload.get("actionable_blocker") or status2.get("actionable_blocker")
                entry["verdict"] = classify_actionable(continued_payload) if blocker_code(continued_payload) else classify_actionable(status2)
                if verify_scope == "degraded" and str(policy.get("scope") or "") == "degraded_plan_only" and entry["verdict"] == "BLOCKED_BACKEND_REQUIRED" and degraded_plan_package_real(entry):
                    entry["verdict"] = "COMPLETED_DEGRADED_PLAN_PACKAGE"
                break
            continue
        if status_is_complete(status):
            if completed_has_real_output(status):
                entry["verdict"] = "COMPLETED_REAL_OUTPUT"
            else:
                entry["verdict"] = "PLACEHOLDER_OUTPUT"
                entry["placeholder_outputs"] = ["no real non-placeholder output found"]
            break
        if status.get("actionable_blocker"):
            entry["actionable_blocker"] = status.get("actionable_blocker")
            entry["verdict"] = classify_actionable(status)
            if verify_scope == "degraded" and str(policy.get("scope") or "") == "degraded_plan_only" and entry["verdict"] == "BLOCKED_BACKEND_REQUIRED" and degraded_plan_package_real(entry):
                entry["verdict"] = "COMPLETED_DEGRADED_PLAN_PACKAGE"
            break
        if status_is_incomplete(status):
            entry["verdict"] = "INCOMPLETE"
        else:
            entry["verdict"] = "UNKNOWN"
        break
    else:
        mark_hang_or_loop(report, entry, "max iteration count exceeded", status)
    if entry.get("failures"):
        fail(f"{pipeline_id}: audit failures present", report)

finalize_report(report)
write_reports(report)
if report["acceptance_ok"]:
    print("verify-all-pipelines-local: PASS acceptance_ok=true")
    raise SystemExit(0)
if report["triage_ok"]:
    print("verify-all-pipelines-local: FAIL acceptance_ok=false triage_ok=true")
    raise SystemExit(2)
raise SystemExit("pipeline audit failed before triage could map all failures")
PY
then
  audit_rc=0
else
  audit_rc=$?
fi

cleanup
trap - EXIT
if [[ "$audit_rc" -eq 0 ]]; then
  echo "verify-all-pipelines-local: PASS acceptance_ok=true"
  exit 0
fi
if [[ "$audit_rc" -eq 2 ]]; then
  echo "verify-all-pipelines-local: FAIL acceptance_ok=false triage_ok=true" >&2
  exit 2
fi
fail "pipeline audit failed"
