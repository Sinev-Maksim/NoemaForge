#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/ops/noemaforge-op-start-llm-safe.sh
# Zone: operator/runtime
# Purpose: Start only the main LLM backend after RAM and modelstore checks.
# Callers: sudo noemaforge start-llm-safe, systemd transient jobs, legacy wrapper noemaforge-start-llm-safe.
# Safety: Keeps modelscan/backend-manager timers disabled to avoid surprise extra loads.
# === End NoemaForge File Header ===
set -euo pipefail

MIN_AVAILABLE_GB="${NOEMAFORGE_MIN_AVAILABLE_GB:-6}"

echo "[noemaforge-start-llm-safe] checking memory..."
free -h

AVAILABLE_KB="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
AVAILABLE_GB="$(( AVAILABLE_KB / 1024 / 1024 ))"

if [ "$AVAILABLE_GB" -lt "$MIN_AVAILABLE_GB" ]; then
  echo "[noemaforge-start-llm-safe] ERROR: less than ${MIN_AVAILABLE_GB} GiB available RAM."
  echo "[noemaforge-start-llm-safe] Run: sudo noemaforge safe-mode"
  exit 1
fi

if [ ! -e /var/lib/modelstore/models/main/model.gguf ]; then
  echo "[noemaforge-start-llm-safe] ERROR: /var/lib/modelstore/models/main/model.gguf is missing."
  echo "[noemaforge-start-llm-safe] Run: sudo noemaforge prepare-gui && noemaforge models"
  exit 1
fi

if [ ! -x /opt/noemaforge/bin/llama-server ] && [ ! -x /opt/noemaforge/bin/noemaforge-llama-start ]; then
  echo "[noemaforge-start-llm-safe] ERROR: llama runtime is missing."
  echo "[noemaforge-start-llm-safe] Expected /opt/noemaforge/bin/llama-server or wrapper."
  exit 1
fi

echo "[noemaforge-start-llm-safe] making sure timers stay disabled..."
systemctl disable --now noemaforge-modelscan.timer noemaforge-llm-backends-manager.timer 2>/dev/null || true

echo "[noemaforge-start-llm-safe] starting main LLM only..."
systemctl start noemaforge-llama@main.service

echo "[noemaforge-start-llm-safe] waiting for socket..."
for _ in $(seq 1 60); do
  if [ -S /run/noemaforge/llm/backends/main.sock ]; then
    break
  fi
  sleep 1
done

if [ ! -S /run/noemaforge/llm/backends/main.sock ]; then
  echo "[noemaforge-start-llm-safe] ERROR: backend socket did not appear."
  systemctl status noemaforge-llama@main.service --no-pager || true
  journalctl -u noemaforge-llama@main.service -n 120 --no-pager || true
  exit 1
fi

echo "[noemaforge-start-llm-safe] checking health..."
sudo -u noemaforge curl --max-time 10 \
  --unix-socket /run/noemaforge/llm/backends/main.sock \
  http://localhost:8080/health || true

echo
echo "[noemaforge-start-llm-safe] status:"
pgrep -a -f '[l]lama-server' || true
free -h
nvidia-smi 2>/dev/null | head -35 || true
