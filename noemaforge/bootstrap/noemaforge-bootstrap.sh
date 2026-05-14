#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/bootstrap/noemaforge-bootstrap.sh
# Zone: release/package
# Version: 0.31.13.alpha
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Provide NoemaForge release functionality for the packaged local runtime.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
# === NoemaForge Autodoc File Header ===
# File: bootstrap/noemaforge-bootstrap.sh
# Purpose: Provide the script 'noemaforge-bootstrap'.
# Invoked by: shell operators or wrapper scripts.
# Inputs: Positional arguments, environment variables, and files read below.
# Outputs: Console output and filesystem side effects.
# AutoDoc: refreshed 2026-04-09 (heuristic)
# === End NoemaForge Autodoc File Header ===




set -euo pipefail

MODE="mvp"
SEED=""
OFFLINE_APT=""
AUTO_ORIGIN="0"
DUAL_INITRAMFS="0"
DRIVER_VAULT="0"
PROVISION_BCA="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed) SEED="$2"; shift 2;;
    --mode) MODE="$2"; shift 2;;
    --offline-apt) OFFLINE_APT="$2"; shift 2;;
    --auto-origin) AUTO_ORIGIN="1"; shift;;
    --dual-initramfs) DUAL_INITRAMFS="1"; shift;;
    --driver-vault) DRIVER_VAULT="1"; shift;;
    --provision-bca) PROVISION_BCA="1"; shift;;
    *) echo "unknown arg: $1" >&2; exit 1;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

# === NoemaForge Autodoc Function Header ===
# Function: log()
# Purpose: Provide the shell routine 'log'.
# Inputs:
#   - Positional shell arguments and environment variables read in the body below.
# Called by:
#   - The current shell script or sourced callers.
# Outputs: Console output and filesystem/process side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
log(){ echo "[noemaforge-bootstrap] $*"; }

# === NoemaForge Autodoc Function Header ===
# Function: apt_try_install()
# Purpose: Provide the shell routine 'apt_try_install'.
# Inputs:
#   - Positional shell arguments and environment variables read in the body below.
# Called by:
#   - The current shell script or sourced callers.
# Outputs: Console output and filesystem/process side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
apt_try_install() {
  DEBIAN_FRONTEND=noninteractive apt-get update -y >/dev/null 2>&1 || return 0
  DEBIAN_FRONTEND=noninteractive apt-get install -y "$@" >/dev/null 2>&1 || return 0
}

# === NoemaForge Autodoc Function Header ===
# Function: apt_offline_install()
# Purpose: Provide the shell routine 'apt_offline_install'.
# Inputs:
#   - Positional shell arguments and environment variables read in the body below.
# Called by:
#   - The current shell script or sourced callers.
# Outputs: Console output and filesystem/process side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
apt_offline_install() {
  local repo="$1"; shift
  if [[ -z "$repo" ]] || [[ ! -d "$repo" ]]; then
    return 1
  fi
  # Expect Packages.gz or Packages in repo root.
  if [[ ! -f "$repo/Packages.gz" ]] && [[ ! -f "$repo/Packages" ]]; then
    return 1
  fi
  local tmpdir="/tmp/noemaforge-offline-apt"
  rm -rf "$tmpdir" && mkdir -p "$tmpdir"
  echo "deb [trusted=yes] file:${repo} ./" >"$tmpdir/sources.list"
  # Do NOT consult default sources; only use our file: repo.
  DEBIAN_FRONTEND=noninteractive apt-get \
    -o Dir::Etc::sourcelist="$tmpdir/sources.list" \
    -o Dir::Etc::sourceparts="-" \
    -o APT::Get::List-Cleanup="0" \
    update -y >/dev/null 2>&1 || return 1
  DEBIAN_FRONTEND=noninteractive apt-get \
    -o Dir::Etc::sourcelist="$tmpdir/sources.list" \
    -o Dir::Etc::sourceparts="-" \
    install -y --no-install-recommends "$@" >/dev/null 2>&1 || return 1
  return 0
}

log "1) Users + dirs"
id -u noemaforge >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin noemaforge

mkdir -p /opt/noemaforge/{bin,configs,contracts,src,release,bootstrap,templates,tools,docs,datasets}
mkdir -p /var/lib/noemaforge/{sel/segments,forensics,quarantine/incidents,.sys,.sys/.cache/cred,driver-vault/debs,toolvault/manifests,toolvault/artifacts,toolvault/installed/plugins,toolvault/aptrepo,projects,routines,context_spill,roadmaps/exports,boot/reports,boot/onfailure,model_scorecards}
mkdir -p /var/lib/modelstore/{models,artifacts}
mkdir -p /run/noemaforge/llm/{backends}
mkdir -p /workspace
mkdir -p /workspace/inbox/{photos,bank,work,video,3dprint,home,articles}
mkdir -p /workspace/outbox
mkdir -p /workspace/outbox/bootreports
mkdir -p /workspace/outbox/support
mkdir -p /workspace/role-runs

chown -R noemaforge:noemaforge /var/lib/noemaforge /var/lib/modelstore /run/noemaforge /workspace
chmod 0700 /var/lib/noemaforge /var/lib/noemaforge/.sys /var/lib/noemaforge/.sys/.cache /var/lib/noemaforge/.sys/.cache/cred
chmod 0750 /var/lib/noemaforge/sel /var/lib/noemaforge/forensics
chmod 0750 /var/lib/noemaforge/quarantine || true
chmod 0770 /workspace

log "2) Packages (best-effort)"

# Prefer OFFLINE apt repo when available (for "bare" systems without network).
OFFLINE_REPO=""
if [[ -n "$OFFLINE_APT" ]]; then
  OFFLINE_REPO="$OFFLINE_APT"
elif [[ -n "$SEED" ]] && [[ -d "$SEED/offline-apt/aptrepo" ]]; then
  OFFLINE_REPO="$SEED/offline-apt/aptrepo"
elif [[ -L "/var/lib/noemaforge/toolvault/aptrepo/_active" ]]; then
  OFFLINE_REPO="/var/lib/noemaforge/toolvault/aptrepo/_active"
elif [[ -d "/var/lib/noemaforge/toolvault/aptrepo" ]]; then
  OFFLINE_REPO="/var/lib/noemaforge/toolvault/aptrepo"
fi

BASE_PKGS=(jq curl git rsync ca-certificates procps findutils coreutils nftables apparmor apparmor-utils podman uidmap slirp4netns fuse-overlayfs initramfs-tools grub2-common util-linux python3 python3-yaml python3-venv bubblewrap ffmpeg alsa-utils pipewire pipewire-bin pipewire-audio wireplumber v4l-utils golang-go build-essential cmake ntfs-3g)

if [[ -n "$OFFLINE_REPO" ]]; then
  log "Offline apt repo detected: $OFFLINE_REPO"
  if ! apt_offline_install "$OFFLINE_REPO" "${BASE_PKGS[@]}"; then
    log "WARN: offline apt install failed; falling back to apt_try_install (may require network)"
    apt_try_install "${BASE_PKGS[@]}"
  fi
else
  log "WARN: no offline apt repo detected; using apt_try_install (may require network)"
  apt_try_install "${BASE_PKGS[@]}"
fi

log "3) systemd slices"
cat >/etc/systemd/system/noemaforge-core.slice <<'EOF'
[Slice]
MemoryAccounting=yes
CPUAccounting=yes
IOAccounting=yes
TasksAccounting=yes
MemoryHigh=800M
MemoryMax=1200M
CPUWeight=10
IOWeight=50
EOF

cat >/etc/systemd/system/noemaforge-models.slice <<'EOF'
[Slice]
MemoryAccounting=yes
CPUAccounting=yes
IOAccounting=yes
TasksAccounting=yes
CPUWeight=1000
IOWeight=200
EOF

log "4) tmpfiles for /run"
cat >/etc/tmpfiles.d/noemaforge.conf <<'EOF'
d /run/noemaforge 0750 noemaforge noemaforge - -
d /run/noemaforge/llm 0750 noemaforge noemaforge - -
d /run/noemaforge/llm/backends 0750 noemaforge noemaforge - -
# mode marker: runtime by default
f /run/noemaforge/mode 0644 noemaforge noemaforge - runtime
EOF
systemd-tmpfiles --create /etc/tmpfiles.d/noemaforge.conf >/dev/null 2>&1 || true

log "5) Copy seed payload"
if [[ -n "$SEED" ]]; then
  # Copy bootstrap itself for future re-runs without seed
  if [[ -f "$SEED/bootstrap/noemaforge-bootstrap.sh" ]]; then
    cp -f "$SEED/bootstrap/noemaforge-bootstrap.sh" /opt/noemaforge/bootstrap/noemaforge-bootstrap.sh
    chmod 0755 /opt/noemaforge/bootstrap/noemaforge-bootstrap.sh
  fi

  [[ -d "$SEED/bin" ]] && cp -a "$SEED/bin/." /opt/noemaforge/bin/ || true
  [[ -d "$SEED/configs" ]] && cp -a "$SEED/configs/." /opt/noemaforge/configs/ || true
  [[ -d "$SEED/contracts" ]] && cp -a "$SEED/contracts/." /opt/noemaforge/contracts/ || true
  [[ -d "$SEED/release" ]] && cp -a "$SEED/release/." /opt/noemaforge/release/ || true
  [[ -d "$SEED/src" ]] && cp -a "$SEED/src/." /opt/noemaforge/src/ || true
  [[ -d "$SEED/tools" ]] && mkdir -p /opt/noemaforge/tools && cp -a "$SEED/tools/." /opt/noemaforge/tools/ || true
  [[ -d "$SEED/datasets" ]] && mkdir -p /opt/noemaforge/datasets && cp -a "$SEED/datasets/." /opt/noemaforge/datasets/ || true
  [[ -d "$SEED/docs" ]] && mkdir -p /opt/noemaforge/docs && cp -a "$SEED/docs/." /opt/noemaforge/docs/ || true
  [[ -f "$SEED/manifest.yaml" ]] && cp -a "$SEED/manifest.yaml" /opt/noemaforge/manifest.yaml || true

  # Hygiene: do not ship/retain Python bytecode caches from the seed payload.
  find /opt/noemaforge/src -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
  find /opt/noemaforge/src -type f -name "*.pyc" -delete 2>/dev/null || true
  [[ -d "$SEED/templates" ]] && cp -a "$SEED/templates/." /opt/noemaforge/templates/ || true

  # exFAT permissions: ensure scripts executable
  chmod 0755 /opt/noemaforge/src/*.py 2>/dev/null || true
  chmod 0755 /opt/noemaforge/src/*.go 2>/dev/null || true
  chmod 0755 /opt/noemaforge/bin/* 2>/dev/null || true
  chmod 0755 /opt/noemaforge/tools/prep/*.sh 2>/dev/null || true

  if [[ -d "$SEED/driver-vault/debs" ]]; then
    cp -a "$SEED/driver-vault/debs/." /var/lib/noemaforge/driver-vault/debs/ || true
  fi

  # If offline apt repo was provided from seed, copy it into ToolVault for future re-runs.
  if [[ -d "$SEED/offline-apt/aptrepo" ]]; then
    mkdir -p /var/lib/noemaforge/toolvault/aptrepo
    cp -a "$SEED/offline-apt/aptrepo/." /var/lib/noemaforge/toolvault/aptrepo/ || true
  fi

  if [[ -f "$SEED/models/main/model.gguf" ]]; then
    mkdir -p /var/lib/modelstore/models/main
    cp -a "$SEED/models/main/model.gguf" /var/lib/modelstore/models/main/model.gguf
    chown -R noemaforge:noemaforge /var/lib/modelstore/models/main
  fi
fi

log "5b) Host preflight + offline APT validation"
if [[ -x /usr/bin/python3 ]] && [[ -f /opt/noemaforge/bootstrap/noemaforge-host-preflight.py ]]; then
  /usr/bin/python3 /opt/noemaforge/bootstrap/noemaforge-host-preflight.py --seed /opt/noemaforge --out /workspace/outbox/bootreports/host_preflight.json ${OFFLINE_REPO:+--offline-apt "$OFFLINE_REPO"} || true
fi
if [[ -x /usr/bin/python3 ]] && [[ -n "$OFFLINE_REPO" ]] && [[ -f /opt/noemaforge/tools/prep/validate_offline_apt.py ]]; then
  /usr/bin/python3 /opt/noemaforge/tools/prep/validate_offline_apt.py --repo "$OFFLINE_REPO" --driver-vault /var/lib/noemaforge/driver-vault/debs --out /workspace/outbox/bootreports/offline_apt_validation.json || true
fi

log "5c) Build gateway binary if source exists and binary is missing"
if [[ ! -x /opt/noemaforge/bin/noemaforge-llm-gateway ]] && [[ -f /opt/noemaforge/src/noemaforge-llm-gateway.go ]] && command -v go >/dev/null 2>&1; then
  mkdir -p /opt/noemaforge/bin
  if GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /opt/noemaforge/bin/noemaforge-llm-gateway /opt/noemaforge/src/noemaforge-llm-gateway.go; then
    chmod 0755 /opt/noemaforge/bin/noemaforge-llm-gateway
    log "Built /opt/noemaforge/bin/noemaforge-llm-gateway from source"
  else
    log "WARN: could not build noemaforge-llm-gateway from source"
  fi
fi

log "6) Ensure baseline configs exist (if missing)"
test -f /opt/noemaforge/configs/compute-policy.yaml || echo "missing compute-policy.yaml" >&2
test -f /opt/noemaforge/configs/model-policy.yaml || echo "missing model-policy.yaml" >&2
test -f /opt/noemaforge/configs/storage-policy.yaml || echo "missing storage-policy.yaml" >&2
test -f /opt/noemaforge/configs/taskqueue-policy.yaml || echo "missing taskqueue-policy.yaml" >&2

log "7) Auto-origin PTUUID (allow only this disk) if requested"
if [[ "$AUTO_ORIGIN" == "1" ]]; then
  ROOTSRC=$(findmnt -n -o SOURCE /)
  DISK="/dev/$(lsblk -no PKNAME "$ROOTSRC")"
  PTUUID=$(blkid -s PTUUID -o value "$DISK" || true)
  if [[ -n "$PTUUID" ]]; then
    sed -i "s/device_ptuuid: \"SETUP_AUTODETECT\"/device_ptuuid: \"${PTUUID}\"/g" /opt/noemaforge/configs/storage-policy.yaml
    log "Origin disk PTUUID set: $PTUUID (disk $DISK)"
  else
    log "WARN: PTUUID not detected"
  fi
fi

log "8) Initialize Contract Epochs (immutable contracts at runtime)"
python3 - <<'PY'
import sys
sys.path.insert(0, '/opt/noemaforge/src')
from prestart import ensure_epoch_initialized
print('epoch_init:', ensure_epoch_initialized(config_dir='/opt/noemaforge/configs', contracts_root='/var/lib/noemaforge/contracts'))
PY

log "8) Policy lock default LOCKED"
echo "LOCKED" >/var/lib/noemaforge/.sys/policy-lock.state
chmod 0600 /var/lib/noemaforge/.sys/policy-lock.state
chown noemaforge:noemaforge /var/lib/noemaforge/.sys/policy-lock.state


log "10) Dual initramfs dep+most if requested"
if [[ "$DUAL_INITRAMFS" == "1" ]]; then
  KVER="$(uname -r)"
  OUT_DEP="/boot/initrd.img-${KVER}-brain-dep"
  OUT_MOST="/boot/initrd.img-${KVER}-brain-most"

  if command -v mkinitramfs >/dev/null 2>&1; then
    mkinitramfs -m dep  -o "$OUT_DEP"  "$KVER" || true
    mkinitramfs -m most -o "$OUT_MOST" "$KVER" || true
    log "Built initrds: dep=$OUT_DEP most=$OUT_MOST"
  else
    log "WARN: mkinitramfs missing; skip"
  fi
fi

log "11) Driver vault (best-effort)"
if [[ "$DRIVER_VAULT" == "1" ]]; then
  mkdir -p /var/lib/noemaforge/driver-vault/debs
  chown -R noemaforge:noemaforge /var/lib/noemaforge/driver-vault
  log "Driver vault at /var/lib/noemaforge/driver-vault/debs"
fi

log "12) Install systemd units: bootdoctor + onfailure + llama backend + gateway + toolproxy + backends-manager + firstboot-eval + memsentinel"
cat >/etc/systemd/system/noemaforge-bootdoctor.service <<'EOF'
[Unit]
Description=NoemaForge BootDoctor (startup diagnostics)
After=local-fs.target
Before=noemaforge-llm-gateway.service noemaforge-toolproxy.service noemaforge-memsentinel.service
Wants=noemaforge-core.slice
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done

[Service]
Type=oneshot
User=root
Group=root
Slice=noemaforge-core.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/noemaforge /workspace /run/noemaforge

ExecStart=/usr/bin/python3 /opt/noemaforge/src/bootdoctor.py --mode boot

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/noemaforge-onfailure@.service <<'EOF'
[Unit]
Description=NoemaForge OnFailure collector (%i)
After=local-fs.target
Wants=noemaforge-core.slice
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done

[Service]
Type=oneshot
User=root
Group=root
Slice=noemaforge-core.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/noemaforge /workspace /run/noemaforge

ExecStart=/usr/bin/python3 /opt/noemaforge/src/bootdoctor.py --mode onfailure --unit %i

[Install]
WantedBy=multi-user.target
EOF


cat >/etc/systemd/system/noemaforge-llama@.service <<'EOF'
[Unit]
Description=NoemaForge llama-server backend (%i)
After=local-fs.target
Wants=noemaforge-models.slice
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done
OnFailure=noemaforge-onfailure@%n.service

[Service]
User=noemaforge
Group=noemaforge
Slice=noemaforge-models.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/run/noemaforge/llm/backends /var/lib/modelstore
WorkingDirectory=/var/lib/modelstore/models/%i

ExecStart=/opt/noemaforge/bin/noemaforge-llama-start %i /run/noemaforge/llm/backends/%i.sock

Restart=on-failure
RestartSec=2
OOMScoreAdjust=500

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/noemaforge-llm-gateway.service <<'EOF'
[Unit]
Description=NoemaForge LLM Gateway (single entrypoint)
After=local-fs.target
Wants=noemaforge-core.slice
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done
OnFailure=noemaforge-onfailure@%n.service

[Service]
User=noemaforge
Group=noemaforge
Slice=noemaforge-core.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/run/noemaforge/llm

Environment=NOEMAFORGE_GATEWAY_SOCKET=/run/noemaforge/llm/gateway.sock
Environment=NOEMAFORGE_DEFAULT_MODEL=main
Environment=NOEMAFORGE_BACKENDS=main:/run/noemaforge/llm/backends/main.sock
Environment=NOEMAFORGE_MAX_BODY_BYTES=10485760

ExecStart=/opt/noemaforge/bin/noemaforge-llm-gateway

Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/noemaforge-toolproxy.service <<'EOF'
[Unit]
Description=NoemaForge ToolProxy (capability-gated tools/LLM)
After=local-fs.target noemaforge-llm-gateway.service
Wants=noemaforge-core.slice noemaforge-llm-gateway.service
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done
OnFailure=noemaforge-onfailure@%n.service

[Service]
User=noemaforge
Group=noemaforge
Slice=noemaforge-core.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/noemaforge /run/noemaforge
ReadWritePaths=/var/lib/modelstore

ExecStart=/usr/bin/python3 /opt/noemaforge/src/toolproxy.py

Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/noemaforge-modelscan.service <<'EOF'
[Unit]
Description=NoemaForge ModelStore Registry Scan
After=local-fs.target
Wants=noemaforge-core.slice
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done
OnFailure=noemaforge-onfailure@%n.service

[Service]
Type=oneshot
User=noemaforge
Group=noemaforge
Slice=noemaforge-core.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/noemaforge /var/lib/modelstore

ExecStart=/usr/bin/python3 /opt/noemaforge/src/model_registry.py --write
EOF

cat >/etc/systemd/system/noemaforge-modelscan.timer <<'EOF'
[Unit]
Description=NoemaForge ModelScan Timer

[Timer]
OnBootSec=60
OnUnitActiveSec=10m
Persistent=true
Unit=noemaforge-modelscan.service

[Install]
WantedBy=timers.target
EOF

cat >/etc/systemd/system/noemaforge-llm-backends-manager.service <<'EOF'
[Unit]
Description=NoemaForge LLM Backends Manager (reconcile llama-server instances)
After=local-fs.target
Wants=noemaforge-core.slice
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done
OnFailure=noemaforge-onfailure@%n.service

[Service]
Type=oneshot
User=root
Group=root
Slice=noemaforge-core.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/noemaforge /run/noemaforge /var/lib/modelstore

ExecStart=/usr/bin/python3 /opt/noemaforge/src/llm_backends_manager.py --reconcile
EOF

cat >/etc/systemd/system/noemaforge-llm-backends-manager.timer <<'EOF'
[Unit]
Description=NoemaForge LLM Backends Manager Timer

[Timer]
OnBootSec=45
OnUnitActiveSec=3m
Persistent=true
Unit=noemaforge-llm-backends-manager.service

[Install]
WantedBy=timers.target
EOF

cat >/etc/systemd/system/noemaforge-firstboot-eval.service <<'EOF'
[Unit]
Description=NoemaForge FirstBoot Model Staffing
After=local-fs.target noemaforge-llm-gateway.service noemaforge-toolproxy.service
Wants=noemaforge-core.slice noemaforge-llm-gateway.service noemaforge-toolproxy.service
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done
ConditionPathExists=!/var/lib/noemaforge/.sys/firstboot-model-eval.done
OnFailure=noemaforge-onfailure@%n.service

[Service]
Type=oneshot
User=root
Group=root
Slice=noemaforge-core.slice
# Never monopolize the machine.
CPUQuota=95%
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/noemaforge /workspace /var/lib/modelstore /run/noemaforge

ExecStart=/usr/bin/python3 /opt/noemaforge/src/firstboot_eval.py
EOF

cat >/etc/systemd/system/noemaforge-memsentinel.service <<'EOF'
[Unit]
Description=NoemaForge MemSentinel (memory pressure -> critical)
After=local-fs.target
Wants=noemaforge-core.slice
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done
OnFailure=noemaforge-onfailure@%n.service

[Service]
User=root
Group=root
Slice=noemaforge-core.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/noemaforge

ExecStart=/usr/bin/python3 /opt/noemaforge/src/memsentinel.py

Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

log "13) Disable automount best-effort"
systemctl disable --now udisks2.service 2>/dev/null || true

log "14) Mark setup done + reload systemd"
touch /var/lib/noemaforge/.sys/setup.done
chmod 0644 /var/lib/noemaforge/.sys/setup.done
systemctl daemon-reload

log "15) Provision BCA timers (recurring/auditor/dailyplan) if requested"
if [[ "$PROVISION_BCA" == "1" ]]; then
  /usr/bin/python3 /opt/noemaforge/src/brainctl.py provision || true
fi

log "Bootstrap complete."
log "Next:"
log "  - Put model: /var/lib/modelstore/models/main/model.gguf (optional)"
log "  - Start: systemctl enable --now noemaforge-memsentinel noemaforge-llm-gateway noemaforge-toolproxy noemaforge-llama@main noemaforge-llm-backends-manager.timer"
log "  - Preferred first launch: sudo /opt/noemaforge/tools/prep/noemaforge-first-launch.sh --share-root /mnt/noemaforge-share --top-k 2"
log "  - Lower-level first-boot helper: /opt/noemaforge/tools/prep/noemaforge-firstboot-from-share.sh --share-root /mnt/noemaforge-share --vault-root /mnt/noemaforge-share/noemaforge-lab/data/Vault --top-k 2"
log "  - Then validate: /opt/noemaforge/tools/prep/noemaforge-firstboot-smoke.sh"
