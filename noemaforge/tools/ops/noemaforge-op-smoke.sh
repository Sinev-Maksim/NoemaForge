#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/ops/noemaforge-op-smoke.sh
# Zone: operator/diagnostics
# Purpose: Smoke-test NoemaForge backend and gateway sockets with health/chat checks.
# Callers: noemaforge smoke, sudo noemaforge smoke, noemaforge runtime-safety smoke-main.
# Safety: Read-only network calls over local Unix sockets; does not start/stop services.
# Notes: 0.28.12 uses per-run temp files to avoid stale /tmp ownership false-negatives.
#        0.33.0 uses liveness-oriented health: non-empty model reply = live (optional --strict-ok for exact "OK" match).
# === End NoemaForge File Header ===
set -euo pipefail

BACKEND_SOCK="${NOEMAFORGE_BACKEND_SOCKET:-/run/noemaforge/llm/backends/main.sock}"
GATEWAY_SOCK="${NOEMAFORGE_GATEWAY_SOCKET:-/run/noemaforge/llm/gateway.sock}"
TIMEOUT="${NOEMAFORGE_SMOKE_TIMEOUT:-90}"
JSON_ONLY="0"
DEBUG="0"
ALLOW_GATEWAY_ONLY="0"
STRICT_OK="0"
PROFILE="${NOEMAFORGE_SMOKE_PROFILE:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) JSON_ONLY="1"; shift ;;
    --debug) DEBUG="1"; shift ;;
    --strict-ok) STRICT_OK="1"; shift ;;
    --profile)
      [[ $# -ge 2 && -n "$2" ]] || { echo "[noemaforge-smoke][ERROR] --profile requires a value" >&2; exit 2; }
      PROFILE="$2"
      shift 2
      ;;
    --profile=*)
      PROFILE="${1#*=}"
      [[ -n "$PROFILE" ]] || { echo "[noemaforge-smoke][ERROR] --profile requires a non-empty value" >&2; exit 2; }
      shift ;;
    --runtime-only|--runtime_only) PROFILE="runtime_only"; shift ;;
    --gateway-only-ok|--allow-gateway-only) ALLOW_GATEWAY_ONLY="1"; shift ;;
    --backend-sock=*)
      BACKEND_SOCK="${1#*=}"
      [[ -n "$BACKEND_SOCK" ]] || { echo "[noemaforge-smoke][ERROR] --backend-sock requires a non-empty value" >&2; exit 2; }
      shift ;;
    --gateway-sock=*)
      GATEWAY_SOCK="${1#*=}"
      [[ -n "$GATEWAY_SOCK" ]] || { echo "[noemaforge-smoke][ERROR] --gateway-sock requires a non-empty value" >&2; exit 2; }
      shift ;;
    --timeout=*)
      TIMEOUT="${1#*=}"
      [[ "$TIMEOUT" =~ ^[0-9]+$ && "$TIMEOUT" -gt 0 ]] || { echo "[noemaforge-smoke][ERROR] --timeout requires a positive integer" >&2; exit 2; }
      shift ;;
    -h|--help|help)
      cat <<'EOH'
Usage:
  noemaforge smoke [--json] [--debug] [--profile runtime_only] [--gateway-only-ok] [--strict-ok]

Checks:
  - backend /health over /run/noemaforge/llm/backends/main.sock
  - backend chat completion (default: non-empty reply = live; --strict-ok: exact "OK" = live)
  - gateway /health over /run/noemaforge/llm/gateway.sock
  - gateway chat completion (default: non-empty reply = live; --strict-ok: exact "OK" = live)

Notes:
  --profile runtime_only validates the gateway-only runtime profile and treats the
  intentionally absent main backend as skipped_expected_runtime_only.

  --strict-ok requires an exact literal "OK" response from model chat completions;
  by default, any non-empty reply is accepted as liveness indication (suitable for
  tiny instruct models that may reply OK. or OK! or other natural variations).
EOH
      exit 0 ;;
    *) echo "[noemaforge-smoke][ERROR] unknown option: $1" >&2; exit 2 ;;
  esac
done

case "$PROFILE" in
  runtime_only|no_llm|none|disabled) PROFILE="runtime_only"; ALLOW_GATEWAY_ONLY="1" ;;
  ""|bootstrap_cpu_llm|heavy_manual) : ;;
  *) echo "[noemaforge-smoke][ERROR] unsupported --profile: $PROFILE" >&2; exit 2 ;;
esac

TMPDIR="$(mktemp -d /tmp/noemaforge-smoke.XXXXXX)"
trap 'rm -rf "$TMPDIR"' EXIT

curl_local() {
  # If running as root, use the service account so socket permissions match runtime use.
  # If running as normal user, use that user; cat is expected to be in group noemaforge.
  if [[ ${EUID:-$(id -u)} -eq 0 ]] && id noemaforge >/dev/null 2>&1; then
    sudo -u noemaforge curl "$@"
  else
    curl "$@"
  fi
}

json_get_content() {
  local file="$1"
  jq -r '.choices[0].message.content // empty' "$file" 2>/dev/null || true
}

result_backend_health="fail"
result_backend_chat="fail"
result_gateway_health="fail"
result_gateway_chat="fail"
backend_response=""
gateway_response=""
backend_health_err=""
backend_chat_err=""
gateway_health_err=""
gateway_chat_err=""

if [[ -S "$BACKEND_SOCK" ]]; then
  if curl_local -fsS --max-time 20 --unix-socket "$BACKEND_SOCK" http://localhost:8080/health >"$TMPDIR/backend-health.out" 2>"$TMPDIR/backend-health.err"; then
    result_backend_health="ok"
  else
    backend_health_err="$(cat "$TMPDIR/backend-health.err" 2>/dev/null || true)"
  fi

  if curl_local -sS --max-time "$TIMEOUT" --unix-socket "$BACKEND_SOCK" http://localhost:8080/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{"model":"main","messages":[{"role":"user","content":"Return exactly: OK"}],"max_tokens":8,"temperature":0}' >"$TMPDIR/backend-chat.json" 2>"$TMPDIR/backend-chat.err"; then
    backend_response="$(json_get_content "$TMPDIR/backend-chat.json")"
    if [[ "$STRICT_OK" == "1" ]]; then
      [[ "$backend_response" == "OK" ]] && result_backend_chat="ok" || result_backend_chat="non_ok_response"
    else
      [[ -n "$backend_response" ]] && result_backend_chat="ok" || result_backend_chat="non_ok_response"
    fi
  else
    backend_chat_err="$(cat "$TMPDIR/backend-chat.err" 2>/dev/null || true)"
  fi
else
  if [[ "$PROFILE" == "runtime_only" ]]; then
    result_backend_health="skipped_expected_runtime_only"
    result_backend_chat="skipped_expected_runtime_only"
    backend_health_err="main backend intentionally absent for runtime_only profile: $BACKEND_SOCK"
    backend_chat_err="$backend_health_err"
  else
    backend_health_err="backend socket missing: $BACKEND_SOCK"
    backend_chat_err="$backend_health_err"
    echo "[noemaforge-smoke][WARN] $backend_health_err" >&2
  fi
fi

if [[ -S "$GATEWAY_SOCK" ]]; then
  if curl_local -fsS --max-time 20 --unix-socket "$GATEWAY_SOCK" http://localhost/health >"$TMPDIR/gateway-health.out" 2>"$TMPDIR/gateway-health.err"; then
    result_gateway_health="ok"
  else
    gateway_health_err="$(cat "$TMPDIR/gateway-health.err" 2>/dev/null || true)"
  fi

  if [[ "$PROFILE" == "runtime_only" ]]; then
    result_gateway_chat="skipped_expected_runtime_only"
  elif curl_local -sS --max-time "$TIMEOUT" --unix-socket "$GATEWAY_SOCK" http://localhost/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{"model":"main","messages":[{"role":"user","content":"Return exactly: OK"}],"max_tokens":8,"temperature":0}' >"$TMPDIR/gateway-chat.json" 2>"$TMPDIR/gateway-chat.err"; then
    gateway_response="$(json_get_content "$TMPDIR/gateway-chat.json")"
    if [[ "$STRICT_OK" == "1" ]]; then
      [[ "$gateway_response" == "OK" ]] && result_gateway_chat="ok" || result_gateway_chat="non_ok_response"
    else
      [[ -n "$gateway_response" ]] && result_gateway_chat="ok" || result_gateway_chat="non_ok_response"
    fi
  else
    gateway_chat_err="$(cat "$TMPDIR/gateway-chat.err" 2>/dev/null || true)"
  fi
else
  gateway_health_err="gateway socket missing: $GATEWAY_SOCK"
  gateway_chat_err="$gateway_health_err"
  echo "[noemaforge-smoke][WARN] $gateway_health_err" >&2
fi

overall="ok"
if [[ "$PROFILE" == "runtime_only" ]]; then
  [[ "$result_gateway_health" == "ok" ]] || overall="fail"
else
  for x in "$result_backend_health" "$result_backend_chat" "$result_gateway_health" "$result_gateway_chat"; do
    [[ "$x" == "ok" ]] || overall="fail"
  done
fi

if [[ "$overall" != "ok" && "$ALLOW_GATEWAY_ONLY" == "1" ]]; then
  if [[ "$result_gateway_health" == "ok" && "$result_gateway_chat" == "ok" ]]; then
    overall="gateway_only_ok"
  fi
fi

if [[ "$JSON_ONLY" == "1" ]]; then
  jq -n \
    --arg overall "$overall" \
    --arg profile "$PROFILE" \
    --arg backend_health "$result_backend_health" \
    --arg backend_chat "$result_backend_chat" \
    --arg gateway_health "$result_gateway_health" \
    --arg gateway_chat "$result_gateway_chat" \
    --arg backend_response "$backend_response" \
    --arg gateway_response "$gateway_response" \
    --arg backend_sock "$BACKEND_SOCK" \
    --arg gateway_sock "$GATEWAY_SOCK" \
    --arg backend_health_err "$backend_health_err" \
    --arg backend_chat_err "$backend_chat_err" \
    --arg gateway_health_err "$gateway_health_err" \
    --arg gateway_chat_err "$gateway_chat_err" \
    '{overall:$overall, profile:$profile, backend:{sock:$backend_sock, health:$backend_health, chat:$backend_chat, response:$backend_response, health_error:$backend_health_err, chat_error:$backend_chat_err}, gateway:{sock:$gateway_sock, health:$gateway_health, chat:$gateway_chat, response:$gateway_response, health_error:$gateway_health_err, chat_error:$gateway_chat_err}}'
else
  echo "=== NoemaForge smoke ==="
  [[ -n "$PROFILE" ]] && echo "profile:        $PROFILE"
  echo "backend socket: $BACKEND_SOCK"
  echo "backend health: $result_backend_health"
  echo "backend chat:   $result_backend_chat response=${backend_response:-<empty>}"
  echo "gateway socket: $GATEWAY_SOCK"
  echo "gateway health: $result_gateway_health"
  echo "gateway chat:   $result_gateway_chat response=${gateway_response:-<empty>}"
  echo "overall:        $overall"
  if [[ "$DEBUG" == "1" || "$overall" != "ok" ]]; then
    echo
    echo "=== NoemaForge smoke debug ==="
    [[ -n "$backend_health_err" ]] && echo "backend health error: $backend_health_err"
    [[ -n "$backend_chat_err" ]] && echo "backend chat error: $backend_chat_err"
    [[ -n "$gateway_health_err" ]] && echo "gateway health error: $gateway_health_err"
    [[ -n "$gateway_chat_err" ]] && echo "gateway chat error: $gateway_chat_err"
  fi
fi

[[ "$overall" == "ok" || "$overall" == "gateway_only_ok" ]]
