#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/ops/noemaforge-op-safe-mode.sh
# Zone: operator/recovery
# Purpose: Enter low-pressure NoemaForge safe mode by stopping LLM and heavy browser processes.
# Callers: sudo noemaforge safe-mode, systemd transient jobs, legacy wrapper noemaforge-safe-mode.
# Safety: Does not disable GUI; it may close Firefox.
# === End NoemaForge File Header ===
set -euo pipefail

ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"

echo "[noemaforge-safe-mode] entering safe mode..."

echo "[noemaforge-safe-mode] stopping NoemaForge LLM..."
"$ROOT/tools/ops/noemaforge-op-llm-stop.sh" 2>/dev/null || true

echo "[noemaforge-safe-mode] stopping Firefox..."
pkill -TERM -f '[f]irefox' 2>/dev/null || true
sleep 3
pkill -KILL -f '[f]irefox' 2>/dev/null || true

echo "[noemaforge-safe-mode] resetting failed units..."
systemctl reset-failed || true

echo "[noemaforge-safe-mode] memory after cleanup:"
free -h

echo "[noemaforge-safe-mode] GPU after cleanup:"
nvidia-smi 2>/dev/null | head -30 || true

echo "[noemaforge-safe-mode] failed units:"
systemctl --failed --no-pager || true

echo "[noemaforge-safe-mode] done"
