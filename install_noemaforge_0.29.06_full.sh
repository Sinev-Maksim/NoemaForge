#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: install_noemaforge_0.29.06_full.sh
# Zone: release/package
# Version: 0.31.13.alpha-patched1
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Install a historical or current NoemaForge release payload.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
set -euo pipefail

VERSION="0.29.06"
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "ERROR: run as root: sudo ./install_noemaforge_0.29.06_full.sh" >&2
  exit 1
fi

PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
BACKUP="/var/backups/noemaforge-${VERSION}-full-$(date +%Y%m%d-%H%M%S)"
GROUP="$(getent group noemaforge >/dev/null && echo noemaforge || echo root)"

backup_one(){
  local f="$1"
  if [[ -e "$f" || -L "$f" ]]; then
    mkdir -p "$BACKUP/$(dirname "${f#/}")"
    cp -a "$f" "$BACKUP/${f#/}" 2>/dev/null || true
  fi
}

echo "[noemaforge-${VERSION}] backup: $BACKUP"
install -d -m 0750 "$BACKUP"
[[ -d "$ROOT" ]] && cp -a "$ROOT" "$BACKUP/noemaforge.old" 2>/dev/null || true
for f in \
  /usr/local/sbin/noemaforge \
  /usr/local/bin/noemaforge \
  /usr/bin/noemaforge \
  /usr/local/sbin/noemaforge-stop \
  /usr/local/sbin/noemaforge-reboot-safe \
  /usr/local/sbin/noemaforge-sel-fix \
  /usr/local/sbin/noemaforge-vault-mount-ro \
  /usr/local/sbin/noemaforge-model-advisor \
  /etc/systemd/system/noemaforge-shutdown-stop.service \
  /etc/systemd/system/noemaforge-toolproxy.service.d/05-sel-perms.conf \
  /etc/systemd/system/noemaforge-llama@.service.d/40-socket-perms.conf \
  /var/lib/noemaforge/.sys/noemaforge-stop-policy.json \
  /var/lib/noemaforge/.sys/runtime-invariants.json
 do
  backup_one "$f"
done

# Verify package checksums before applying if present.
if [[ -f "$PKG_DIR/SHA256SUMS" ]] && command -v sha256sum >/dev/null 2>&1; then
  (cd "$PKG_DIR" && sha256sum -c SHA256SUMS)
fi

install -d -m 0755 "$ROOT"
rsync -a --delete "$PKG_DIR/noemaforge/" "$ROOT/"

chmod 0755 "$ROOT/bin/noemaforge" "$ROOT/bin/noemaforge-llama-start" "$ROOT/tools/ops/"*.sh "$ROOT/tools/prep/"*.sh "$ROOT/src/"*.py 2>/dev/null || true

install -D -m 0755 "$ROOT/bin/noemaforge" /usr/local/sbin/noemaforge
ln -sfn /usr/local/sbin/noemaforge /usr/local/bin/noemaforge
ln -sfn /usr/local/sbin/noemaforge /usr/bin/noemaforge

install -D -m 0755 "$PKG_DIR/helpers/noemaforge-stop" /usr/local/sbin/noemaforge-stop
install -D -m 0755 "$PKG_DIR/helpers/noemaforge-reboot-safe" /usr/local/sbin/noemaforge-reboot-safe
install -D -m 0755 "$PKG_DIR/helpers/noemaforge-sel-fix" /usr/local/sbin/noemaforge-sel-fix
install -D -m 0755 "$PKG_DIR/helpers/noemaforge-vault-mount-ro" /usr/local/sbin/noemaforge-vault-mount-ro
install -D -m 0755 "$PKG_DIR/helpers/noemaforge-model-advisor" /usr/local/sbin/noemaforge-model-advisor
ln -sfn /usr/local/sbin/noemaforge-stop /usr/local/bin/noemaforge-stop
ln -sfn /usr/local/sbin/noemaforge-model-advisor /usr/local/bin/noemaforge-model-advisor

install -D -m 0644 "$PKG_DIR/systemd/noemaforge-shutdown-stop.service" /etc/systemd/system/noemaforge-shutdown-stop.service
install -d -m 0755 /etc/systemd/system/noemaforge-toolproxy.service.d /etc/systemd/system/noemaforge-llama@.service.d
install -m 0644 "$PKG_DIR/systemd/dropins/noemaforge-toolproxy.service.d/05-sel-perms.conf" /etc/systemd/system/noemaforge-toolproxy.service.d/05-sel-perms.conf
install -m 0644 "$PKG_DIR/systemd/dropins/noemaforge-llama@.service.d/40-socket-perms.conf" /etc/systemd/system/noemaforge-llama@.service.d/40-socket-perms.conf

install -d -m 0755 /usr/local/share/noemaforge
install -m 0644 "$PKG_DIR/context.md" /usr/local/share/noemaforge/context.md
install -m 0644 "$PKG_DIR/README.md" /usr/local/share/noemaforge/README-0.29.06.md
install -m 0644 "$PKG_DIR/RELEASE_NOTES.md" /usr/local/share/noemaforge/RELEASE_NOTES-0.29.06.md
install -d -m 0755 /usr/local/share/noemaforge/docs
rsync -a "$PKG_DIR/docs/" /usr/local/share/noemaforge/docs/

install -d -o root -g "$GROUP" -m 0750 /var/lib/noemaforge /var/lib/noemaforge/bootstrap /var/lib/noemaforge/.sys /var/lib/noemaforge/.sys/cap_tokens 2>/dev/null || true
install -d -o noemaforge -g "$GROUP" -m 2770 /var/lib/noemaforge/sel /var/lib/noemaforge/sel/segments 2>/dev/null || install -d -o root -g "$GROUP" -m 2770 /var/lib/noemaforge/sel /var/lib/noemaforge/sel/segments 2>/dev/null || true
install -d -o root -g "$GROUP" -m 0775 /var/lib/noemaforge/tasks /var/lib/noemaforge/tasks/logs 2>/dev/null || true

install -m 0644 "$PKG_DIR/policies/noemaforge-stop-policy.json" /var/lib/noemaforge/.sys/noemaforge-stop-policy.json
install -m 0644 "$PKG_DIR/policies/runtime-invariants.json" /var/lib/noemaforge/.sys/runtime-invariants.json
chgrp "$GROUP" /var/lib/noemaforge/.sys/noemaforge-stop-policy.json /var/lib/noemaforge/.sys/runtime-invariants.json 2>/dev/null || true
chmod 0640 /var/lib/noemaforge/.sys/noemaforge-stop-policy.json /var/lib/noemaforge/.sys/runtime-invariants.json 2>/dev/null || true

/usr/local/sbin/noemaforge-sel-fix 2>/dev/null || true

systemctl daemon-reload
systemctl enable noemaforge-shutdown-stop.service 2>/dev/null || true
# Do not start heavy NoemaForge runtime automatically during install.
# Manager/modelscan timers are intentionally left in their current state.

bash -n /usr/local/sbin/noemaforge
bash -n /usr/local/sbin/noemaforge-stop
bash -n /usr/local/sbin/noemaforge-reboot-safe
bash -n /usr/local/sbin/noemaforge-vault-mount-ro
python3 -m py_compile /usr/local/sbin/noemaforge-model-advisor 2>/dev/null || true

cat <<EOM
NoemaForge ${VERSION} public MWP full package installed.
Backup: $BACKUP

Recommended next:
  hash -r
  noemaforge recommend-model
  sudo noemaforge stop --dry-run
  sudo noemaforge vault-status
  sudo noemaforge safe-start --wait --restart
  noemaforge smoke --debug
  noemaforge toolproxy diag --test-llm

Context transfer doc:
  /usr/local/share/noemaforge/context.md
EOM
