#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/ops/noemaforge-op-gui-status.sh
# Zone: operator/gui-diagnostics
# Purpose: Show GUI/NVIDIA state without changing the system.
# Callers: sudo noemaforge gui-status, legacy wrapper gui-status.
# === End NoemaForge File Header ===
set -euo pipefail

echo "===== display manager ====="
systemctl status display-manager.service gdm.service gdm3.service --no-pager 2>/dev/null | sed -n '1,100p' || true

echo
echo "===== NVIDIA modules ====="
lsmod | grep -E '^nvidia' || true

echo
echo "===== NVIDIA DRM ====="
cat /sys/module/nvidia_drm/parameters/modeset 2>/dev/null || echo "nvidia_drm not loaded"

echo
echo "===== GLX ====="
update-alternatives --query glx 2>/dev/null | grep -E '^(Status|Value):' || true

echo
echo "===== NVIDIA-SMI ====="
nvidia-smi 2>&1 | head -40 || true

echo
echo "===== Xorg / GNOME / Firefox / llama GPU users ====="
nvidia-smi 2>/dev/null | grep -E 'Xorg|gnome|firefox|llama' || true

echo
echo "===== failed units ====="
systemctl --failed --no-pager || true
