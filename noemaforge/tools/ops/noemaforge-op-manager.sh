#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/ops/noemaforge-op-manager.sh
# Zone: operator/runtime
# Purpose: Safely inspect/reconcile/enable/disable NoemaForge backend-manager and modelscan timers.
# Callers: sudo noemaforge manager <status|disable|reconcile|enable>
# Safety: Runtime Desired Count defaults to 1. Reconcile enforces single-active-model mode.
# TODO(parallel-model-runtime): runtime_desired_count > 1 is future work and must require a scheduler/resource guard.
# === End NoemaForge File Header ===
set -euo pipefail

ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
# shellcheck source=/opt/noemaforge/tools/ops/noemaforge-op-common.sh
source "$ROOT/tools/ops/noemaforge-op-common.sh"

action="${1:-status}"; shift || true
LOCK_MODE="wait"
LOCK_WAIT_SECONDS="300"
RUNTIME_DESIRED_COUNT="${NOEMAFORGE_RUNTIME_DESIRED_COUNT:-1}"
PLAN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --runtime-desired-count|--desired-count|--max-active)
      RUNTIME_DESIRED_COUNT="${2:-1}"; shift 2 ;;
    --runtime-desired-count=*|--desired-count=*|--max-active=*)
      RUNTIME_DESIRED_COUNT="${1#*=}"; shift ;;
    --plan|--dry-run)
      PLAN=1; shift ;;
    --lock-wait|--wait-lock) LOCK_MODE="wait"; shift ;;
    --lock-wait=*) LOCK_MODE="wait"; LOCK_WAIT_SECONDS="${1#*=}"; shift ;;
    --skip-if-running) LOCK_MODE="skip"; shift ;;
    --lock-fail|--fail-if-running) LOCK_MODE="fail"; shift ;;
    *) break ;;
  esac
done

active_llama_count() {
  systemctl list-units --all --plain --no-legend 'noemaforge-llama@*.service' 2>/dev/null \
    | awk '$3=="active" {c++} END {print c+0}'
}

case "$action" in
  status)
    echo "=== runtime desired policy ==="
    echo "runtime_desired_count=${RUNTIME_DESIRED_COUNT}"
    echo "active_llama_units=$(active_llama_count)"
    echo "policy=/opt/noemaforge/configs/llm-backends-policy.yaml"
    echo "invariant=active_llama_units <= runtime_desired_count"
    echo "todo=parallel-model-runtime requires explicit scheduler/resource guard"
    echo
    echo "=== manager timers ==="
    systemctl is-enabled noemaforge-llm-backends-manager.timer 2>/dev/null || true
    systemctl is-active noemaforge-llm-backends-manager.timer 2>/dev/null || true
    systemctl is-enabled noemaforge-modelscan.timer 2>/dev/null || true
    systemctl is-active noemaforge-modelscan.timer 2>/dev/null || true
    echo
    echo "=== manager service ==="
    systemctl status noemaforge-llm-backends-manager.service noemaforge-modelscan.service --no-pager 2>/dev/null || true
    echo
    echo "=== llama units ==="
    systemctl list-units --all 'noemaforge-llama@*.service' --no-pager || true
    exit 0 ;;
  disable|off)
    systemctl disable --now noemaforge-llm-backends-manager.timer noemaforge-modelscan.timer 2>/dev/null || true
    systemctl stop noemaforge-llm-backends-manager.service noemaforge-modelscan.service 2>/dev/null || true
    systemctl reset-failed noemaforge-llm-backends-manager.service noemaforge-modelscan.service 2>/dev/null || true
    echo "[noemaforge-manager] backend manager/modelscan disabled."
    "$0" status --runtime-desired-count="$RUNTIME_DESIRED_COUNT"
    exit 0 ;;
  reconcile|once)
    if ! noemaforge_ops_lock_acquire "manager-reconcile" "$LOCK_MODE" "$LOCK_WAIT_SECONDS"; then
      rc=$?; [[ "$rc" == "66" ]] && exit 0; exit "$rc"
    fi
    echo "[noemaforge-manager] runtime desired count: $RUNTIME_DESIRED_COUNT"
    echo "[noemaforge-manager] runtime safety check before reconcile..."
    if [[ -f "$ROOT/src/runtime_safety.py" ]]; then
      /usr/bin/python3 "$ROOT/src/runtime_safety.py" check || {
        echo "[noemaforge-manager][ERROR] runtime-safety check failed; not reconciling." >&2
        exit 1
      }
    fi
    echo "[noemaforge-manager] running one reconcile pass with active-model limit..."
    args=(--reconcile --stop-extra --runtime-desired-count "$RUNTIME_DESIRED_COUNT")
    [[ "$PLAN" == "1" ]] && args+=(--plan)
    /usr/bin/python3 "$ROOT/src/llm_backends_manager.py" "${args[@]}"
    echo "[noemaforge-manager] reconcile done."
    systemctl --failed --no-pager || true
    systemctl list-units --all 'noemaforge-llama@*.service' --no-pager || true
    echo "[noemaforge-manager] active_llama_units=$(active_llama_count); runtime_desired_count=$RUNTIME_DESIRED_COUNT"
    exit 0 ;;
  enable|on)
    if ! noemaforge_ops_lock_acquire "manager-enable" "$LOCK_MODE" "$LOCK_WAIT_SECONDS"; then
      rc=$?; [[ "$rc" == "66" ]] && exit 0; exit "$rc"
    fi
    echo "[noemaforge-manager] checking runtime safety before enabling timers..."
    if [[ -f "$ROOT/src/runtime_safety.py" ]]; then
      /usr/bin/python3 "$ROOT/src/runtime_safety.py" check || {
        echo "[noemaforge-manager][ERROR] runtime-safety check failed; not enabling timers." >&2
        exit 1
      }
    fi
    echo "[noemaforge-manager] enforcing runtime_desired_count=$RUNTIME_DESIRED_COUNT before enabling timers..."
    /usr/bin/python3 "$ROOT/src/llm_backends_manager.py" --reconcile --stop-extra --runtime-desired-count "$RUNTIME_DESIRED_COUNT" || {
      echo "[noemaforge-manager][ERROR] reconcile failed; not enabling timers." >&2
      exit 1
    }
    systemctl enable --now noemaforge-modelscan.timer noemaforge-llm-backends-manager.timer
    echo "[noemaforge-manager] timers enabled in conservative single-active mode."
    "$0" status --runtime-desired-count="$RUNTIME_DESIRED_COUNT"
    exit 0 ;;
  help|-h|--help)
    cat <<'EOH'
Usage:
  sudo noemaforge manager status
  sudo noemaforge manager disable
  sudo noemaforge manager reconcile [--plan] [--runtime-desired-count=1]
  sudo noemaforge manager enable [--runtime-desired-count=1]

Invariant:
  runtime_desired_count defaults to 1.  The manager may see many safe ModelStore
  entries, but only runtime_desired_count noemaforge-llama@*.service instances may
  be active.  Extra running backends are stopped during reconcile.

Recommended path after safe-start/smoke:
  sudo noemaforge manager reconcile --plan
  sudo noemaforge manager reconcile
  noemaforge smoke
  sudo noemaforge manager enable

TODO:
  Parallel model runtime is future work and must require explicit scheduler and
  RAM/VRAM guards; do not infer parallelism from safe_count or ModelStore size.
EOH
    exit 0 ;;
  *)
    echo "[noemaforge-manager][ERROR] unknown action: $action" >&2
    exit 2 ;;
esac
