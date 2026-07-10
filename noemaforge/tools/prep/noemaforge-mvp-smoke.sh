#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/prep/noemaforge-mvp-smoke.sh
# Zone: prep/public-mwp
# Purpose: Read-only/minimal-write smoke for public MVP/MWP CLI, pipeline, persona and readiness surface.
# Safety: Writes only to a temporary pipeline state dir unless --state is supplied.
# === End NoemaForge File Header ===
set -euo pipefail

ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
STATE=""
JSON=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --state) STATE="$2"; shift 2 ;;
    --json) JSON=1; shift ;;
    -h|--help|help)
      cat <<'EOH'
Usage: noemaforge-mvp-smoke.sh [--root PATH] [--state PATH] [--json]

Checks the public MVP/MWP surface without requiring a running LLM:
  - noemaforge status JSON shape is present
  - Trixie preflight JSON shape is present
  - pipeline catalog/validate and pattern catalog work
  - persona catalog validates and writes activation/evolution context
  - public_mwp run can be created, approved, gated, repaired, diagnosed and exported
  - readiness, context-lint, compact, queue, metrics, schema validation, LLM lease and template-import surfaces work without a live LLM
  - dashboard state/launcher and persona doctor work without starting LLM
  - selftest telemetry, code QA sub-team and wiki incremental patch surfaces work offline
EOH
      exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$STATE" ]]; then
  STATE="$(mktemp -d /tmp/noemaforge-mvp-smoke.XXXXXX)"
fi
mkdir -p "$STATE"
CHECKS_DIR="$STATE/checks"
mkdir -p "$CHECKS_DIR"
NOEMAFORGE_BIN="$ROOT/bin/noemaforge"
[[ -x "$NOEMAFORGE_BIN" ]] || NOEMAFORGE_BIN="$(command -v noemaforge || true)"
[[ -x "$NOEMAFORGE_BIN" ]] || { echo "missing noemaforge CLI" >&2; exit 1; }

PASS=0; FAIL=0; RESULTS=()
record(){
  local id="$1" status="$2" msg="$3" command="${4:-}" exit_code="${5:-}" stdout_path="${6:-}" stderr_path="${7:-}" report_path="${8:-}"
  RESULTS+=("$id|$status|$msg|$command|$exit_code|$stdout_path|$stderr_path|$report_path")
  [[ "$status" == pass ]] && PASS=$((PASS+1)) || FAIL=$((FAIL+1))
}

export NOEMAFORGE_ROOT="$ROOT" NOEMAFORGE_PIPELINE_STATE="$STATE" NOEMAFORGE_SELFTEST_STATE="$STATE/selftests"
# Smoke writes only to a temporary state dir; allow degraded_readonly override for this validation path.
export NOEMAFORGE_ALLOW_DEGRADED_MUTATION=1
export NOEMAFORGE_BOOT_MODE_FILE="$STATE/boot-mode"
printf 'manual\n' > "$STATE/boot-mode"

"$NOEMAFORGE_BIN" status --json >/tmp/noemaforge-mvp-status.json 2>/tmp/noemaforge-mvp-status.err || true
if [[ -s /tmp/noemaforge-mvp-status.json ]] && grep -q '"health"' /tmp/noemaforge-mvp-status.json; then
  record status_json pass "noemaforge status --json emits MVP status shape"
else
  record status_json fail "noemaforge status --json failed or emitted unexpected shape"
fi

if "$ROOT/tools/prep/noemaforge-autostart-safe.sh" --mode gui --dry-run --json >/tmp/noemaforge-mvp-autostart-gui.json 2>/tmp/noemaforge-mvp-autostart-gui.err || true; then
  if grep -q '"mode":"gui"\|"mode": "gui"' /tmp/noemaforge-mvp-autostart-gui.json /tmp/noemaforge-mvp-autostart-gui.err 2>/dev/null \
     && grep -q '"profile":"runtime_only"\|"profile": "runtime_only"' /tmp/noemaforge-mvp-autostart-gui.json /tmp/noemaforge-mvp-autostart-gui.err 2>/dev/null; then
    record autostart_gui_plan pass "GUI autostart gate is callable and defaults to runtime_only"
  else
    record autostart_gui_plan fail "GUI autostart dry-run did not expose mode=gui profile=runtime_only"
  fi
else
  record autostart_gui_plan fail "GUI autostart gate failed unexpectedly"
fi

if "$ROOT/tools/prep/noemaforge-autostart-safe.sh" --mode wogui --dry-run --json >/tmp/noemaforge-mvp-autostart-wogui.json 2>/tmp/noemaforge-mvp-autostart-wogui.err || true; then
  if grep -q '"mode":"wogui"\|"mode": "wogui"' /tmp/noemaforge-mvp-autostart-wogui.json /tmp/noemaforge-mvp-autostart-wogui.err 2>/dev/null \
     && grep -q '"profile":"bootstrap_cpu_llm"\|"profile": "bootstrap_cpu_llm"' /tmp/noemaforge-mvp-autostart-wogui.json /tmp/noemaforge-mvp-autostart-wogui.err 2>/dev/null; then
    record autostart_wogui_plan pass "woGUI autostart defaults to bootstrap_cpu_llm"
  else
    record autostart_wogui_plan fail "woGUI autostart dry-run did not expose mode=wogui profile=bootstrap_cpu_llm"
  fi
else
  record autostart_wogui_plan fail "woGUI autostart gate failed unexpectedly"
fi

if "$ROOT/tools/prep/noemaforge-boot-mode.sh" show --json >/tmp/noemaforge-mvp-boot-mode.json 2>/tmp/noemaforge-mvp-boot-mode.err && grep -q '"mode"' /tmp/noemaforge-mvp-boot-mode.json; then
  record boot_mode_show pass "boot-mode command reports conditional autostart policy"
else
  record boot_mode_show fail "boot-mode command failed"
fi

trixie_dir="$CHECKS_DIR/trixie_json"; mkdir -p "$trixie_dir"
trixie_cmd="$NOEMAFORGE_BIN trixie-preflight --root $ROOT --json --skip-modelstore"
trixie_rc=0
"$NOEMAFORGE_BIN" trixie-preflight --root "$ROOT" --json --skip-modelstore >"$trixie_dir/stdout.txt" 2>"$trixie_dir/stderr.txt" || trixie_rc=$?
cp "$trixie_dir/stdout.txt" "$trixie_dir/report.json" 2>/dev/null || true
if [[ -s "$trixie_dir/stdout.txt" ]] && grep -q '"checks"' "$trixie_dir/stdout.txt"; then
  record trixie_json pass "trixie-preflight emits MVP preflight shape even when host checks fail" "$trixie_cmd" "$trixie_rc" "$trixie_dir/stdout.txt" "$trixie_dir/stderr.txt" "$trixie_dir/report.json"
else
  record trixie_json fail "trixie-preflight JSON shape missing" "$trixie_cmd" "$trixie_rc" "$trixie_dir/stdout.txt" "$trixie_dir/stderr.txt" "$trixie_dir/report.json"
fi

pipeline_validate_dir="$CHECKS_DIR/pipeline_validate"; mkdir -p "$pipeline_validate_dir"
pipeline_validate_cmd="$NOEMAFORGE_BIN pipeline validate --json"
pipeline_validate_rc=0
"$NOEMAFORGE_BIN" pipeline validate --json >"$pipeline_validate_dir/stdout.txt" 2>"$pipeline_validate_dir/stderr.txt" || pipeline_validate_rc=$?
cp "$pipeline_validate_dir/stdout.txt" "$pipeline_validate_dir/report.json" 2>/dev/null || true
if [[ "$pipeline_validate_rc" -eq 0 ]]; then
  record pipeline_validate pass "pipeline validate passed" "$pipeline_validate_cmd" "$pipeline_validate_rc" "$pipeline_validate_dir/stdout.txt" "$pipeline_validate_dir/stderr.txt" "$pipeline_validate_dir/report.json"
else
  record pipeline_validate fail "pipeline validate failed" "$pipeline_validate_cmd" "$pipeline_validate_rc" "$pipeline_validate_dir/stdout.txt" "$pipeline_validate_dir/stderr.txt" "$pipeline_validate_dir/report.json"
fi

if "$NOEMAFORGE_BIN" pipeline patterns --json --limit 3 >/tmp/noemaforge-mvp-patterns.json 2>/tmp/noemaforge-mvp-patterns.err && grep -q '"patterns"' /tmp/noemaforge-mvp-patterns.json; then
  record pipeline_patterns pass "pipeline pattern catalog is queryable"
else
  record pipeline_patterns fail "pipeline pattern catalog query failed"
fi

if "$NOEMAFORGE_BIN" pipeline readiness --json >/tmp/noemaforge-mvp-readiness.json 2>/tmp/noemaforge-mvp-readiness.err && grep -q '"readiness_score"' /tmp/noemaforge-mvp-readiness.json; then
  record pipeline_readiness pass "pipeline readiness emits release-readiness score"
else
  record pipeline_readiness fail "pipeline readiness failed"
fi

cat > "$STATE/import-template.json" <<'JSONTEMPLATE'
{"name":"MVP Template","nodes":[{"name":"Webhook"},{"name":"Review"}],"connections":{}}
JSONTEMPLATE
if "$NOEMAFORGE_BIN" pipeline template-import "$STATE/import-template.json" --family n8n --pipeline-id mvp_import >/tmp/noemaforge-mvp-template-import.json 2>/tmp/noemaforge-mvp-template-import.err && grep -q '"pipeline"' /tmp/noemaforge-mvp-template-import.json; then
  record pipeline_template_import pass "template import maps external workflow to NoemaForge pipeline draft"
else
  record pipeline_template_import fail "template import failed"
fi

export NOEMAFORGE_PERSONA_STATE="$STATE/personas"
if "$NOEMAFORGE_BIN" persona validate >/tmp/noemaforge-mvp-persona-validate.json 2>/tmp/noemaforge-mvp-persona-validate.err; then
  record persona_validate pass "persona catalog validates"
else
  record persona_validate fail "persona catalog validation failed"
fi

if "$NOEMAFORGE_BIN" persona activate Бехтерев --reason mvp_smoke >/tmp/noemaforge-mvp-persona-activate.json 2>/tmp/noemaforge-mvp-persona-activate.err && grep -q '"context_packet"' /tmp/noemaforge-mvp-persona-activate.json; then
  record persona_activate pass "persona activation writes context packet"
else
  record persona_activate fail "persona activation failed"
fi

if "$NOEMAFORGE_BIN" persona evolve Гармр --reason mvp_smoke >/tmp/noemaforge-mvp-persona-evolve.json 2>/tmp/noemaforge-mvp-persona-evolve.err && grep -q '"portrait"' /tmp/noemaforge-mvp-persona-evolve.json; then
  record persona_evolve pass "persona evolution writes next portrait"
else
  record persona_evolve fail "persona evolution failed"
fi

RUN_JSON="$STATE/run.json"
RUN_ID=""
if "$NOEMAFORGE_BIN" pipeline run public_mwp --task-id mvp_smoke --request "MVP smoke" > "$RUN_JSON"; then
  RUN_ID="$(sed -n 's/.*"run_id": *"\([^"]*\)".*/\1/p' "$RUN_JSON" | head -1)"
fi
if [[ -n "$RUN_ID" ]]; then
  record pipeline_run pass "created $RUN_ID"
else
  record pipeline_run fail "could not create public_mwp run"
fi

if [[ -n "$RUN_ID" ]] && find "$STATE/runs/$RUN_ID/context_packets" -name '*.json' -print -quit | grep -q .; then
  record typed_context_sidecar pass "pipeline context packets include JSON sidecars"
else
  record typed_context_sidecar fail "typed context sidecar missing"
fi

pipeline_lifecycle_dir="$CHECKS_DIR/pipeline_lifecycle"; mkdir -p "$pipeline_lifecycle_dir"
pipeline_lifecycle_cmd="$NOEMAFORGE_BIN pipeline approve $RUN_ID --allow-degraded && $NOEMAFORGE_BIN pipeline advance $RUN_ID --stage status_check --status in_progress --note smoke --allow-degraded && $NOEMAFORGE_BIN pipeline doctor $RUN_ID"
pipeline_lifecycle_rc=0
if [[ -n "$RUN_ID" ]]; then
  {
    "$NOEMAFORGE_BIN" pipeline approve "$RUN_ID" --allow-degraded &&
    "$NOEMAFORGE_BIN" pipeline advance "$RUN_ID" --stage status_check --status in_progress --note smoke --allow-degraded &&
    "$NOEMAFORGE_BIN" pipeline doctor "$RUN_ID"
  } >"$pipeline_lifecycle_dir/stdout.txt" 2>"$pipeline_lifecycle_dir/stderr.txt" || pipeline_lifecycle_rc=$?
else
  pipeline_lifecycle_rc=1
  printf 'pipeline run id is missing\n' >"$pipeline_lifecycle_dir/stderr.txt"
  : >"$pipeline_lifecycle_dir/stdout.txt"
fi
cp "$pipeline_lifecycle_dir/stdout.txt" "$pipeline_lifecycle_dir/report.json" 2>/dev/null || true
if [[ "$pipeline_lifecycle_rc" -eq 0 ]]; then
  record pipeline_lifecycle pass "approve/advance/doctor passed" "$pipeline_lifecycle_cmd" "$pipeline_lifecycle_rc" "$pipeline_lifecycle_dir/stdout.txt" "$pipeline_lifecycle_dir/stderr.txt" "$pipeline_lifecycle_dir/report.json"
else
  record pipeline_lifecycle fail "pipeline lifecycle failed" "$pipeline_lifecycle_cmd" "$pipeline_lifecycle_rc" "$pipeline_lifecycle_dir/stdout.txt" "$pipeline_lifecycle_dir/stderr.txt" "$pipeline_lifecycle_dir/report.json"
fi

if [[ -n "$RUN_ID" ]] && "$NOEMAFORGE_BIN" pipeline gate "$RUN_ID" --json >/tmp/noemaforge-mvp-pipeline-gate.json && grep -q '"ready_to_advance"' /tmp/noemaforge-mvp-pipeline-gate.json; then
  record pipeline_gate pass "pipeline gate reports stage readiness"
else
  record pipeline_gate fail "pipeline gate failed"
fi

if [[ -n "$RUN_ID" ]] && "$NOEMAFORGE_BIN" pipeline repair "$RUN_ID" --dry-run >/tmp/noemaforge-mvp-pipeline-repair.json && grep -q '"run_count"' /tmp/noemaforge-mvp-pipeline-repair.json; then
  record pipeline_repair pass "pipeline repair dry-run is available"
else
  record pipeline_repair fail "pipeline repair dry-run failed"
fi

if [[ -n "$RUN_ID" ]] && "$NOEMAFORGE_BIN" pipeline dashboard-state --out "$STATE/dashboard-state.json" >/dev/null && [[ -s "$STATE/dashboard-state.json" ]]; then
  record dashboard_state pass "dashboard-state generated"
else
  record dashboard_state fail "dashboard-state missing"
fi

if [[ -n "$RUN_ID" ]] && "$NOEMAFORGE_BIN" pipeline context-lint "$RUN_ID" >/tmp/noemaforge-mvp-context-lint.json && grep -q '"stage_count"' /tmp/noemaforge-mvp-context-lint.json; then
  record pipeline_context_lint pass "pipeline context packets linted"
else
  record pipeline_context_lint fail "pipeline context lint failed"
fi

if [[ -n "$RUN_ID" ]] && "$NOEMAFORGE_BIN" pipeline compact "$RUN_ID" --register >/tmp/noemaforge-mvp-compact.json && grep -q '"registered"' /tmp/noemaforge-mvp-compact.json; then
  record pipeline_compact pass "compact context generated and registered"
else
  record pipeline_compact fail "pipeline compact failed"
fi

if "$NOEMAFORGE_BIN" pipeline queue --json >/tmp/noemaforge-mvp-queue.json && grep -q '"items"' /tmp/noemaforge-mvp-queue.json; then
  record pipeline_queue pass "pipeline queue surface works"
else
  record pipeline_queue fail "pipeline queue failed"
fi

if "$NOEMAFORGE_BIN" pipeline metrics >/tmp/noemaforge-mvp-metrics.json && grep -q '"readiness_score"' /tmp/noemaforge-mvp-metrics.json; then
  record pipeline_metrics pass "pipeline metrics emitted"
else
  record pipeline_metrics fail "pipeline metrics failed"
fi

if "$NOEMAFORGE_BIN" pipeline metrics --format prometheus >/tmp/noemaforge-mvp-metrics.prom && grep -q 'noemaforge_pipeline_runs_total' /tmp/noemaforge-mvp-metrics.prom; then
  record pipeline_metrics_prometheus pass "pipeline metrics Prometheus exporter emitted"
else
  record pipeline_metrics_prometheus fail "pipeline metrics Prometheus exporter failed"
fi

if "$NOEMAFORGE_BIN" pipeline schema-validate >/tmp/noemaforge-mvp-schema-validate.json && grep -q '"ok"' /tmp/noemaforge-mvp-schema-validate.json; then
  record pipeline_schema_validate pass "P1 pipeline schema validation works"
else
  record pipeline_schema_validate fail "P1 pipeline schema validation failed"
fi

if [[ -n "$RUN_ID" ]] && "$NOEMAFORGE_BIN" pipeline schema-validate --run-id "$RUN_ID" >/tmp/noemaforge-mvp-schema-run.json && grep -q '"typed_context_sidecars"' /tmp/noemaforge-mvp-schema-run.json; then
  record pipeline_schema_run_validate pass "typed context sidecars validate for run"
else
  record pipeline_schema_run_validate fail "typed context sidecar validation failed"
fi

LEASE_ID=""
if "$NOEMAFORGE_BIN" pipeline lease acquire --owner mvp_smoke --task-id "$RUN_ID" --priority 50 --ttl-seconds 60 >/tmp/noemaforge-mvp-lease-acquire.json; then
  LEASE_ID="$(python3 -c 'import json; print(json.load(open("/tmp/noemaforge-mvp-lease-acquire.json")).get("lease_id", ""))' 2>/dev/null || true)"
fi
if [[ -n "$LEASE_ID" ]] && "$NOEMAFORGE_BIN" pipeline lease status >/tmp/noemaforge-mvp-lease-status.json && grep -q "$LEASE_ID" /tmp/noemaforge-mvp-lease-status.json; then
  record pipeline_lease pass "single-LLM lease lifecycle is callable"
  "$NOEMAFORGE_BIN" pipeline lease release "$LEASE_ID" >/tmp/noemaforge-mvp-lease-release.json || true
else
  record pipeline_lease fail "single-LLM lease lifecycle failed"
fi

if [[ -n "$RUN_ID" ]] && "$NOEMAFORGE_BIN" pipeline executor-step "$RUN_ID" >/tmp/noemaforge-mvp-executor-step.json && grep -q '"action"' /tmp/noemaforge-mvp-executor-step.json; then
  record pipeline_executor_step pass "lightweight executor-step reports DAG action"
else
  record pipeline_executor_step fail "pipeline executor-step failed"
fi

if [[ -n "$RUN_ID" ]] && "$NOEMAFORGE_BIN" pipeline event-log --run-id "$RUN_ID" --json >/tmp/noemaforge-mvp-event-log.json && grep -q '"items"' /tmp/noemaforge-mvp-event-log.json; then
  record pipeline_event_log pass "pipeline event-log is queryable"
else
  record pipeline_event_log fail "pipeline event-log failed"
fi

if "$NOEMAFORGE_BIN" toolproxy smoke --tokens-dir "$STATE/cap_tokens" >/tmp/noemaforge-mvp-toolproxy-smoke.json && grep -q '"ok"' /tmp/noemaforge-mvp-toolproxy-smoke.json; then
  record toolproxy_token_smoke pass "ToolProxy capability token issue/verify smoke works offline"
else
  record toolproxy_token_smoke fail "ToolProxy offline capability token smoke failed"
fi

if "$NOEMAFORGE_BIN" persona doctor >/tmp/noemaforge-mvp-persona-doctor.json && grep -q '"next_safe_action"' /tmp/noemaforge-mvp-persona-doctor.json; then
  record persona_doctor pass "persona doctor checks state"
else
  record persona_doctor fail "persona doctor failed"
fi

selftest_core_dir="$CHECKS_DIR/selftest_core"; mkdir -p "$selftest_core_dir"
selftest_core_cmd="$NOEMAFORGE_BIN testbench run --suite quick --out $STATE/selftest-core --json"
selftest_core_rc=0
"$NOEMAFORGE_BIN" testbench run --suite quick --out "$STATE/selftest-core" --json >"$selftest_core_dir/stdout.txt" 2>"$selftest_core_dir/stderr.txt" || selftest_core_rc=$?
cp "$selftest_core_dir/stdout.txt" "$selftest_core_dir/report.json" 2>/dev/null || true
if [[ "$selftest_core_rc" -eq 0 ]] && grep -q '"failed": 0' "$selftest_core_dir/stdout.txt"; then
  record selftest_core pass "testbench quick suite records resource telemetry" "$selftest_core_cmd" "$selftest_core_rc" "$selftest_core_dir/stdout.txt" "$selftest_core_dir/stderr.txt" "$selftest_core_dir/report.json"
else
  record selftest_core fail "testbench quick suite failed" "$selftest_core_cmd" "$selftest_core_rc" "$selftest_core_dir/stdout.txt" "$selftest_core_dir/stderr.txt" "$selftest_core_dir/report.json"
fi


# 0.32.1: code-dev member-cell and legacy QA surfaces.
if "$NOEMAFORGE_BIN" qa code team --producer qwen25-coder-14b --json >/tmp/noemaforge-mvp-codeqa-team.json 2>/tmp/noemaforge-mvp-codeqa-team.err && grep -q '"reviewers"' /tmp/noemaforge-mvp-codeqa-team.json; then
  record code_qa_team pass "code QA reviewer selection excludes producer and returns sub-team"
else
  record code_qa_team fail "code QA reviewer selection failed"
fi
mkdir -p "$STATE/codeqa_project"
cat > "$STATE/codeqa_project/app.py" <<'PYAPP'
def add(a, b):
    return a + b
PYAPP
if "$NOEMAFORGE_BIN" qa code run --project "$STATE/codeqa_project" --producer qwen25-coder-14b --state "$STATE/codeqa_state" --run-id mvp_codeqa --json >/tmp/noemaforge-mvp-codeqa-run.json 2>/tmp/noemaforge-mvp-codeqa-run.err && [[ -s "$STATE/codeqa_state/runs/mvp_codeqa/next_participant_handoff_context.md" ]]; then
  record code_qa_run pass "code QA run emits consensus and next participant handoff"
else
  record code_qa_run fail "code QA run/handoff failed"
fi

if "$NOEMAFORGE_BIN" member validate --root "$ROOT" >/tmp/noemaforge-mvp-member-validate.json 2>/tmp/noemaforge-mvp-member-validate.err && grep -q '"ok": true' /tmp/noemaforge-mvp-member-validate.json; then
  record member_runtime_validate pass "member-cell policy validates"
else
  record member_runtime_validate fail "member-cell policy failed validation"
fi

if "$NOEMAFORGE_BIN" member team --member qa --producer qwen25-coder-14b --json >/tmp/noemaforge-mvp-member-team.json 2>/tmp/noemaforge-mvp-member-team.err && grep -q '"models"' /tmp/noemaforge-mvp-member-team.json; then
  record member_team_select pass "member-cell model selection returns producer-distinct cell"
else
  record member_team_select fail "member-cell team selection failed"
fi

if "$NOEMAFORGE_BIN" member run --member code_analyser_visualiser --project "$STATE/codeqa_project" --state "$STATE/member_state" --run-id mvp_member_analyser --json >/tmp/noemaforge-mvp-member-run.json 2>/tmp/noemaforge-mvp-member-run.err && [[ -s "$STATE/member_state/runs/mvp_member_analyser/architecture_overview.mmd" ]] && [[ -s "$STATE/member_state/runs/mvp_member_analyser/bottleneck_report.json" ]]; then
  record member_analyser_run pass "code analyzer/visualizer emits diagrams, bottlenecks and typed handoff"
else
  record member_analyser_run fail "code analyzer/visualizer member run failed"
fi

mkdir -p "$STATE/wiki_repo"
wiki_patch_dir="$CHECKS_DIR/wiki_patch_create"; mkdir -p "$wiki_patch_dir"
wiki_patch_cmd="$NOEMAFORGE_BIN wiki-patch create --wiki-repo $STATE/wiki_repo --source-root $ROOT --state $STATE/wiki-patches --title MVP smoke telemetry patch --description MVP smoke generated wiki patch from testbench summary --metrics-after $STATE/selftest-core/selftest-report.json --include docs/wiki/metrics/testbench-and-regression-metrics.md --json"
wiki_patch_rc=0
if [[ -s "$STATE/selftest-core/selftest-report.json" ]]; then
  "$NOEMAFORGE_BIN" wiki-patch create \
    --wiki-repo "$STATE/wiki_repo" \
    --source-root "$ROOT" \
    --state "$STATE/wiki-patches" \
    --title "MVP smoke telemetry patch" \
    --description "MVP smoke generated wiki patch from testbench summary" \
    --metrics-after "$STATE/selftest-core/selftest-report.json" \
    --include "docs/wiki/metrics/testbench-and-regression-metrics.md" \
    --json >"$wiki_patch_dir/stdout.txt" 2>"$wiki_patch_dir/stderr.txt" || wiki_patch_rc=$?
else
  wiki_patch_rc=1
  printf 'missing selftest report: %s\n' "$STATE/selftest-core/selftest-report.json" >"$wiki_patch_dir/stderr.txt"
  : >"$wiki_patch_dir/stdout.txt"
fi
cp "$wiki_patch_dir/stdout.txt" "$wiki_patch_dir/report.json" 2>/dev/null || true
if [[ "$wiki_patch_rc" -eq 0 ]] && grep -q '"patch_dir"' "$wiki_patch_dir/stdout.txt"; then
  record wiki_patch_create pass "wiki incremental patch can be generated from selftest report" "$wiki_patch_cmd" "$wiki_patch_rc" "$wiki_patch_dir/stdout.txt" "$wiki_patch_dir/stderr.txt" "$wiki_patch_dir/report.json"
else
  record wiki_patch_create fail "wiki incremental patch generation failed" "$wiki_patch_cmd" "$wiki_patch_rc" "$wiki_patch_dir/stdout.txt" "$wiki_patch_dir/stderr.txt" "$wiki_patch_dir/report.json"
fi

if "$NOEMAFORGE_BIN" dashboard state --out "$STATE/dashboard-state-via-launcher.json" >/tmp/noemaforge-mvp-dashboard-launcher.txt && [[ -s "$STATE/dashboard-state-via-launcher.json" ]]; then
  record dashboard_launcher pass "dashboard launcher writes state"
else
  record dashboard_launcher fail "dashboard launcher failed"
fi

if [[ -n "$RUN_ID" ]] && "$NOEMAFORGE_BIN" pipeline export "$RUN_ID" --out "$STATE/$RUN_ID.tar.gz" >/dev/null && [[ -s "$STATE/$RUN_ID.tar.gz" ]]; then
  record pipeline_export pass "pipeline export generated"
else
  record pipeline_export fail "pipeline export failed"
fi

if [[ "$JSON" == "1" ]]; then
  python3 - "$FAIL" "$PASS" "$STATE" "${RESULTS[@]}" <<'PYJSON'
import json, sys
fail = int(sys.argv[1]); passed = int(sys.argv[2]); state = sys.argv[3]
checks = []
for raw in sys.argv[4:]:
    parts = (raw.split('|', 7) + [''] * 8)[:8]
    cid, status, msg, command, exit_code, stdout_path, stderr_path, report_path = parts
    check = {'id': cid, 'status': status, 'ok': status == 'pass', 'message': msg}
    if command:
        check.update({
            'command': command,
            'exit_code': int(exit_code) if exit_code else None,
            'stdout_path': stdout_path or None,
            'stderr_path': stderr_path or None,
            'report_path': report_path or None,
            'next': f"cat {stderr_path}" if stderr_path else None,
        })
    checks.append(check)
print(json.dumps({'ok': fail == 0, 'passed': passed, 'failed': fail, 'state': state, 'checks': checks}, ensure_ascii=False, indent=2))
PYJSON
else
  for raw in "${RESULTS[@]}"; do IFS='|' read -r id status msg <<<"$raw"; printf '[%s] %s: %s\n' "$status" "$id" "$msg"; done
  printf 'summary: pass=%s fail=%s state=%s\n' "$PASS" "$FAIL" "$STATE"
fi
[[ "$FAIL" -eq 0 ]]
