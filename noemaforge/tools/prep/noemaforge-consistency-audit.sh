#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-consistency-audit.sh
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
# NoemaForge release consistency/policy/wiki/TODO audit.
set -euo pipefail
ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
FORMAT="human"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --json) FORMAT="json"; shift ;;
    -h|--help|help|\?) cat <<'USAGE'
Usage: noemaforge consistency-audit [--json] [--root ROOT]

Checks active version metadata, recursion guards, required policies, wiki/TODO
coverage, multimodal and persona GUI readiness surfaces. Does not start models.
USAGE
      exit 0 ;;
    *) echo "[consistency-audit][ERROR] unknown argument: $1" >&2; exit 2 ;;
  esac
done
python3 - "$ROOT" "$FORMAT" <<'PYCONSISTENCY'
import json, subprocess, sys
from pathlib import Path
root=Path(sys.argv[1]); fmt=sys.argv[2]
try:
    release_version=(root/'VERSION').read_text().strip()
except Exception:
    release_version='0.32.1'
checks=[]
def run(id, desc, cmd):
    try:
        p=subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        ok=p.returncode==0
    except Exception as e:
        ok=False; p=type('P',(),{'returncode':None,'stdout':'','stderr':str(e)})()
    checks.append({'id':id,'ok':ok,'rc':p.returncode,'description':desc,'stdout':p.stdout[-4000:],'stderr':p.stderr[-4000:]})
def file_check(id, desc, rel):
    candidates=[root/rel]
    if rel.startswith('../docs/'):
        candidates.append(Path('/usr/local/share/noemaforge/docs')/rel[len('../docs/'):])
    ok=any(p.exists() for p in candidates)
    checks.append({'id':id,'ok':ok,'description':desc,'path':' or '.join(str(p) for p in candidates)})
run('version_audit','Release metadata/runtime versions are consistent',[str(root/'tools/prep/noemaforge-version-audit.sh'),'--root',str(root)])
run('recursion_audit','No setup/installer/wrapper recursion hazards',[str(root/'tools/prep/noemaforge-recursion-audit.sh'),'--json',str(root)])
for rel in [
 'configs/multimodal-backends-policy.json','configs/media-pipeline-catalog.json','configs/persona-catalog.json','configs/autostart-llm-policy.json','configs/runtime-invariants.yaml',
 'tools/prep/noemaforge-multimodal.sh','tools/prep/noemaforge-persona-gui.sh','tools/prep/noemaforge-first-run-audit.sh','tools/prep/noemaforge-gui-recover-minimal.sh', 'configs/gui-shell-policy.json','configs/task-categories.json','configs/inactivity-policy.json','configs/pipeline-ui-catalog.json','configs/pipeline-editor-policy.json','configs/review-routing-policy.json','configs/runtime-device-policy.json','configs/smarthome-local-control-policy.json',
 f'../docs/wiki/multimodal/multimodal-vault-readiness-{release_version}.md', f'../docs/wiki/gui/persona-portraits-and-dashboard-{release_version}.md', f'../docs/wiki/gui/admin-console-and-admin-routing-{release_version}.md', f'../docs/wiki/evolution/model-evolution-control-plane-{release_version}.md', f'../docs/wiki/first-start/model-selection-modes-{release_version}.md', f'../docs/wiki/gui/admin-chat-locales-and-artifacts-{release_version}.md', f'../docs/wiki/multios/multios-runtime-host-roadmap-{release_version}.md', f'../docs/wiki/safety/sense-privacy-honesty-critics-rfc-roadmap-{release_version}.md', f'../docs/wiki/gui/stateful-gui-shell-{release_version}.md', f'../docs/wiki/telemetry/runtime-product-metrics-{release_version}.md', f'../docs/wiki/pipelines/pipeline-dock-editor-{release_version}.md', f'../docs/wiki/smarthome/local-first-smart-home-control-{release_version}.md', f'../docs/wiki/tasks/inactivity-and-task-governance-{release_version}.md', f'../docs/wiki/personas/persona-portrait-fallback-{release_version}.md', 'TODO.md']:
    file_check('file_'+rel.replace('/','_').replace('.','_'), 'Required release artifact exists', rel)

# Locale user-information docs required for public-facing active builds.
for loc in ['en','ru','uk','es','de','pt','it','zh-CN','ja','ko']:
    for doc in ['README.md','HOW2START.md','RELEASE_NOTES.md','USER_GUIDE.md']:
        file_check('file_docs_i18n_'+loc.replace('-','_')+'_'+doc.replace('.','_'), 'Localized user-information file exists', f'../docs/i18n/{loc}/{doc}')

for rel in ['configs/multimodal-backends-policy.json','configs/media-pipeline-catalog.json','configs/persona-catalog.json','configs/gui-shell-policy.json','configs/task-categories.json','configs/inactivity-policy.json','configs/pipeline-ui-catalog.json','configs/pipeline-editor-policy.json','configs/review-routing-policy.json','configs/runtime-device-policy.json','configs/smarthome-local-control-policy.json']:
    p=root/rel
    ok=False; msg=''
    try:
        json.loads(p.read_text()); ok=True
    except Exception as e: msg=str(e)
    checks.append({'id':'json_'+rel.replace('/','_'), 'ok':ok, 'description':'JSON config parses', 'path':str(p), 'message':msg})
for p in sorted((root/'configs'/'locales').glob('*.json')):
    ok=False; msg=''
    try:
        data=json.loads(p.read_text())
        ok=isinstance(data, dict)
    except Exception as e:
        msg=str(e)
    checks.append({'id':'json_locale_'+p.name.replace('.','_'), 'ok':ok, 'description':'Locale JSON parses', 'path':str(p), 'message':msg})
for rel in ['bin/noemaforge','tools/prep/noemaforge-multimodal.sh','tools/prep/noemaforge-persona-gui.sh','tools/prep/noemaforge-first-run-audit.sh','tools/prep/noemaforge-av-readiness.sh','tools/prep/noemaforge-gui-recover-minimal.sh']:
    run('bash_n_'+rel.replace('/','_'),'Shell script syntax',[ 'bash','-n', str(root/rel) ])
for rel in ['src/multimodal_runtime.py','src/pipeline_runtime.py','src/team_member_runtime.py','src/selftest_runtime.py','src/admin_runtime.py','src/admin_gui_server.py','src/dev_team_runtime.py','src/model_evolution_runtime.py','src/i18n_runtime.py','src/model_selection_runtime.py']:
    p=root/rel
    ok=False; msg=''
    try:
        compile(p.read_text(encoding='utf-8', errors='replace'), str(p), 'exec')
        ok=True
    except Exception as e:
        msg=str(e)
    checks.append({'id':'py_syntax_'+rel.replace('/','_'),'ok':ok,'description':'Python syntax','path':str(p),'message':msg})
failed=[c for c in checks if not c.get('ok')]
report={'ok':not failed,'root':str(root),'passed':len(checks)-len(failed),'failed':len(failed),'checks':checks}
if fmt=='json': print(json.dumps(report,indent=2,ensure_ascii=False))
else:
    if not failed:
        print(f"overall: OK ({len(checks)} consistency checks passed)")
    else:
        print(f"overall: FAIL ({len(failed)} failed / {len(checks)} total)")
        for c in failed: print(f"- {c['id']}: {c.get('description','')} {c.get('path','')}")
sys.exit(0 if not failed else 1)
PYCONSISTENCY
