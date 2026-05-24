#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-first-run-audit.sh
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
# NoemaForge first-run auditor: one-command first-run checks with internal RUN handling.
set -euo pipefail

ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
MODE="failed"          # summary|failed|full
FORMAT="human"        # human|json
STORAGE_SCAN=1
MVP_SMOKE=1
REBOOT_READY=0
OUT=""
VERSION="0.32.1"

usage(){ cat <<'USAGE'
Usage: noemaforge first-run [options]
       noemaforge first-run audit [options]

Options:
  --summary                 Print one-line overall result when OK.
  --failed                  Print only failed checks and key context. Default.
  --full                    Print all check output.
  --json                    Emit JSON report.
  --out DIR                 Store logs in DIR. If omitted, creates ~/noemaforge-first-run-<version>/run-<timestamp>.
  --no-storage-scan         Skip Vault/GGUF inventory scan.
  --skip-mvp-smoke          Skip mvp-smoke if you want a faster pass.
  --reboot-ready            Also verify GUI timer/no-LLM/NVIDIA readiness before reboot.
  --root ROOT               NoemaForge root. Default /opt/noemaforge.

The command initializes its own RUN directory. It never writes to / because RUN is empty.
It does not start heavy LLM backends.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    audit|run|check) shift ;;
    --summary) MODE="summary"; shift ;;
    --failed|--failures) MODE="failed"; shift ;;
    --full|--verbose) MODE="full"; shift ;;
    --json) FORMAT="json"; shift ;;
    --out) OUT="$2"; shift 2 ;;
    --no-storage-scan) STORAGE_SCAN=0; shift ;;
    --skip-mvp-smoke) MVP_SMOKE=0; shift ;;
    --reboot-ready) REBOOT_READY=1; shift ;;
    --root) ROOT="$2"; shift 2 ;;
    -h|--help|help|\?) usage; exit 0 ;;
    *) echo "[first-run][ERROR] unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# Recompute version and PATH after --root has been parsed.
[[ -r "$ROOT/VERSION" ]] && VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
export PATH="$ROOT/bin:$PATH"
NOEMAFORGE_BIN="$ROOT/bin/noemaforge"
export NOEMAFORGE_BIN

if [[ -z "$OUT" ]]; then
  OUT="$HOME/noemaforge-first-run-${VERSION}/run-$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "$OUT/checks"
mkdir -p "$HOME/noemaforge-first-run-${VERSION}" 2>/dev/null || true
printf 'export RUN=%q\n' "$OUT" > "$HOME/noemaforge-first-run-${VERSION}/current-run.env" 2>/dev/null || true

CHECKS_FILE="$OUT/checks.tsv"
: > "$CHECKS_FILE"

json_escape(){ python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'; }

run_check(){
  local id="$1" desc="$2" cmd="$3"
  local out_file="$OUT/checks/${id}.log" start end rc status
  start=$(date +%s)
  set +e
  bash -c "$cmd" >"$out_file" 2>&1
  rc=$?
  set -e
  end=$(date +%s)
  if [[ $rc -eq 0 ]]; then status="pass"; else status="fail"; fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$id" "$status" "$rc" "$((end-start))" "$desc" "$out_file" >> "$CHECKS_FILE"
  if [[ "$MODE" == "full" ]]; then
    printf '\n===== %s [%s] %s =====\n' "$id" "$status" "$desc"
    sed -n '1,220p' "$out_file"
  elif [[ "$MODE" == "failed" && "$status" == "fail" ]]; then
    printf '\n===== FAILED: %s =====\n%s\n' "$id" "$desc"
    sed -n '1,220p' "$out_file"
  fi
}

# Context header
{
  echo "NoemaForge first-run audit"
  echo "version=${VERSION}"
  echo "root=${ROOT}"
  echo "run=${OUT}"
  echo "date=$(date --iso-8601=seconds 2>/dev/null || date)"
} > "$OUT/00-run-context.txt"

# Core no-recursion/CLI checks.
run_check version "Canonical CLI returns release version under timeout" "timeout 5 \"$NOEMAFORGE_BIN\" version | grep -Fx '${VERSION}'"
run_check paths "Public noemaforge paths resolve to /opt/noemaforge/bin/noemaforge" "for p in /usr/local/bin/noemaforge /usr/local/sbin/noemaforge /usr/bin/noemaforge /bin/noemaforge; do [ -e \$p ] || continue; r=\$(readlink -f \$p); echo \$p '->' \$r; [ \$r = /opt/noemaforge/bin/noemaforge ]; done"
run_check version_audit "Active code/config versions are consistent" "${ROOT}/tools/prep/noemaforge-version-audit.sh --root '${ROOT}' --expected '${VERSION}'"
run_check recursion_audit "No setup/installer/wrapper/systemd recursion hazards" "${ROOT}/tools/prep/noemaforge-recursion-audit.sh --json '${ROOT}'"
run_check consistency_audit "Release consistency/policies/wiki/TODO audit" "${ROOT}/tools/prep/noemaforge-consistency-audit.sh --json --root '${ROOT}'"
run_check gui_help "gui_start help is native and non-hanging" "timeout 5 \"$NOEMAFORGE_BIN\" gui_start --help >/tmp/noemaforge-first-run-gui-help.txt && grep -q 'Start Debian GUI' /tmp/noemaforge-first-run-gui-help.txt"
run_check gui_dry_run "sudo gui_start dry-run is bounded and does not start LLM" "sudo timeout 5 \"$NOEMAFORGE_BIN\" gui_start --dry-run"

# Storage and model inventory.
if [[ "$STORAGE_SCAN" == 1 ]]; then
  run_check share_mount "Share mount exists at /mnt/noemaforge-share" "findmnt /mnt/noemaforge-share"
  run_check vault_exists "Canonical Vault exists" "test -d /mnt/noemaforge-share/noemaforge-lab/data/Vault && du -sh /mnt/noemaforge-share/noemaforge-lab/data/Vault"
  run_check vault_scan "Vault/GGUF file summary" "VAULT=/mnt/noemaforge-share/noemaforge-lab/data/Vault; echo all_files=\$(find \$VAULT -type f 2>/dev/null | wc -l); echo gguf_files=\$(find \$VAULT -type f -name '*.gguf' 2>/dev/null | wc -l); find \$VAULT/models-gguf -type f -name '*.gguf' -printf '%s %p\\n' 2>/dev/null | sort -nr | head -30"
  run_check modelstore "ModelStore main model safety" "ls -l /var/lib/modelstore/models/main/model.gguf 2>/dev/null && readlink -f /var/lib/modelstore/models/main/model.gguf 2>/dev/null"
  run_check multimodal_scan "Vault multimodal/non-GGUF model scan" "\"$NOEMAFORGE_BIN\" multimodal scan --json"
  run_check multimodal_status "Multimodal backend prerequisites and model capabilities" "\"$NOEMAFORGE_BIN\" multimodal status --json"
fi

# System readiness and catalogs.
run_check trixie_preflight "Debian Trixie/ModelStore/share preflight (warn-only when storage scan is skipped)" "\"$NOEMAFORGE_BIN\" trixie-preflight --json || [[ $STORAGE_SCAN == 0 ]]"
run_check pipeline_validate "Pipeline catalog validates" "\"$NOEMAFORGE_BIN\" pipeline validate"
run_check schema_validate "Schema catalog validates and reports release version" "\"$NOEMAFORGE_BIN\" schema validate | tee /tmp/noemaforge-first-run-schema.json && grep -q \"\\\"version\\\": \\\"${VERSION}\\\"\" /tmp/noemaforge-first-run-schema.json"
run_check member_validate "Member catalog validates and reports release version" "\"$NOEMAFORGE_BIN\" member validate | tee /tmp/noemaforge-first-run-member.json && grep -q \"\\\"version\\\": \\\"${VERSION}\\\"\" /tmp/noemaforge-first-run-member.json"
run_check testbench_quick "Quick testbench resource telemetry" "\"$NOEMAFORGE_BIN\" testbench run --suite quick --json"
if [[ "$MVP_SMOKE" == 1 ]]; then
  run_check mvp_smoke "MVP/MWP smoke" "noemaforge mvp-smoke --json"
fi
run_check av_readiness "Audio/video readiness is reported honestly" "\"$NOEMAFORGE_BIN\" av-readiness --json"
run_check persona_gui "Persona portraits and dashboard GUI readiness" "\"$NOEMAFORGE_BIN\" persona gui-status --json"
run_check admin_greeting "Admin accepts GUI greeting typo inside local console" "\"$NOEMAFORGE_BIN\" admin message --message 'Првиет!' --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d[\"route\"][\"id\"]==\"greeting\"'"
run_check admin_code_route "Admin code/dev-team route requests clarification or launches Dev Team" "\"$NOEMAFORGE_BIN\" admin --state '${OUT}/runtime/pipelines' message --message 'запусти dev team поправить код' --execute --allow-degraded --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get(\"clarification_required\") is True or any(a.get(\"type\")==\"dev_team\" for a in d.get(\"actions\",[]))'"
run_check admin_model_evolution_route "Admin can conduct model-evolution runtime" "\"$NOEMAFORGE_BIN\" admin --state '${OUT}/runtime/pipelines' --evolution-state '${OUT}/runtime/model-evolution' message --message 'проведи эволюцию модели' --execute --allow-degraded --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert any(a.get(\"type\")==\"model_evolution\" for a in d.get(\"actions\",[]))'"
run_check admin_gui_api_syntax "Admin GUI/API server syntax is valid" "python3 - <<'PYADMINAPI'
from pathlib import Path
p=Path('$ROOT/src/admin_gui_server.py')
compile(p.read_text(encoding='utf-8', errors='replace'), str(p), 'exec')
PYADMINAPI"

if [[ "$REBOOT_READY" == 1 ]]; then
  run_check gui_timer "GUI timer enabled and direct graphical target link absent" "systemctl is-enabled noemaforge-autostart-gui.timer && ! find /etc/systemd/system/graphical.target.wants -lname '*noemaforge-autostart-gui.service' | grep -q ."
  run_check no_llm "GUI runtime_only has no active llama-server" "! pgrep -a -f '[l]lama-server'"
  run_check failed_units "No failed systemd units" "test \$(systemctl --failed --no-legend --no-pager | wc -l) -eq 0"
  run_check nvidia "NVIDIA status available" "nvidia-smi"
fi

# Summarize.
python3 - "$CHECKS_FILE" "$OUT" "$FORMAT" "$MODE" <<'PY'
import json, sys, pathlib
checks=[]
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    id,status,rc,dur,desc,out=line.split('\t',5)
    checks.append({"id":id,"status":status,"ok":status=="pass","rc":int(rc),"duration_sec":int(dur),"description":desc,"log":out})
failed=[c for c in checks if not c['ok']]
warnings=[]
for c in checks:
    if c['id'] == 'av_readiness':
        try:
            txt=pathlib.Path(c['log']).read_text(errors='replace')
            if '"ready_for_audio_video_production": false' in txt or 'NOT PRODUCTION READY' in txt:
                warnings.append({"id":"av_not_production_ready","message":"Audio/video pipeline is not production-ready; see av_readiness log.","log":c['log']})
        except Exception:
            pass
report={"ok":not failed,"passed":len(checks)-len(failed),"failed":len(failed),"warnings":warnings,"run_dir":sys.argv[2],"checks":checks}
pathlib.Path(sys.argv[2], 'summary.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n")
fmt=sys.argv[3]; mode=sys.argv[4]
if fmt=='json':
    print(json.dumps(report, indent=2, ensure_ascii=False))
else:
    if not failed and not warnings:
        print(f"overall: OK ({len(checks)} checks passed). run={sys.argv[2]}")
    elif not failed:
        print(f"overall: OK_WITH_WARNINGS ({len(checks)} checks passed, {len(warnings)} warnings). run={sys.argv[2]}")
        for w in warnings:
            print(f"- warning {w['id']}: {w['message']} [log: {w['log']}]")
    else:
        print(f"overall: FAIL ({len(failed)} failed / {len(checks)} total, {len(warnings)} warnings). run={sys.argv[2]}")
        for c in failed:
            print(f"- {c['id']}: {c['description']} [log: {c['log']}]")
        for w in warnings:
            print(f"- warning {w['id']}: {w['message']} [log: {w['log']}]")
sys.exit(0 if not failed else 1)
PY

