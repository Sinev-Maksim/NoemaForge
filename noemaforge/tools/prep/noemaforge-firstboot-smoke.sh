#!/usr/bin/env bash

# === NoemaForge Autodoc File Header ===
# File: tools/prep/noemaforge-firstboot-smoke.sh
# Purpose: Helper / validation script 'noemaforge-firstboot-smoke.sh'.
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
# File: tools/prep/noemaforge-firstboot-smoke.sh
# Zone: prep
# Purpose: Verify first-boot orchestration status, required scorecards, epoch state, and runtime sockets.
# Callers: install runbook, operator shell.
# Inputs: none.
# Outputs: human-readable OK/ERROR lines and process exit status.
# Side effects: reads local runtime state only.
# Security notes:
#   - Read-only validation helper.
# === End NoemaForge File Header ===
set -euo pipefail

fail() { printf '[noemaforge-smoke][ERROR] %s\n' "$*" >&2; exit 1; }
pass() { printf '[noemaforge-smoke][OK] %s\n' "$*"; }

[[ -f /var/lib/noemaforge/bootstrap/firstboot-status.json ]] || fail "firstboot-status.json missing"
python3 - <<'PY' || fail "firstboot status malformed"
import json
obj=json.load(open('/var/lib/noemaforge/bootstrap/firstboot-status.json','r',encoding='utf-8'))
assert obj.get('state') in {'reboot_pending','applied_no_reboot','blocked_no_models','blocked_apply_failed'}
print(obj.get('state'))
PY
pass "Firstboot status present"

[[ -S /run/noemaforge/llm/gateway.sock ]] || fail "LLM gateway socket missing"
[[ -S /run/noemaforge/toolproxy.sock ]] || fail "ToolProxy socket missing"
pass "Sockets present"


[[ -x /opt/noemaforge/bin/noemaforge-llama-start ]] || fail "noemaforge-llama-start wrapper missing"
[[ -x /opt/noemaforge/bin/llama-server ]] || fail "llama-server binary missing"
pass "Runtime model launcher present"

python3 /opt/noemaforge/src/gguf_select.py validate-modelstore --root /var/lib/modelstore --json-out /var/lib/noemaforge/bootstrap/modelstore-validation.safe.json >/dev/null || fail "ModelStore GGUF shard validation failed"
pass "ModelStore GGUF shard safety validated"

[[ -f /var/lib/modelstore/model_registry.json ]] || fail "Model registry missing"
[[ -d /var/lib/noemaforge/model_scorecards ]] || fail "Model scorecards directory missing"
scorecard_exists() {
  local name="$1"
  # Do not use `find | grep` here: under `set -o pipefail`, grep can exit
  # before find finishes after the first match and make an existing scorecard
  # look like a smoke failure. `-print -quit` plus command substitution is
  # deterministic and cheap.
  [[ -n "$(find /var/lib/noemaforge/model_scorecards -type f -name "*$name" -print -quit 2>/dev/null)" ]]
}
scorecard_exists 'operator.admin__administrator__llm.json' || fail "Administrator scorecard missing"
scorecard_exists 'system.guard__surgeon__llm.json' || fail "Surgeon scorecard missing"
pass "Expected scorecards present"

python3 - <<'PY' || fail "Current epoch path missing"
import os
cur='/var/lib/noemaforge/contracts/epochs/current'
assert os.path.islink(cur) or os.path.isdir(cur)
print('epoch-ok')
PY
pass "Epoch path present"
