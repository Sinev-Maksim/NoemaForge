#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/ops/noemaforge-op-llm-memory-override.sh
# Zone: operator/runtime-limits
# Purpose: Create a memory-limit drop-in for noemaforge-llama@main.service based on host RAM.
# Callers: sudo noemaforge llm-memory-override, legacy wrapper noemaforge-llm-memory-override.
# === End NoemaForge File Header ===
set -euo pipefail

SERVICE="noemaforge-llama@main.service"
DROPIN_DIR="/etc/systemd/system/${SERVICE}.d"
DROPIN_FILE="${DROPIN_DIR}/20-memory-limits.conf"

TOTAL_KB="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
TOTAL_MB="$(( TOTAL_KB / 1024 ))"

RESERVE_MB="${NOEMAFORGE_LLM_RESERVE_MB:-2048}"
MAX_MB="$(( TOTAL_MB - RESERVE_MB ))"
HIGH_MB="$(( MAX_MB - 1024 ))"

if [ "$MAX_MB" -lt 4096 ]; then
  echo "ERROR: calculated MemoryMax is too low: ${MAX_MB}M"
  exit 1
fi

if [ "$HIGH_MB" -lt 3072 ]; then
  HIGH_MB="$MAX_MB"
fi

echo "[noemaforge-llm-memory-override] Total RAM: ${TOTAL_MB}M"
echo "[noemaforge-llm-memory-override] Reserve: ${RESERVE_MB}M"
echo "[noemaforge-llm-memory-override] MemoryHigh: ${HIGH_MB}M"
echo "[noemaforge-llm-memory-override] MemoryMax: ${MAX_MB}M"

mkdir -p "$DROPIN_DIR"

cat > "$DROPIN_FILE" <<EOC
[Service]
MemoryHigh=${HIGH_MB}M
MemoryMax=${MAX_MB}M
MemorySwapMax=2G
OOMPolicy=stop
Restart=no
EOC

systemctl daemon-reload

echo
echo "[noemaforge-llm-memory-override] Applied:"
systemctl cat "$SERVICE" | sed -n '/20-memory-limits.conf/,$p'
