#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-gui-diagnose.sh
# Zone: release/package
# Version: 0.31.13.alpha-patched1
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Provide NoemaForge release functionality for the packaged local runtime.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
# NoemaForge 0.31.13.alpha-patched1 GUI/NVIDIA/Secure Boot diagnostic surface.
set -euo pipefail
JSON=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) JSON=1; shift ;;
    -h|--help|help|"?") cat <<'USAGE'
Usage:
  noemaforge gui-diagnose [--json]

Checks GUI/GDM/NVIDIA/Secure Boot/MOK/ToolProxy readiness. It does not change state.
USAGE
      exit 0 ;;
    *) echo "[noemaforge-gui-diagnose][ERROR] unknown option: $1" >&2; exit 2 ;;
  esac
done

val(){ local cmd="$1"; bash -lc "$cmd" 2>/dev/null || true; }
SB="$(val 'mokutil --sb-state | head -1')"
KERNEL="$(uname -r)"
GDM_ACTIVE="$(val 'systemctl is-active gdm3.service 2>/dev/null || systemctl is-active gdm.service 2>/dev/null || systemctl is-active display-manager.service 2>/dev/null || true')"
NVIDIA_SMI_OK=0; nvidia-smi >/tmp/noemaforge-gui-diagnose-nvidia-smi.out 2>/tmp/noemaforge-gui-diagnose-nvidia-smi.err && NVIDIA_SMI_OK=1 || true
DRM_MODESET="$(val 'sudo cat /sys/module/nvidia_drm/parameters/modeset 2>/dev/null || cat /sys/module/nvidia_drm/parameters/modeset 2>/dev/null || true')"
SIGNER="$(val 'modinfo -F signer nvidia-current 2>/dev/null || modinfo -F signer nvidia 2>/dev/null || true')"
VERMAGIC="$(val 'modinfo -F vermagic nvidia-current 2>/dev/null || modinfo -F vermagic nvidia 2>/dev/null || true')"
MOK_TEST=""
if [[ -f /var/lib/dkms/mok.pub ]]; then MOK_TEST="$(val 'sudo mokutil --test-key /var/lib/dkms/mok.pub 2>&1 || true')"; fi
TP_ACTIVE="$(val 'systemctl is-active noemaforge-toolproxy.service 2>/dev/null || true')"
PROBLEMS=()
[[ "$SB" == *enabled* && -z "$SIGNER" ]] && PROBLEMS+=("Secure Boot enabled but NVIDIA signer is empty; DKMS/MOK signing may be incomplete")
[[ "$SB" == *enabled* && "$MOK_TEST" == *'not'*'enrolled'* ]] && PROBLEMS+=("DKMS MOK key is not enrolled; run mokutil --import /var/lib/dkms/mok.pub and enroll on reboot")
[[ "$NVIDIA_SMI_OK" != 1 ]] && PROBLEMS+=("nvidia-smi failed; inspect /tmp/noemaforge-gui-diagnose-nvidia-smi.err")
[[ "$DRM_MODESET" != "Y" ]] && PROBLEMS+=("nvidia_drm modeset is not Y")
[[ "$TP_ACTIVE" != "active" ]] && PROBLEMS+=("ToolProxy is not active")
if [[ "$JSON" == 1 ]]; then
  python3 - "$SB" "$KERNEL" "$GDM_ACTIVE" "$NVIDIA_SMI_OK" "$DRM_MODESET" "$SIGNER" "$VERMAGIC" "$TP_ACTIVE" "${PROBLEMS[@]}" <<'PY_JSON_GUI_DIAGNOSE'
import json, sys
sb,kernel,gdm,nvsmi,drm,signer,vermagic,tp,*problems=sys.argv[1:]
print(json.dumps({"ok": not problems, "secure_boot": sb, "kernel": kernel, "display_manager_active": gdm, "nvidia_smi_ok": nvsmi=='1', "nvidia_drm_modeset": drm, "nvidia_module_signer": signer, "nvidia_vermagic": vermagic, "toolproxy_active": tp, "problems": problems}, ensure_ascii=False, indent=2))
PY_JSON_GUI_DIAGNOSE
else
  echo "NoemaForge GUI diagnose"
  echo "  secure boot:        ${SB:-unknown}"
  echo "  kernel:             $KERNEL"
  echo "  display manager:    ${GDM_ACTIVE:-unknown}"
  echo "  nvidia-smi:         $([[ $NVIDIA_SMI_OK == 1 ]] && echo ok || echo fail)"
  echo "  nvidia_drm modeset: ${DRM_MODESET:-unknown}"
  echo "  nvidia signer:      ${SIGNER:-empty}"
  echo "  nvidia vermagic:    ${VERMAGIC:-unknown}"
  echo "  toolproxy:          ${TP_ACTIVE:-unknown}"
  echo
  if ((${#PROBLEMS[@]})); then
    echo "Problems:"
    for p in "${PROBLEMS[@]}"; do echo "  - $p"; done
    exit 1
  fi
  echo "No blocking GUI/NVIDIA/ToolProxy problems detected."
fi
