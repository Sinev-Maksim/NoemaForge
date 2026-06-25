#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/ops/noemaforge-op-safe-start.sh
# Zone: operator/runtime
# Purpose: Idempotently start the safe NoemaForge core with explicit LLM profile: runtime-only, CPU bootstrap LLM, or manual heavy LLM.
# Callers: sudo noemaforge safe-start, sudo noemaforge start, sudo noemaforge up.
# Safety: Keeps backend-manager/modelscan timers disabled unless --enable-managers is explicitly supplied.
# Version: 0.32.1 live-reboot-stabilization
# === End NoemaForge File Header ===
set -euo pipefail

ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
# shellcheck source=/opt/noemaforge/tools/ops/noemaforge-op-common.sh
source "$ROOT/tools/ops/noemaforge-op-common.sh"

LOCK_MODE="wait"
LOCK_WAIT_SECONDS="300"
ENABLE_MANAGERS="0"
SKIP_REPAIR="0"
WAIT_HEALTH="1"
FORCE_RESTART="0"
MIN_AVAILABLE_GB="${NOEMAFORGE_MIN_AVAILABLE_GB:-4}"
LLM_PROFILE="${NOEMAFORGE_SAFE_START_LLM_PROFILE:-bootstrap_cpu_llm}"
ALLOW_HEAVY_LLM="0"
PRESERVE_EXISTING_LLM="0"
MAIN_SOCK="/run/noemaforge/llm/backends/main.sock"
MAIN_UNIT="noemaforge-llama@main.service"

backend_health() {
  [[ -S "$MAIN_SOCK" ]] || return 1
  sudo -u noemaforge curl -fsS --max-time 5 --unix-socket "$MAIN_SOCK" http://localhost:8080/health >/tmp/noemaforge-safe-start-health.out 2>/tmp/noemaforge-safe-start-health.err
}

normalize_llm_profile() {
  case "$LLM_PROFILE" in
    runtime_only|no_llm|none|disabled) LLM_PROFILE="runtime_only" ;;
    bootstrap_cpu_llm|bootstrap|cpu|cpu_bootstrap) LLM_PROFILE="bootstrap_cpu_llm" ;;
    heavy_manual|manual_heavy|allow_heavy) LLM_PROFILE="heavy_manual"; ALLOW_HEAVY_LLM="1" ;;
    *) echo "[noemaforge-safe-start][ERROR] unsupported --llm-profile: $LLM_PROFILE" >&2; exit 2 ;;
  esac
}

is_heavy_model_target() {
  local target="${1,,}"
  # Conservative heuristic: anything above small CPU bootstrap class is manual-only.
  echo "$target" | grep -Eiq '(14b|30b|32b|34b|70b|72b|mixtral|moe|qwen.?2\.5.?14b|gpu-heavy|research-heavy)'
}

print_llm_policy() {
  echo "[noemaforge-safe-start] llm_profile=$LLM_PROFILE"
  echo "[noemaforge-safe-start] policy: gui=runtime_only by default; wogui=bootstrap_cpu_llm; heavy_llm=manual_only; max_active_llms=1"
}

stop_main_backend() {
  echo "[noemaforge-safe-start] stopping stale main backend if present..."
  systemctl stop "$MAIN_UNIT" 2>/dev/null || true
  # Only target processes that are bound to the main NoemaForge backend socket.
  pkill -TERM -f '[l]lama-server.*\/run\/noemaforge\/llm\/backends\/main\.sock' 2>/dev/null || true
  pkill -TERM -f '[l]lama-server-cuda.*\/run\/noemaforge\/llm\/backends\/main\.sock' 2>/dev/null || true
  sleep 1
  pkill -KILL -f '[l]lama-server.*\/run\/noemaforge\/llm\/backends\/main\.sock' 2>/dev/null || true
  pkill -KILL -f '[l]lama-server-cuda.*\/run\/noemaforge\/llm\/backends\/main\.sock' 2>/dev/null || true
  rm -f "$MAIN_SOCK" 2>/dev/null || true
}

usage() { cat <<'EOH'
Usage:
  sudo noemaforge safe-start [--wait|--direct] [--llm-profile=runtime_only|bootstrap_cpu_llm|heavy_manual]

Starts safe NoemaForge runtime:
  - disables backend-manager/modelscan timers by default;
  - runs runtime-safety repair/check when available;
  - starts noemaforge-llm-gateway and noemaforge-toolproxy;
  - starts LLM backend only with --llm-profile=bootstrap_cpu_llm or --llm-profile=heavy_manual;
  - runtime_only enforces no active main backend unless --preserve-existing-llm is explicit;
  - blocks heavy model starts unless --llm-profile=heavy_manual/--allow-heavy is explicit;
  - keeps max_active_llms=1.

Recommended boot-mode policy:
  GUI mode:   runtime_only by default; CPU bootstrap LLM optional; heavy LLM manual only.
  woGUI mode: bootstrap_cpu_llm by default; heavy LLM manual only.

Examples:
  sudo noemaforge safe-start --llm-profile=runtime_only --wait
  sudo noemaforge safe-start --llm-profile=bootstrap_cpu_llm --wait
  sudo noemaforge safe-start --llm-profile=heavy_manual --restart --wait
EOH
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable-managers|--full) ENABLE_MANAGERS="1"; shift ;;
    --no-health-wait) WAIT_HEALTH="0"; shift ;;
    --skip-repair) SKIP_REPAIR="1"; shift ;;
    --restart|--force-restart) FORCE_RESTART="1"; shift ;;
    --preserve-existing-llm) PRESERVE_EXISTING_LLM="1"; shift ;;
    --llm-profile) LLM_PROFILE="$2"; shift 2 ;;
    --llm-profile=*) LLM_PROFILE="${1#*=}"; shift ;;
    --runtime-only|--no-llm) LLM_PROFILE="runtime_only"; WAIT_HEALTH="0"; shift ;;
    --bootstrap-cpu-llm|--cpu-bootstrap) LLM_PROFILE="bootstrap_cpu_llm"; shift ;;
    --allow-heavy|--heavy-manual) LLM_PROFILE="heavy_manual"; ALLOW_HEAVY_LLM="1"; shift ;;
    --min-available-gb=*) MIN_AVAILABLE_GB="${1#*=}"; shift ;;
    --lock-wait|--wait-lock) LOCK_MODE="wait"; shift ;;
    --lock-wait=*) LOCK_MODE="wait"; LOCK_WAIT_SECONDS="${1#*=}"; shift ;;
    --lock-fail|--fail-if-running) LOCK_MODE="fail"; shift ;;
    --skip-if-running) LOCK_MODE="skip"; shift ;;
    -h|--help|help) usage; exit 0 ;;
    *) echo "[noemaforge-safe-start][ERROR] unknown option: $1" >&2; exit 2 ;;
  esac
done

normalize_llm_profile
[[ "$LLM_PROFILE" == "runtime_only" ]] && WAIT_HEALTH="0"
print_llm_policy

if ! noemaforge_ops_lock_acquire "safe-start" "$LOCK_MODE" "$LOCK_WAIT_SECONDS"; then
  rc=$?
  [[ "$rc" == "66" ]] && exit 0
  exit "$rc"
fi

echo "[noemaforge-safe-start] checking available memory..."
free -h || true
AVAILABLE_KB="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
AVAILABLE_GB="$(( AVAILABLE_KB / 1024 / 1024 ))"
if [[ "$AVAILABLE_GB" -lt "$MIN_AVAILABLE_GB" ]]; then
  echo "[noemaforge-safe-start][ERROR] less than ${MIN_AVAILABLE_GB} GiB available RAM. Run: sudo noemaforge safe-mode" >&2
  exit 1
fi

if [[ "$ENABLE_MANAGERS" != "1" ]]; then
  echo "[noemaforge-safe-start] keeping backend-manager/modelscan timers disabled."
  systemctl disable --now noemaforge-llm-backends-manager.timer noemaforge-modelscan.timer 2>/dev/null || true
  systemctl stop noemaforge-llm-backends-manager.service 2>/dev/null || true
fi

install -d -o noemaforge -g noemaforge -m 0750 /run/noemaforge /run/noemaforge/llm /run/noemaforge/llm/backends 2>/dev/null || {
  mkdir -p /run/noemaforge/llm/backends
  chown -R noemaforge:noemaforge /run/noemaforge 2>/dev/null || true
}

if command -v noemaforge-sel-fix >/dev/null 2>&1; then
  noemaforge-sel-fix --smoke || true
fi

if [[ -f "$ROOT/src/runtime_safety.py" ]]; then
  if [[ "$SKIP_REPAIR" != "1" ]]; then
    echo "[noemaforge-safe-start] running runtime-safety repair..."
    /usr/bin/python3 "$ROOT/src/runtime_safety.py" repair || true
  fi
  echo "[noemaforge-safe-start] running runtime-safety check..."
  /usr/bin/python3 "$ROOT/src/runtime_safety.py" check || true
else
  echo "[noemaforge-safe-start][WARN] runtime_safety.py not found; continuing."
fi

MAIN_TARGET=""
if [[ "$LLM_PROFILE" == "runtime_only" ]]; then
  if [[ "$PRESERVE_EXISTING_LLM" == "1" ]]; then
    echo "[noemaforge-safe-start] runtime_only profile: preserving existing LLM because --preserve-existing-llm was supplied."
  else
    echo "[noemaforge-safe-start] runtime_only profile: enforcing no active main backend."
    systemctl disable "$MAIN_UNIT" 2>/dev/null || true
    stop_main_backend
  fi
fi
if [[ "$LLM_PROFILE" != "runtime_only" ]]; then
  if [[ ! -e /var/lib/modelstore/models/main/model.gguf ]]; then
    echo "[noemaforge-safe-start][ERROR] /var/lib/modelstore/models/main/model.gguf is missing." >&2
    echo "[noemaforge-safe-start][HINT] Run: sudo noemaforge runtime-safety repair || sudo noemaforge prepare-gui" >&2
    exit 1
  fi

  MAIN_TARGET="$(readlink -f /var/lib/modelstore/models/main/model.gguf 2>/dev/null || true)"
  echo "[noemaforge-safe-start] main model target: ${MAIN_TARGET:-unknown}"
  if echo "$MAIN_TARGET" | grep -Eiq '0000?[2-9].*of|0000?[2-9]-of|0000?[2-9]_of'; then
    echo "[noemaforge-safe-start][ERROR] main points to non-head shard: $MAIN_TARGET" >&2
    exit 1
  fi
  if is_heavy_model_target "$MAIN_TARGET" && [[ "$ALLOW_HEAVY_LLM" != "1" ]]; then
    echo "[noemaforge-safe-start][ERROR] heavy model detected and heavy LLM autostart is manual-only: $MAIN_TARGET" >&2
    echo "[noemaforge-safe-start][HINT] Use explicit manual mode: sudo noemaforge safe-start --llm-profile=heavy_manual --restart" >&2
    exit 1
  fi
else
  echo "[noemaforge-safe-start] runtime_only profile: skipping modelstore/backend start."
fi

echo "[noemaforge-safe-start] enabling safe core services..."
if [[ "$LLM_PROFILE" == "runtime_only" ]]; then
  systemctl enable noemaforge-llm-gateway.service noemaforge-toolproxy.service 2>/dev/null || true
else
  systemctl enable noemaforge-llm-gateway.service noemaforge-toolproxy.service "$MAIN_UNIT" 2>/dev/null || true
fi

echo "[noemaforge-safe-start] starting gateway/toolproxy..."
systemctl daemon-reload
systemctl reset-failed || true
systemctl start noemaforge-llm-gateway.service
systemctl start noemaforge-toolproxy.service

if [[ "$LLM_PROFILE" == "runtime_only" ]]; then
  echo "[noemaforge-safe-start] runtime_only profile: gateway/toolproxy started; main backend not started."
else
  MAIN_ACTIVE="$(systemctl is-active "$MAIN_UNIT" 2>/dev/null || true)"
  if [[ "$FORCE_RESTART" == "1" ]]; then
    echo "[noemaforge-safe-start] --restart requested."
    stop_main_backend
    echo "[noemaforge-safe-start] starting main backend..."
    systemctl start "$MAIN_UNIT"
  elif [[ "$MAIN_ACTIVE" == "active" ]]; then
    echo "[noemaforge-safe-start] main backend is already active; checking health before touching socket."
    if backend_health; then
      echo "[noemaforge-safe-start] existing main backend is healthy; leaving it running."
    else
      echo "[noemaforge-safe-start][WARN] main is active but unhealthy or socket missing; restarting main only."
      cat /tmp/noemaforge-safe-start-health.err 2>/dev/null || true
      stop_main_backend
      systemctl start "$MAIN_UNIT"
    fi
  else
    echo "[noemaforge-safe-start] main backend is not active; cleaning stale socket and starting."
    rm -f "$MAIN_SOCK" 2>/dev/null || true
    systemctl start "$MAIN_UNIT"
  fi
fi

if [[ "$WAIT_HEALTH" == "1" && "$LLM_PROFILE" != "runtime_only" ]]; then
  echo "[noemaforge-safe-start] waiting for main backend socket..."
  for _ in $(seq 1 90); do
    [[ -S "$MAIN_SOCK" ]] && break
    sleep 1
  done
  if [[ ! -S "$MAIN_SOCK" ]]; then
    echo "[noemaforge-safe-start][ERROR] main backend socket did not appear." >&2
    systemctl status "$MAIN_UNIT" --no-pager || true
    journalctl -u "$MAIN_UNIT" -n 160 --no-pager || true
    exit 1
  fi

  echo "[noemaforge-safe-start] waiting for backend health..."
  ok="0"
  for _ in $(seq 1 120); do
    if backend_health; then
      ok="1"
      cat /tmp/noemaforge-safe-start-health.out
      break
    fi
    sleep 2
  done
  if [[ "$ok" != "1" ]]; then
    echo "[noemaforge-safe-start][ERROR] backend health did not pass." >&2
    cat /tmp/noemaforge-safe-start-health.err 2>/dev/null || true
    systemctl status "$MAIN_UNIT" --no-pager || true
    exit 1
  fi
fi

if [[ "$ENABLE_MANAGERS" == "1" ]]; then
  echo "[noemaforge-safe-start] --enable-managers requested: starting manager timers after safe core."
  systemctl enable --now noemaforge-modelscan.timer noemaforge-llm-backends-manager.timer 2>/dev/null || true
fi

echo
echo "=== status ==="
if [[ "$LLM_PROFILE" == "runtime_only" ]]; then
  systemctl status noemaforge-llm-gateway.service noemaforge-toolproxy.service --no-pager || true
else
  systemctl status "$MAIN_UNIT" noemaforge-llm-gateway.service noemaforge-toolproxy.service --no-pager || true
fi

echo
echo "=== failed ==="
systemctl --failed --no-pager || true

echo "[noemaforge-safe-start] done profile=$LLM_PROFILE"
