#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/ops/noemaforge-op-llm-stop.sh
# Zone: operator/runtime
# Purpose: Idempotently stop NoemaForge LLM runtime, all llama units, timers and stale sockets.
# Callers: sudo noemaforge llm-stop, sudo noemaforge service-stop, transient systemd jobs, legacy wrappers.
# Safety: Locked with flock; repeated executions do not create concurrent pkill/systemctl storms.
# === End NoemaForge File Header ===
set -euo pipefail

ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
# shellcheck source=/opt/noemaforge/tools/ops/noemaforge-op-common.sh
source "$ROOT/tools/ops/noemaforge-op-common.sh"

LOCK_MODE="skip"
LOCK_WAIT_SECONDS="300"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --lock-wait|--wait-lock)
      LOCK_MODE="wait"; shift ;;
    --lock-wait=*)
      LOCK_MODE="wait"; LOCK_WAIT_SECONDS="${1#*=}"; shift ;;
    --lock-fail|--fail-if-running)
      LOCK_MODE="fail"; shift ;;
    --skip-if-running)
      LOCK_MODE="skip"; shift ;;
    *)
      break ;;
  esac
done

if ! noemaforge_ops_lock_acquire "llm-service-stop" "$LOCK_MODE" "$LOCK_WAIT_SECONDS"; then
  rc=$?
  # skip-if-running is intentionally success/idempotent.
  [[ "$rc" == "66" ]] && exit 0
  exit "$rc"
fi

echo "[noemaforge-service-stop] stopping NoemaForge LLM services..."

echo "[noemaforge-service-stop] disabling timers..."
systemctl disable --now noemaforge-modelscan.timer noemaforge-llm-backends-manager.timer 2>/dev/null || true

echo "[noemaforge-service-stop] stopping backend manager..."
systemctl stop noemaforge-llm-backends-manager.service 2>/dev/null || true

mapfile -t LLAMA_UNITS < <(noemaforge_list_llama_units)
if [[ ${#LLAMA_UNITS[@]} -gt 0 ]]; then
  echo "[noemaforge-service-stop] stopping llama units: ${LLAMA_UNITS[*]}"
  systemctl stop "${LLAMA_UNITS[@]}" 2>/dev/null || true
else
  echo "[noemaforge-service-stop] no noemaforge-llama@*.service units found"
fi

echo "[noemaforge-service-stop] terminating llama-server processes..."
pkill -TERM -f '[l]lama-server' 2>/dev/null || true
sleep 2
pkill -KILL -f '[l]lama-server' 2>/dev/null || true

echo "[noemaforge-service-stop] removing stale sockets..."
rm -f /run/noemaforge/llm/backends/*.sock 2>/dev/null || true

echo "[noemaforge-service-stop] resetting failed runtime units..."
if [[ ${#LLAMA_UNITS[@]} -gt 0 ]]; then
  systemctl reset-failed "${LLAMA_UNITS[@]}" 2>/dev/null || true
fi
systemctl reset-failed noemaforge-llm-backends-manager.service noemaforge-modelscan.service 2>/dev/null || true
systemctl reset-failed 2>/dev/null || true

echo "[noemaforge-service-stop] status:"
pgrep -a -f '[l]lama-server' || echo "llama-server stopped"
ls -la /run/noemaforge/llm/backends 2>/dev/null || true
free -h || true
nvidia-smi 2>/dev/null | head -20 || true

echo
echo "=== failed ==="
systemctl --failed --no-pager || true

echo
echo "=== llama units ==="
systemctl list-units --all 'noemaforge-llama@*.service' --no-pager || true

echo "[noemaforge-service-stop] done"
