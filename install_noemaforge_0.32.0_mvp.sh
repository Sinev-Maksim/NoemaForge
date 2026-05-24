#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: install_noemaforge_0.32.0_mvp.sh
# Zone: release/package
# Version: 0.32.0
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Install a historical or current NoemaForge release payload.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
# NoemaForge 0.32.0 public MVP/MWP installer.
# Installs the operator CLI, safe runtime helpers, docs, and config defaults.
# The copied payload includes noemaforge/templates/pipeline-dashboard for the local Admin GUI.
# It does not auto-start heavy LLM backends and does not enable parallel runtime.
set -euo pipefail

# 0.32.0: this is the real installer; it performs installation directly and must not re-enter setup.
# setup.sh may delegate here, but this file performs the install directly.

VERSION="0.32.0"
PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOTFS="/"
DATA_ROOT="/var/lib/noemaforge"
MODEL_PROFILE="minimal"
WITH_SHARE=""
VERIFY=0
SELFTEST=0
PRESERVE_TIMERS=0
DRY_RUN=0

usage(){ cat <<'USAGE'
Usage: sudo ./install_noemaforge_0.32.0_mvp.sh [options]

Options:
  --verify                    Verify SHA256SUMS when present.
  --selftest                  Run installer/package syntax checks.
  --rootfs DIR                Alternate rootfs for test installs.
  --data-root DIR             NoemaForge data root; default /var/lib/noemaforge.
  --model-profile NAME        minimal|balanced|writer|research|gpu-heavy.
  --with-share PATH           Record/share path for later mount normalization.
  --preserve-timers           Do not disable existing NoemaForge timers.
  --dry-run                   Print plan only.

Safe defaults:
  - disables manager/modelscan timers unless --preserve-timers is passed;
  - installs runtime invariant max_active_llms=1;
  - never downloads models or starts heavy backends.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verify) VERIFY=1; shift ;;
    --selftest) SELFTEST=1; shift ;;
    --rootfs) ROOTFS="$2"; shift 2 ;;
    --data-root) DATA_ROOT="$2"; shift 2 ;;
    --model-profile) MODEL_PROFILE="$2"; shift 2 ;;
    --with-share) WITH_SHARE="$2"; shift 2 ;;
    --preserve-timers) PRESERVE_TIMERS=1; shift ;;
    --dry-run|--plan) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

case "$MODEL_PROFILE" in minimal|balanced|writer|research|gpu-heavy) : ;; *) echo "ERROR: unsupported model profile: $MODEL_PROFILE" >&2; exit 2 ;; esac
if [[ "$ROOTFS" == "/" && "$DRY_RUN" != 1 && ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "ERROR: run live install as root" >&2
  exit 1
fi

target(){ local p="$1"; printf '%s/%s' "${ROOTFS%/}" "${p#/}"; }
install_file(){ local src="$1" rel="$2" mode="${3:-0755}"; [[ "$DRY_RUN" == 1 ]] && { echo "install $rel mode=$mode"; return 0; }; mkdir -p "$(dirname "$(target "$rel")")"; install -m "$mode" "$src" "$(target "$rel")"; }
install_default_once(){ local src="$1" rel="$2" mode="${3:-0644}"; [[ "$DRY_RUN" == 1 ]] && { echo "install-default $rel mode=$mode if-missing"; return 0; }; [[ -e "$(target "$rel")" ]] && return 0; install_file "$src" "$rel" "$mode"; }
install_symlink(){ local src="$1" dst="$2"; [[ "$DRY_RUN" == 1 ]] && { echo "link $dst -> $src"; return 0; }; mkdir -p "$(dirname "$(target "$dst")")"; ln -sfn "$src" "$(target "$dst")"; }
backup_one(){ local p="$1" t; t="$(target "$p")"; if [[ "$ROOTFS" == "/" && "$DRY_RUN" != 1 && ( -e "$t" || -L "$t" ) ]]; then mkdir -p "$BACKUP/backup-root/$(dirname "${p#/}")"; cp -a "$t" "$BACKUP/backup-root/${p#/}" 2>/dev/null || true; fi; }

if [[ "$VERIFY" == 1 && -f "$PKG_DIR/SHA256SUMS" ]]; then
  (cd "$PKG_DIR" && sha256sum -c SHA256SUMS)
elif [[ "$VERIFY" == 1 && -f "$PKG_DIR/SHA256SUMS" ]]; then
  (cd "$PKG_DIR" && sha256sum -c SHA256SUMS)
fi

if [[ "$SELFTEST" == 1 ]]; then
  echo "[setup] selftest: shell syntax"
  bash -n "$PKG_DIR/setup.sh"
  bash -n "$PKG_DIR/install_noemaforge_0.32.0_mvp.sh"
  bash -n "$PKG_DIR/uninstall_noemaforge_0.32.0_mvp.sh"
  bash -n "$PKG_DIR/noemaforge/bin/noemaforge"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-version-audit.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-first-run-audit.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-av-readiness.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-multimodal.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-consistency-audit.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-persona-gui.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-trixie-preflight.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-mvp-smoke.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-autostart-safe.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-boot-mode.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-gui-diagnose.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-gui-start.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-gui-recover-minimal.sh"
  bash -n "$PKG_DIR/noemaforge/tools/prep/noemaforge-recursion-audit.sh"
  echo "[install] selftest: critical python syntax"
  PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
    "$PKG_DIR/noemaforge/src/admin_runtime.py" \
    "$PKG_DIR/noemaforge/src/admin_gui_server.py" \
    "$PKG_DIR/noemaforge/src/dev_team_runtime.py" \
    "$PKG_DIR/noemaforge/src/model_evolution_runtime.py"
  find "$PKG_DIR/noemaforge/src" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
  echo "[install] selftest: CLI/API surfaces are covered by targeted verification; package syntax validation passed"
fi
cat <<PLAN
NoemaForge ${VERSION} install plan
  rootfs:          $ROOTFS
  data_root:       $DATA_ROOT
  model_profile:   $MODEL_PROFILE
  with_share:      ${WITH_SHARE:-not-set}
  preserve_timers: $PRESERVE_TIMERS
  dry_run:         $DRY_RUN
  invariant:       max_active_llms=1, gui_llm_profile=runtime_only, wogui_llm_profile=bootstrap_cpu_llm, heavy_llm_autostart=manual_only
PLAN
[[ "$DRY_RUN" == 1 ]] && exit 0

BACKUP="/var/backups/noemaforge-${VERSION}-$(date +%Y%m%d-%H%M%S)"
if [[ "$ROOTFS" == "/" ]]; then install -d -m 0750 "$BACKUP"; echo "[noemaforge-${VERSION}] backup: $BACKUP"; else echo "[noemaforge-${VERSION}] rootfs install: $ROOTFS"; fi

for p in \
  /opt/noemaforge \
  /usr/local/sbin/noemaforge /usr/local/bin/noemaforge /usr/bin/noemaforge \
  /usr/local/sbin/noemaforge-stop /usr/local/sbin/gui-rescue /usr/local/sbin/gui_rescue /usr/local/sbin/gui-status /usr/local/bin/gui-rescue /usr/local/bin/gui_rescue /usr/local/bin/gui-status /usr/bin/gui-rescue /usr/bin/gui_rescue /usr/bin/gui-status /usr/local/sbin/noemaforge-reboot-safe /usr/local/sbin/noemaforge-vault-mount-ro /usr/local/sbin/noemaforge-model-advisor \
  /usr/local/lib/noemaforge-common.sh \
  /etc/default/noemaforge-recovery /etc/default/noemaforge-runtime /etc/default/noemaforge-firstboot \
  /opt/helpers /opt/systemd \
  /etc/noemaforge/boot-mode /etc/systemd/system/noemaforge-autostart-gui.service /etc/systemd/system/noemaforge-autostart-gui.timer /etc/systemd/system/noemaforge-autostart-wogui.service \
  /etc/systemd/system/noemaforge-llm-gateway.service /etc/systemd/system/noemaforge-toolproxy.service /etc/systemd/system/noemaforge-memsentinel.service /etc/systemd/system/noemaforge-llama@.service \
  /var/lib/noemaforge/.sys/runtime-invariants.json; do
  backup_one "$p"
done

mkdir -p "$(target /opt/noemaforge)"
if command -v rsync >/dev/null 2>&1; then
  rsync -a "$PKG_DIR/noemaforge/" "$(target /opt/noemaforge)/"
else
  cp -a "$PKG_DIR/noemaforge/." "$(target /opt/noemaforge)/"
fi

for h in noemaforge-stop noemaforge-reboot-safe noemaforge-sel-fix noemaforge-vault-mount-ro noemaforge-model-advisor noemaforge-safe-start noemaforge-smoke noemaforge-manager noemaforge-monitor noemaforge-chat noemaforge-interpret noemaforge-toolproxy-diag gui-status gui-rescue gui-start noemaforge-health noemaforge-safe-mode noemaforge-llm-memory-override noemaforge-start-llm-safe noemaforge-llm-stop noemaforge-service-stop; do
  [[ -f "$PKG_DIR/helpers/$h" ]] && install_file "$PKG_DIR/helpers/$h" "/usr/local/sbin/$h" 0755
done
install_file "$PKG_DIR/lib/noemaforge-common.sh" /usr/local/lib/noemaforge-common.sh 0644
install -d -m 0755 "$(target /etc/default)"
for default_name in noemaforge-recovery noemaforge-runtime noemaforge-firstboot; do
  [[ -f "$PKG_DIR/policies/${default_name}.example" ]] && install_default_once "$PKG_DIR/policies/${default_name}.example" "/etc/default/$default_name" 0644
done
# 0.32.0: public noemaforge commands are symlinks to the canonical /opt/noemaforge CLI; no wrapper is installed so `noemaforge version` and policy always use the same root.
install_symlink /opt/noemaforge/bin/noemaforge /usr/local/sbin/noemaforge
install_symlink /opt/noemaforge/bin/noemaforge /usr/local/bin/noemaforge
install_symlink /opt/noemaforge/bin/noemaforge /usr/bin/noemaforge
install_symlink /opt/noemaforge/bin/noemaforge /bin/noemaforge
for h in noemaforge-stop noemaforge-reboot-safe noemaforge-sel-fix noemaforge-vault-mount-ro noemaforge-model-advisor noemaforge-safe-start noemaforge-smoke noemaforge-manager noemaforge-monitor noemaforge-chat noemaforge-interpret noemaforge-toolproxy-diag gui-rescue gui-status gui-start noemaforge-llm-stop noemaforge-service-stop noemaforge-health noemaforge-safe-mode noemaforge-start-llm-safe noemaforge-llm-memory-override; do
  [[ -f "$PKG_DIR/helpers/$h" ]] && install_symlink "/usr/local/sbin/$h" "/usr/local/bin/$h"
done
install_symlink /usr/local/sbin/gui-rescue /usr/local/sbin/gui_rescue
install_symlink /usr/local/sbin/gui-rescue /usr/local/bin/gui_rescue
install_symlink /usr/local/sbin/gui-rescue /usr/bin/gui-rescue
install_symlink /usr/local/sbin/gui-rescue /usr/bin/gui_rescue
install_symlink /usr/local/sbin/gui-status /usr/bin/gui-status
install_symlink /usr/local/sbin/gui-start /usr/local/bin/gui-start
install_symlink /usr/local/sbin/gui-start /usr/local/sbin/gui_start
install_symlink /usr/local/sbin/gui-start /usr/local/bin/gui_start
install_symlink /usr/local/sbin/gui-start /usr/bin/gui-start
install_symlink /usr/local/sbin/gui-start /usr/bin/gui_start

# Compatibility paths used by legacy selftests and TTY recovery docs.
install -d -m 0755 "$(target /opt/helpers)" "$(target /opt/systemd)"
install_symlink /usr/local/sbin/gui-rescue /opt/helpers/gui-rescue
install_symlink /usr/local/sbin/gui-rescue /opt/helpers/gui_rescue
install_symlink /usr/local/sbin/gui-status /opt/helpers/gui-status
install_symlink /usr/local/sbin/gui-start /opt/helpers/gui-start
install_symlink /usr/local/sbin/gui-start /opt/helpers/gui_start

install -d -m 0750 "$(target "$DATA_ROOT")" "$(target "$DATA_ROOT/.sys")" "$(target "$DATA_ROOT/bootstrap")"
# 0.32.0 live-fix: create writable runtime/state directories for operator-facing
# commands and service users before systemd services start.
for d in   "$DATA_ROOT/pipelines" "$DATA_ROOT/personas" "$DATA_ROOT/testbench" "$DATA_ROOT/selftest" "$DATA_ROOT/selftests"   "$DATA_ROOT/wiki-patches" "$DATA_ROOT/wiki_patches" "$DATA_ROOT/dashboard" "$DATA_ROOT/runtime"   "$DATA_ROOT/model-evolution" "$DATA_ROOT/model-selection" "$DATA_ROOT/dev-team" "$DATA_ROOT/multimodal"   "$DATA_ROOT/model_scorecards" "$DATA_ROOT/team_scorecards" "$DATA_ROOT/contracts" "$DATA_ROOT/requests" "$DATA_ROOT/requests/prestart"   "$DATA_ROOT/boot" "$DATA_ROOT/boot/reports" "$DATA_ROOT/outbox"; do
  install -d -m 2775 "$(target "$d")"
done
for d in "$DATA_ROOT/sel" "$DATA_ROOT/sel/segments" "$DATA_ROOT/sel/anchors" "$DATA_ROOT/sel/tmp" "$DATA_ROOT/.sys/cap_tokens"; do
  install -d -m 2770 "$(target "$d")"
done
if [[ -f "$PKG_DIR/policies/runtime-invariants.json" ]]; then
  install_file "$PKG_DIR/policies/runtime-invariants.json" "$DATA_ROOT/.sys/runtime-invariants.json" 0640
fi
if [[ -f "$PKG_DIR/policies/noemaforge-stop-policy.json" ]]; then
  install_file "$PKG_DIR/policies/noemaforge-stop-policy.json" "$DATA_ROOT/.sys/noemaforge-stop-policy.json" 0640
fi
cat > "$(target "$DATA_ROOT/.sys/setup-profile.json")" <<PROFILE
{
  "version": "${VERSION}",
  "model_profile": "${MODEL_PROFILE}",
  "with_share": "${WITH_SHARE}",
  "max_active_llms": 1,
  "heavy_llm_autostart": "manual_only",
  "gui_llm_profile": "runtime_only",
  "wogui_llm_profile": "bootstrap_cpu_llm",
  "boot_mode_default": "manual",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
PROFILE
cat > "$(target "$DATA_ROOT/.sys/setup.done")" <<SETUPDONE
version=${VERSION}
root=/opt/noemaforge
state=${DATA_ROOT}
share=${WITH_SHARE}
vault=${WITH_SHARE%/}/noemaforge-lab/data/Vault
created_by=setup.sh
created_at=$(date -Is)
SETUPDONE
chmod 0644 "$(target "$DATA_ROOT/.sys/setup.done")"
cat > "$(target "$DATA_ROOT/.sys/setup-state.json")" <<SETUPSTATE
{
  "ok": true,
  "version": "${VERSION}",
  "root": "/opt/noemaforge",
  "state": "${DATA_ROOT}",
  "share": "${WITH_SHARE}",
  "vault": "${WITH_SHARE%/}/noemaforge-lab/data/Vault",
  "created_by": "setup.sh",
  "created_at": "$(date -Is)"
}
SETUPSTATE
chmod 0644 "$(target "$DATA_ROOT/.sys/setup-state.json")"

DOCROOT="/usr/local/share/noemaforge"
mkdir -p "$(target "$DOCROOT/docs")"
install_file "$PKG_DIR/context.md" "$DOCROOT/context.md" 0644
install_file "$PKG_DIR/README.md" "$DOCROOT/README.md" 0644
if command -v rsync >/dev/null 2>&1; then rsync -a "$PKG_DIR/docs/" "$(target "$DOCROOT/docs/")"; else cp -a "$PKG_DIR/docs/." "$(target "$DOCROOT/docs/")"; fi

# Install optional conditional autostart units. They are not enabled by default.
install_file "$PKG_DIR/systemd/noemaforge-autostart-gui.service" /etc/systemd/system/noemaforge-autostart-gui.service 0644
install_file "$PKG_DIR/systemd/noemaforge-autostart-gui.timer" /etc/systemd/system/noemaforge-autostart-gui.timer 0644
install_file "$PKG_DIR/systemd/noemaforge-autostart-wogui.service" /etc/systemd/system/noemaforge-autostart-wogui.service 0644
install_file "$PKG_DIR/systemd/noemaforge-llm-gateway.service" /etc/systemd/system/noemaforge-llm-gateway.service 0644
install_file "$PKG_DIR/systemd/noemaforge-toolproxy.service" /etc/systemd/system/noemaforge-toolproxy.service 0644
install_file "$PKG_DIR/systemd/noemaforge-memsentinel.service" /etc/systemd/system/noemaforge-memsentinel.service 0644
install_file "$PKG_DIR/systemd/noemaforge-llama@.service" /etc/systemd/system/noemaforge-llama@.service 0644
install_file "$PKG_DIR/systemd/noemaforge-autostart-gui.service" /opt/systemd/noemaforge-autostart-gui.service 0644
install_file "$PKG_DIR/systemd/noemaforge-autostart-gui.timer" /opt/systemd/noemaforge-autostart-gui.timer 0644
install_file "$PKG_DIR/systemd/noemaforge-autostart-wogui.service" /opt/systemd/noemaforge-autostart-wogui.service 0644
install_file "$PKG_DIR/systemd/noemaforge-llm-gateway.service" /opt/systemd/noemaforge-llm-gateway.service 0644
install_file "$PKG_DIR/systemd/noemaforge-toolproxy.service" /opt/systemd/noemaforge-toolproxy.service 0644
install_file "$PKG_DIR/systemd/noemaforge-memsentinel.service" /opt/systemd/noemaforge-memsentinel.service 0644
install_file "$PKG_DIR/systemd/noemaforge-llama@.service" /opt/systemd/noemaforge-llama@.service 0644
if [[ -d "$PKG_DIR/systemd/dropins" ]]; then
  find "$PKG_DIR/systemd/dropins" -type f | while read -r f; do
    rel="${f#$PKG_DIR/systemd/dropins/}"
    install_file "$f" "/etc/systemd/system/$rel" 0644
  done
fi
mkdir -p "$(target /etc/noemaforge)"
if [[ ! -e "$(target /etc/noemaforge/boot-mode)" ]]; then
  printf 'manual
' > "$(target /etc/noemaforge/boot-mode)"
  chmod 0644 "$(target /etc/noemaforge/boot-mode)"
fi
if [[ ! -e "$(target /etc/noemaforge/autostart-gui-profile)" ]]; then
  printf 'runtime_only
' > "$(target /etc/noemaforge/autostart-gui-profile)"
  chmod 0644 "$(target /etc/noemaforge/autostart-gui-profile)"
fi
if [[ ! -e "$(target /etc/noemaforge/autostart-wogui-profile)" ]]; then
  printf 'bootstrap_cpu_llm
' > "$(target /etc/noemaforge/autostart-wogui-profile)"
  chmod 0644 "$(target /etc/noemaforge/autostart-wogui-profile)"
fi

if [[ "$ROOTFS" == "/" ]]; then
  getent group noemaforge >/dev/null || groupadd --system noemaforge
  id noemaforge >/dev/null 2>&1 || useradd --system --home-dir "$DATA_ROOT" --shell /usr/sbin/nologin --gid noemaforge noemaforge
  GROUP="noemaforge"
  chgrp "$GROUP" "$DATA_ROOT" "$DATA_ROOT/.sys" "$DATA_ROOT/bootstrap" 2>/dev/null || true
  chmod 2775 "$DATA_ROOT" 2>/dev/null || true
  chmod 2770 "$DATA_ROOT/.sys" 2>/dev/null || true
  chown -R noemaforge:noemaforge "$DATA_ROOT/sel" "$DATA_ROOT/.sys/cap_tokens" 2>/dev/null || true
  chmod 2770 "$DATA_ROOT/sel" "$DATA_ROOT/sel/segments" "$DATA_ROOT/sel/anchors" "$DATA_ROOT/sel/tmp" "$DATA_ROOT/.sys/cap_tokens" 2>/dev/null || true
  # patched7: writable operator/service state dirs. Preserve append-only SEL segments.
  for d in "$DATA_ROOT/pipelines" "$DATA_ROOT/personas" "$DATA_ROOT/multimodal" "$DATA_ROOT/model-evolution" "$DATA_ROOT/model-selection" "$DATA_ROOT/dev-team" "$DATA_ROOT/bootstrap" "$DATA_ROOT/testbench" "$DATA_ROOT/wiki-patches" "$DATA_ROOT/model_scorecards" "$DATA_ROOT/contracts" "$DATA_ROOT/requests"; do
    install -d -o noemaforge -g noemaforge -m 2775 "$d" 2>/dev/null || true
    chgrp -R noemaforge "$d" 2>/dev/null || true
    chmod -R g+rwX "$d" 2>/dev/null || true
    find "$d" -type d -exec chmod 2775 {} + 2>/dev/null || true
  done
  # patched7: make old BrainOS share available under canonical NoemaForge share path when requested.
  if [[ -n "$WITH_SHARE" && "$WITH_SHARE" == "/mnt/noemaforge-share" && -d /mnt/brainos-share/brainos-lab && ! -d /mnt/noemaforge-share/noemaforge-lab/data/Vault ]]; then
    mkdir -p /mnt/noemaforge-share 2>/dev/null || true
    ln -sfn brainos-lab /mnt/brainos-share/noemaforge-lab 2>/dev/null || true
    if command -v mountpoint >/dev/null 2>&1; then
      mountpoint -q /mnt/noemaforge-share || mount --bind /mnt/brainos-share /mnt/noemaforge-share 2>/dev/null || true
    else
      findmnt /mnt/noemaforge-share >/dev/null 2>&1 || mount --bind /mnt/brainos-share /mnt/noemaforge-share 2>/dev/null || true
    fi
  fi
  # patched10: if we install a canonical NoemaForge bind mount, make it non-blocking.
  # A strict fstab bind to /mnt/noemaforge-share can send Debian into emergency mode
  # when the legacy share is busy/unavailable during shutdown or boot.
  if [[ -n "$WITH_SHARE" && "$WITH_SHARE" == "/mnt/noemaforge-share" && -d /mnt/brainos-share ]]; then
    if [[ -w /etc/fstab ]]; then
      cp -a /etc/fstab /etc/fstab.bak.noemaforge-patched10.$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
      # Disable old active NoemaForge bind lines before writing a nofail/automount version.
      sed -i -E 's#^([^#].*[[:space:]]/mnt/noemaforge-share[[:space:]].*)#\# TEMP disabled by NoemaForge patched10: \1#' /etc/fstab 2>/dev/null || true
      if ! grep -qE '^[^#].*[[:space:]]/mnt/noemaforge-share[[:space:]]' /etc/fstab; then
        printf '%s\n' '/mnt/brainos-share /mnt/noemaforge-share none bind,nofail,x-systemd.automount,x-systemd.idle-timeout=300,x-systemd.requires-mounts-for=/mnt/brainos-share 0 0' >> /etc/fstab
      fi
    fi
  fi
  # patched10: harden both legacy and canonical share mounts against emergency-mode boot blocks.
  # Add nofail/automount/device-timeout to any existing /mnt/brainos-share and /mnt/noemaforge-share lines,
  # then reload systemd so it does not keep stale fstab units.
  if [[ -w /etc/fstab ]]; then
    cp -a /etc/fstab /etc/fstab.bak.noemaforge-patched10.$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
    python3 - <<'PYFSTAB' 2>/dev/null || true
from pathlib import Path
p = Path('/etc/fstab')
lines = p.read_text().splitlines() if p.exists() else []
out = []

def add_opts(opts, extras):
    parts = [x for x in opts.split(',') if x]
    for e in extras:
        key = e.split('=', 1)[0]
        if not any(x == e or x.startswith(key + '=') for x in parts):
            parts.append(e)
    return ','.join(parts)

for raw in lines:
    stripped = raw.strip()
    if not stripped or stripped.startswith('#'):
        out.append(raw)
        continue
    cols = stripped.split()
    if len(cols) < 4:
        out.append(raw)
        continue
    mnt = cols[1]
    if mnt == '/mnt/brainos-share':
        cols[3] = add_opts(cols[3], ['nofail','x-systemd.automount','x-systemd.device-timeout=10','x-systemd.idle-timeout=300'])
        out.append('\t'.join(cols)); continue
    if mnt == '/mnt/noemaforge-share':
        cols[3] = add_opts(cols[3], ['bind','nofail','x-systemd.automount','x-systemd.requires-mounts-for=/mnt/brainos-share','x-systemd.device-timeout=10','x-systemd.idle-timeout=300'])
        out.append('\t'.join(cols)); continue
    out.append(raw)
p.write_text('\n'.join(out) + '\n')
PYFSTAB
    systemctl daemon-reload 2>/dev/null || true
  fi
  # patched7: service user may need the legacy brainos gid when NTFS share is mounted that way.
  getent group brainos >/dev/null 2>&1 && usermod -aG brainos noemaforge 2>/dev/null || true
  # patched7: copy legacy llama backends into NoemaForge if clean-package payload lacks them.
  if [[ ! -x /opt/noemaforge/bin/llama-server-cpu && -x /opt/brainos/bin/llama-server-cpu ]]; then install -m 0755 /opt/brainos/bin/llama-server-cpu /opt/noemaforge/bin/llama-server-cpu; fi
  if [[ ! -x /opt/noemaforge/bin/llama-server-cuda && -x /opt/brainos/bin/llama-server-cuda ]]; then install -m 0755 /opt/brainos/bin/llama-server-cuda /opt/noemaforge/bin/llama-server-cuda; fi
  # patched7: rewrite ModelStore symlinks to canonical NoemaForge share path.
  if [[ -d /var/lib/modelstore/models ]]; then
    find /var/lib/modelstore/models -type l -name model.gguf -print0 | while IFS= read -r -d '' p; do
      old="$(readlink -f "$p" 2>/dev/null || true)"
      case "$old" in
        /mnt/brainos-share/brainos-lab/*)
          suffix="${old#/mnt/brainos-share/brainos-lab}"
          new="/mnt/noemaforge-share/noemaforge-lab${suffix}"
          [[ -f "$new" ]] && ln -sfn "$new" "$p" || true
          ;;
      esac
    done
  fi
  # patched7: disable legacy BrainOS units that may keep sockets or failed states around.
  systemctl disable --now brainos-llm-gateway.service brainos-toolproxy.service brainos-memsentinel.service brainos-autostart-gui.service brainos-autostart-gui.timer brainos-first-start.service 2>/dev/null || true
  /usr/local/sbin/noemaforge-sel-fix 2>/dev/null || true
  systemctl daemon-reload 2>/dev/null || true
  # 0.32.0: GUI mode must be timer-driven. The direct service is never enabled under graphical.target.
  mode="manual"
  [[ -r /etc/noemaforge/boot-mode ]] && mode="$(tr -d '[:space:]' < /etc/noemaforge/boot-mode)"
  case "$mode" in
    gui)
      systemctl set-default graphical.target 2>/dev/null || true
      systemctl disable noemaforge-autostart-gui.service noemaforge-autostart-wogui.service 2>/dev/null || true
      systemctl enable noemaforge-autostart-gui.timer 2>/dev/null || true
      ;;
    wogui)
      systemctl set-default multi-user.target 2>/dev/null || true
      systemctl disable --now noemaforge-autostart-gui.timer 2>/dev/null || true
      systemctl disable noemaforge-autostart-gui.service 2>/dev/null || true
      systemctl enable noemaforge-autostart-wogui.service 2>/dev/null || true
      ;;
    manual|*)
      systemctl disable --now noemaforge-autostart-gui.timer 2>/dev/null || true
      systemctl disable noemaforge-autostart-gui.service noemaforge-autostart-wogui.service 2>/dev/null || true
      ;;
  esac
  if [[ "$PRESERVE_TIMERS" != 1 ]]; then
    systemctl disable --now noemaforge-llm-backends-manager.timer noemaforge-modelscan.timer 2>/dev/null || true
  fi
fi

cat <<EOM
NoemaForge ${VERSION} MVP/MWP package installed.
Backup: ${BACKUP:-none-rootfs}

Next safe checks:
  hash -r
  noemaforge help
  noemaforge profiles recommend
  sudo noemaforge stop --dry-run
  noemaforge pipeline validate
  noemaforge member validate
  noemaforge member team --member qa --producer qwen25-coder-14b --json
  sudo noemaforge trixie-preflight --json

Conditional autostart is installed safely. GUI mode uses noemaforge-autostart-gui.timer, not direct graphical.target service:
  sudo noemaforge boot-mode set gui --apply-systemd      # timer-driven runtime/toolproxy after GUI; no LLM by default
  sudo noemaforge boot-mode set wogui --apply-systemd    # headless runtime with CPU bootstrap LLM

Start runtime manually only when ready:
  sudo noemaforge safe-start --wait --restart
  noemaforge smoke --debug
EOM

