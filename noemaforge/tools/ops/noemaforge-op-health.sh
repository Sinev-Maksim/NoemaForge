#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/ops/noemaforge-op-health.sh
# Zone: operator/diagnostics
# Purpose: Aggregated host, GPU, GUI and NoemaForge LLM health view.
# Callers: sudo noemaforge health, legacy wrapper noemaforge-health.
# === End NoemaForge File Header ===
set -euo pipefail

echo "===== HOST ====="
hostnamectl 2>/dev/null || true
echo

echo "===== MEMORY ====="
free -h
echo

echo "===== SWAP ====="
swapon --show || true
echo

echo "===== NVIDIA ====="
nvidia-smi 2>&1 | head -40 || true
echo

echo "===== NVIDIA DRM ====="
cat /sys/module/nvidia_drm/parameters/modeset 2>/dev/null || echo "nvidia_drm not loaded"
echo

echo "===== GLX ====="
update-alternatives --query glx 2>/dev/null | grep -E '^(Status|Value):' || true
echo

echo "===== DISPLAY MANAGER ====="
systemctl status display-manager.service gdm.service gdm3.service --no-pager 2>/dev/null | sed -n '1,80p' || true
echo

echo "===== NOEMAFORGE LLM ====="
systemctl is-active noemaforge-llama@main.service 2>/dev/null || true
systemctl is-enabled noemaforge-llama@main.service 2>/dev/null || true
pgrep -a -f '[l]lama-server' || echo "no llama-server"
echo

echo "===== NOEMAFORGE TIMERS ====="
systemctl is-enabled noemaforge-modelscan.timer 2>/dev/null || true
systemctl is-enabled noemaforge-llm-backends-manager.timer 2>/dev/null || true
systemctl list-timers --all | grep -E 'noemaforge|llm|modelscan' || true
echo

echo "===== MODELSTORE ====="
find /var/lib/modelstore/models -maxdepth 2 -type f -o -type l 2>/dev/null | sed -n '1,80p' || true
echo

echo "===== FAILED UNITS ====="
systemctl --failed --no-pager || true
