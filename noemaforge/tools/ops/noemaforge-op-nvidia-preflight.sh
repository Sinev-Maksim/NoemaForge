#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/ops/noemaforge-op-nvidia-preflight.sh
# Zone: operator/gui-recovery
# Purpose: Install/status/remove NVIDIA DRM/KMS preflight before display manager.
# Callers: sudo noemaforge nvidia-preflight install|status|restart|remove.
# Safety: Does not install NVIDIA drivers; only creates/removes systemd preflight wiring.
# === End NoemaForge File Header ===
set -euo pipefail

ACTION="${1:-status}"
UNIT=/etc/systemd/system/nvidia-gui-preflight.service
DROPIN_DIR=/etc/systemd/system/display-manager.service.d
DROPIN=${DROPIN_DIR}/10-nvidia-preflight.conf

install_unit() {
  cat > "$UNIT" <<'EOC'
[Unit]
Description=Preload NVIDIA DRM/KMS before display manager
After=local-fs.target systemd-modules-load.service
Before=display-manager.service gdm.service gdm3.service

[Service]
Type=oneshot
ExecStart=/bin/sh -c '/sbin/modprobe nvidia-current 2>/dev/null || /sbin/modprobe nvidia 2>/dev/null || true'
ExecStart=/bin/sh -c '/sbin/modprobe nvidia-current-modeset 2>/dev/null || /sbin/modprobe nvidia_modeset 2>/dev/null || true'
ExecStart=/bin/sh -c '/sbin/modprobe nvidia-current-uvm 2>/dev/null || /sbin/modprobe nvidia_uvm 2>/dev/null || true'
ExecStart=/bin/sh -c '/sbin/modprobe nvidia-current-drm modeset=1 2>/dev/null || /sbin/modprobe nvidia_drm modeset=1 2>/dev/null || true'
ExecStart=/bin/sh -c 'test "$(cat /sys/module/nvidia_drm/parameters/modeset 2>/dev/null)" = Y'
RemainAfterExit=yes

[Install]
WantedBy=graphical.target
EOC

  mkdir -p "$DROPIN_DIR"
  cat > "$DROPIN" <<'EOC'
[Unit]
Wants=nvidia-gui-preflight.service
After=nvidia-gui-preflight.service
EOC

  systemctl daemon-reload
  systemctl enable nvidia-gui-preflight.service
}

case "$ACTION" in
  install)
    echo "[nvidia-preflight] installing systemd preflight unit..."
    install_unit
    echo "[nvidia-preflight] starting preflight once..."
    systemctl restart nvidia-gui-preflight.service || true
    echo "[nvidia-preflight] nvidia_drm modeset:"
    cat /sys/module/nvidia_drm/parameters/modeset 2>/dev/null || echo "nvidia_drm not loaded"
    ;;
  restart)
    systemctl daemon-reload
    systemctl restart nvidia-gui-preflight.service
    cat /sys/module/nvidia_drm/parameters/modeset 2>/dev/null || true
    ;;
  status)
    systemctl status nvidia-gui-preflight.service --no-pager 2>/dev/null || true
    echo
    echo "Unit: $UNIT"
    test -f "$UNIT" && sed -n '1,120p' "$UNIT" || echo "missing"
    echo
    echo "Drop-in: $DROPIN"
    test -f "$DROPIN" && sed -n '1,80p' "$DROPIN" || echo "missing"
    echo
    cat /sys/module/nvidia_drm/parameters/modeset 2>/dev/null || echo "nvidia_drm not loaded"
    ;;
  remove|disable)
    systemctl disable --now nvidia-gui-preflight.service 2>/dev/null || true
    rm -f "$UNIT" "$DROPIN"
    systemctl daemon-reload
    systemctl reset-failed nvidia-gui-preflight.service 2>/dev/null || true
    echo "[nvidia-preflight] removed"
    ;;
  *)
    echo "Usage: sudo noemaforge nvidia-preflight install|status|restart|remove" >&2
    exit 2
    ;;
esac
