#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/prep/noemaforge-gui-prepare.sh
# Zone: prep/gui-safe
# Purpose: GUI-safe preparation before first start: packages, mount/Vault validation, llama-server discovery, full inventory, dataset scan, eval-pack build, and dry-run reorg plan.
# Callers: bin/noemaforge prepare-gui, operator shell.
# Inputs: --share-root, --vault-root, --candidate-limit, optional shortlist/mirror/shard flags.
# Outputs: /var/lib/noemaforge/bootstrap/gui-prepare.* and model-candidates.safe.json.
# Safety notes:
#   - Does not stop the graphical shell.
#   - Does not start NoemaForge runtime services or run firstboot scoring.
#   - Fails early when runtime-critical prerequisites are absent.
# === End NoemaForge File Header ===
set -euo pipefail

SHARE_ROOT="/mnt/noemaforge-share"
VAULT_ROOT=""
CANDIDATE_LIMIT="0"
SHORTLIST_FILE=""
INCLUDE_DOWNLOAD_MIRROR="0"
ALLOW_INCOMPLETE_SHARDS="0"
SKIP_PACKAGES="0"
STATE_DIR="/var/lib/noemaforge/bootstrap"
REPORT="$STATE_DIR/gui-prepare.json"
MARKER="$STATE_DIR/gui-prepare.done"
DISCOVERY_LOG="$STATE_DIR/model-discovery.log"
DISCOVERY_ERR="$STATE_DIR/model-discovery.stderr.log"

usage() {
  cat <<'EOF'
Usage:
  sudo noemaforge prepare-gui [options]

Options:
  --share-root PATH              Mounted NOEMAFORGE_SHARE path. Default: /mnt/noemaforge-share
  --vault-root PATH              Vault root. Auto-detects Vault and noemaforge-lab/data/Vault.
  --candidate-limit N            Compatibility GGUF discovery limit only; role-aware first-start uses top-8 per role after tests.
  --shortlist-file PATH          Optional text shortlist filter.
  --include-download-mirror      Also scan Vault/download-mirror/**/models*.
  --allow-incomplete-shards      Unsafe fallback: allow first shard even if other shards are missing.
  --skip-packages                Skip apt package installation/check block.
  -h, --help                     Show this help.

This is safe to run from GNOME. It prepares and validates, but it does not stop
the GUI and does not start the first NoemaForge runtime epoch.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --share-root) SHARE_ROOT="$2"; shift 2 ;;
    --vault-root) VAULT_ROOT="$2"; shift 2 ;;
    --candidate-limit) CANDIDATE_LIMIT="$2"; shift 2 ;;
    --shortlist-file) SHORTLIST_FILE="$2"; shift 2 ;;
    --include-download-mirror) INCLUDE_DOWNLOAD_MIRROR="1"; shift ;;
    --allow-incomplete-shards) ALLOW_INCOMPLETE_SHARDS="1"; shift ;;
    --skip-packages) SKIP_PACKAGES="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[noemaforge-prepare-gui][ERROR] unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

log(){ printf '[noemaforge-prepare-gui] %s\n' "$*"; }
fail(){ printf '[noemaforge-prepare-gui][ERROR] %s\n' "$*" >&2; exit 1; }
require_root(){ [[ $EUID -eq 0 ]] || fail "Run as root: sudo noemaforge prepare-gui"; }

fix_state_permissions() {
  # Reports must be readable by the operator outside sudo. The intended operator
  # user (cat) is already in group noemaforge, so keep the state private to that group
  # instead of making /var/lib/noemaforge world-readable.
  local group="noemaforge"
  getent group "$group" >/dev/null 2>&1 || group="root"

  install -d -o root -g "$group" -m 0750 /var/lib/noemaforge "$STATE_DIR"
  install -d -o root -g "$group" -m 0750 /workspace/outbox /workspace/outbox/bootreports 2>/dev/null || true

  # Make parent traversal explicit. Some earlier bootstrap/patch states left these
  # paths root-only, which made `noemaforge models` report the JSON as "missing".
  chgrp "$group" /var/lib/noemaforge "$STATE_DIR" 2>/dev/null || true
  chmod 0750 /var/lib/noemaforge "$STATE_DIR" 2>/dev/null || true

  for f in     "$STATE_DIR/model-candidates.safe.json"     "$STATE_DIR/noemaforge-firstboot-shortlist.safe.txt"     "$STATE_DIR/gui-prepare.json"     "$STATE_DIR/gui-prepare.done"     "$DISCOVERY_LOG"     "$DISCOVERY_ERR" "$STATE_DIR/model-inventory.json" "$STATE_DIR/dataset-inventory.json" "$STATE_DIR/role-eligibility-matrix.json" "$STATE_DIR/vault-reorg-plan.json" "$STATE_DIR/vault-reorg-audit.json" "$STATE_DIR/vault-reorg-apply-report.json"; do
    if [[ -e "$f" || -L "$f" ]]; then
      chown root:"$group" "$f" 2>/dev/null || chgrp "$group" "$f" 2>/dev/null || true
      chmod 0640 "$f" 2>/dev/null || true
    fi
  done
}

install_packages() {
  [[ "$SKIP_PACKAGES" == "0" ]] || { log "Package block skipped."; return 0; }
  command -v apt-get >/dev/null 2>&1 || fail "apt-get not found; unsupported host."
  log "Installing/checking required host packages while GUI is still available."
  DEBIAN_FRONTEND=noninteractive apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    jq curl git rsync ca-certificates procps findutils coreutils util-linux \
    python3 python3-yaml python3-venv bubblewrap \
    ffmpeg alsa-utils pipewire pipewire-bin pipewire-audio wireplumber v4l-utils \
    golang-go build-essential cmake ntfs-3g
}

find_vault_root() {
  if [[ -n "$VAULT_ROOT" ]]; then
    [[ -d "$VAULT_ROOT" ]] || fail "--vault-root does not exist: $VAULT_ROOT"
    return 0
  fi
  for d in "$SHARE_ROOT/noemaforge-lab/data/Vault" "$SHARE_ROOT/Vault"; do
    if [[ -d "$d" ]]; then
      VAULT_ROOT="$d"
      return 0
    fi
  done
  fail "Could not auto-detect Vault under $SHARE_ROOT. Provide --vault-root."
}

ensure_setup() {
  [[ -f /var/lib/noemaforge/.sys/setup.done ]] || fail "NoemaForge bootstrap marker missing: /var/lib/noemaforge/.sys/setup.done"
  [[ -f /opt/noemaforge/src/gguf_select.py ]] || fail "Missing /opt/noemaforge/src/gguf_select.py; apply model-safe patch first."
  [[ -f /opt/noemaforge/src/vault_inventory.py ]] || fail "Missing /opt/noemaforge/src/vault_inventory.py; apply 0.32.2 role-aware patch first."
  [[ -f /opt/noemaforge/src/role_tournament.py ]] || fail "Missing /opt/noemaforge/src/role_tournament.py; apply 0.32.2 role-aware patch first."
  [[ -f /opt/noemaforge/configs/role-catalog.yaml ]] || fail "Missing /opt/noemaforge/configs/role-catalog.yaml."
  # Incremental tar/rsync installs can leave helper scripts as 0644. Since
  # prepare-gui runs as root, repair executable bits here instead of failing late.
  local helper
  for helper in     /opt/noemaforge/tools/prep/noemaforge-firstboot-from-share.sh     /opt/noemaforge/tools/prep/noemaforge-first-launch.sh     /opt/noemaforge/tools/prep/noemaforge-firstboot-smoke.sh     /opt/noemaforge/tools/prep/noemaforge-headless.sh     /opt/noemaforge/bin/noemaforge     /opt/noemaforge/bin/noemaforge-llama-start
  do
    [[ -f "$helper" ]] || fail "Missing first-start helper: $helper"
    chmod 0755 "$helper" 2>/dev/null || true
    [[ -x "$helper" ]] || fail "Missing executable first-start helper: $helper"
  done
  fix_state_permissions
  install -d -m 0750 -o noemaforge -g noemaforge /run/noemaforge /run/noemaforge/llm /run/noemaforge/llm/backends
}

ensure_share_mount() {
  [[ -d "$SHARE_ROOT" ]] || fail "share root directory missing: $SHARE_ROOT"
  findmnt "$SHARE_ROOT" >/dev/null 2>&1 || fail "$SHARE_ROOT is not mounted. Fix NOEMAFORGE_SHARE mount before first start."
  [[ -r "$SHARE_ROOT" ]] || fail "$SHARE_ROOT is not readable."
}

validate_llama_server_runtime() {
  local bin="$1" ldd_out="" ldd_rc=0
  [[ -x "$bin" ]] || fail "llama-server is not executable: $bin"
  command -v ldd >/dev/null 2>&1 || fail "ldd not found; cannot verify llama-server shared-library readiness."
  ldd_out="$(ldd "$bin" 2>&1)" || ldd_rc=$?
  if printf '%s\n' "$ldd_out" | grep -q 'not found'; then
    fail "llama-server has unresolved shared libraries: $(printf '%s\n' "$ldd_out" | grep 'not found' | head -n 3 | tr '\n' '; ')"
  fi
  if [[ "$ldd_rc" -ne 0 ]] && ! printf '%s\n' "$ldd_out" | grep -Eqi 'not a dynamic executable|statically linked'; then
    fail "llama-server shared-library inspection failed with ldd rc=${ldd_rc}: $(printf '%s\n' "$ldd_out" | head -n 3 | tr '\n' '; ')"
  fi
  log "llama-server binary/shared-library gate passed: $bin"
}

ensure_llama_server() {
  if [[ -x /opt/noemaforge/bin/llama-server ]]; then
    log "llama-server present: /opt/noemaforge/bin/llama-server"
    validate_llama_server_runtime /opt/noemaforge/bin/llama-server
    return 0
  fi
  log "llama-server missing in /opt/noemaforge/bin; searching local disks/share."
  local cand=""
  cand="$(find "$SHARE_ROOT" /srv /home/cat -type f -name 'llama-server' -perm -111 -print -quit 2>/dev/null || true)"
  if [[ -n "$cand" ]]; then
    install -m 0755 "$cand" /opt/noemaforge/bin/llama-server
    log "Installed llama-server from: $cand"
    validate_llama_server_runtime /opt/noemaforge/bin/llama-server
    return 0
  fi
  cat >&2 <<'ERR'
[noemaforge-prepare-gui][ERROR]
/opt/noemaforge/bin/llama-server is required but was not found.
Place an executable llama-server on NOEMAFORGE_SHARE, /srv, or /home/cat, or build llama.cpp and install:
  sudo install -m 0755 <path-to-llama-server> /opt/noemaforge/bin/llama-server
Then rerun:
  sudo noemaforge prepare-gui
ERR
  exit 70
}

install_modelsafe_unit_override() {
  log "Ensuring systemd override for model-safe llama launcher."
  install -d /etc/systemd/system/noemaforge-llama@.service.d
  cat >/etc/systemd/system/noemaforge-llama@.service.d/20-modelsafe-wrapper.conf <<'EOF_OVERRIDE'
[Service]
ExecStart=
ExecStart=/opt/noemaforge/bin/noemaforge-llama-start %i /run/noemaforge/llm/backends/%i.sock
ExecStartPre=/bin/rm -f /run/noemaforge/llm/backends/%i.sock
EOF_OVERRIDE
  systemctl daemon-reload
  systemd-tmpfiles --create /etc/tmpfiles.d/noemaforge.conf >/dev/null 2>&1 || true
}

safe_model_discovery() {
  local candidates="$STATE_DIR/model-candidates.safe.json"
  local safe_shortlist="$STATE_DIR/noemaforge-firstboot-shortlist.safe.txt"
  local args=(discover --vault-root "$VAULT_ROOT" --share-root "$SHARE_ROOT" --candidate-limit "$CANDIDATE_LIMIT" --json-out "$candidates" --shortlist-out "$safe_shortlist")
  [[ -n "$SHORTLIST_FILE" ]] && args+=(--shortlist-file "$SHORTLIST_FILE")
  [[ "$INCLUDE_DOWNLOAD_MIRROR" == "1" ]] && args+=(--include-download-mirror)
  [[ "$ALLOW_INCOMPLETE_SHARDS" == "1" ]] && args+=(--allow-incomplete-shards)
  log "Building safe GGUF candidate list. Non-head shards are rejected."
  log "Discovery report target: $candidates"
  log "Discovery logs: $DISCOVERY_LOG ; $DISCOVERY_ERR"

  set +e
  /usr/bin/python3 /opt/noemaforge/src/gguf_select.py "${args[@]}" >"$DISCOVERY_LOG" 2>"$DISCOVERY_ERR"
  local status=$?
  set -e

  if [[ "$status" -ne 0 ]]; then
    log "gguf_select exited with code $status; continuing diagnostics before failing."
    if [[ -s "$DISCOVERY_ERR" ]]; then
      echo "----- model discovery stderr tail -----" >&2
      tail -n 80 "$DISCOVERY_ERR" >&2 || true
      echo "---------------------------------------" >&2
    fi
  fi

  if [[ ! -s "$candidates" ]]; then
    /usr/bin/python3 - "$candidates" "$VAULT_ROOT" "$SHARE_ROOT" "$status" "$DISCOVERY_LOG" "$DISCOVERY_ERR" <<'PY'
import datetime, json, os, sys
out, vault, share, status, log_path, err_path = sys.argv[1:]
os.makedirs(os.path.dirname(out), exist_ok=True)
obj = {
    'ok': False,
    'error': 'model_discovery_report_missing',
    'status': int(status),
    'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'vault_root': vault,
    'share_root': share,
    'candidate_count': 0,
    'rejected_count': 0,
    'roots': [],
    'candidates': [],
    'rejected': [],
    'logs': {'stdout': log_path, 'stderr': err_path},
}
with open(out, 'w', encoding='utf-8') as f:
    json.dump(obj, f, ensure_ascii=False, indent=2)
    f.write('\n')
PY
    fix_state_permissions
    fail "Safe model discovery failed before writing a normal report. See $candidates and $DISCOVERY_ERR"
  fi

  local count rejected ok err
  count="$(/usr/bin/python3 - <<PY
import json
obj=json.load(open('$candidates','r',encoding='utf-8'))
print(obj.get('candidate_count', 0))
PY
)"
  rejected="$(/usr/bin/python3 - <<PY
import json
obj=json.load(open('$candidates','r',encoding='utf-8'))
print(obj.get('rejected_count', 0))
PY
)"
  ok="$(/usr/bin/python3 - <<PY
import json
obj=json.load(open('$candidates','r',encoding='utf-8'))
print('1' if obj.get('ok') else '0')
PY
)"
  err="$(/usr/bin/python3 - <<PY
import json
obj=json.load(open('$candidates','r',encoding='utf-8'))
print(obj.get('error') or '')
PY
)"

  if [[ "$count" -le 0 ]]; then
    echo "[noemaforge-prepare-gui][MODEL DISCOVERY] No safe GGUF candidates were accepted." >&2
    echo "Report: $candidates" >&2
    echo "Logs:   $DISCOVERY_LOG" >&2
    echo "Errors: $DISCOVERY_ERR" >&2
    echo "Quick manual probe:" >&2
    echo "  find '$SHARE_ROOT' -type f -iname '*.gguf' -printf '%s %p\n' 2>/dev/null | sort -nr | head -n 30" >&2
    fail "Safe model candidate list is empty. Check Vault path or rejected shard reasons with: noemaforge models"
  fi
  [[ "$ok" == "1" ]] || fail "Safe model discovery report is not OK: ${err:-unknown error}. See $candidates"
  log "Safe GGUF candidates: $count; rejected: $rejected. Report: $candidates"
  fix_state_permissions
}

roleaware_prepare_reports() {
  log "Building full model inventory across canonical Vault."
  /usr/bin/python3 /opt/noemaforge/src/vault_inventory.py scan \
    --share-root "$SHARE_ROOT" \
    --vault-root "$VAULT_ROOT" \
    --json-out "$STATE_DIR/model-inventory.json"
  fix_state_permissions

  log "Scanning datasets and capability hints."
  /usr/bin/python3 /opt/noemaforge/src/dataset_inventory.py scan \
    --share-root "$SHARE_ROOT" \
    --vault-root "$VAULT_ROOT" \
    --json-out "$STATE_DIR/dataset-inventory.json"
  fix_state_permissions

  log "Building role-specific 10-task first-start eval packs."
  /usr/bin/python3 /opt/noemaforge/src/dataset_inventory.py build-packs \
    --role-catalog /opt/noemaforge/configs/role-catalog.yaml \
    --out-root /var/lib/noemaforge/eval-packs/first-start-light \
    --dataset-inventory "$STATE_DIR/dataset-inventory.json"
  fix_state_permissions

  log "Building role eligibility matrix; top-k is per role, not global."
  /usr/bin/python3 /opt/noemaforge/src/role_tournament.py eligibility \
    --inventory "$STATE_DIR/model-inventory.json" \
    --role-catalog /opt/noemaforge/configs/role-catalog.yaml \
    --json-out "$STATE_DIR/role-eligibility-matrix.json"
  fix_state_permissions

  log "Building safe dry-run Vault reorg plan with canonical-preserving quarantine policy."
  /usr/bin/python3 /opt/noemaforge/src/vault_reorg.py plan \
    --share-root "$SHARE_ROOT" \
    --vault-root "$VAULT_ROOT" \
    --json-out "$STATE_DIR/vault-reorg-plan.json"
  fix_state_permissions
}

write_prepare_report() {
  local candidates="$STATE_DIR/model-candidates.safe.json"
  /usr/bin/python3 - "$REPORT" "$MARKER" "$SHARE_ROOT" "$VAULT_ROOT" "$CANDIDATE_LIMIT" "$candidates" <<'PY'
import datetime, json, os, sys
report_path, marker_path, share, vault, limit, candidates_path = sys.argv[1:]
try:
    candidates = json.load(open(candidates_path, 'r', encoding='utf-8'))
except Exception:
    candidates = {}
obj = {
    'state': 'ready_for_first_start',
    'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'share_root': share,
    'vault_root': vault,
    'candidate_limit': int(limit),
    'candidate_report': candidates_path,
    'candidate_count': candidates.get('candidate_count', 0),
    'rejected_count': candidates.get('rejected_count', 0),
    'next_command': 'sudo noemaforge first-start',
    'discovery_logs': {
        'stdout': '/var/lib/noemaforge/bootstrap/model-discovery.log',
        'stderr': '/var/lib/noemaforge/bootstrap/model-discovery.stderr.log',
    },
}
os.makedirs(os.path.dirname(report_path), exist_ok=True)
with open(report_path, 'w', encoding='utf-8') as f:
    json.dump(obj, f, ensure_ascii=False, indent=2)
    f.write('\n')
with open(marker_path, 'w', encoding='utf-8') as f:
    f.write(obj['updated_at'] + '\n')
print(json.dumps(obj, ensure_ascii=False, indent=2))
PY
  fix_state_permissions
}

main() {
  require_root
  install_packages
  ensure_setup
  ensure_share_mount
  find_vault_root
  ensure_llama_server
  install_modelsafe_unit_override
  safe_model_discovery
  roleaware_prepare_reports
  write_prepare_report
  log "GUI-safe preparation is complete. Next: sudo noemaforge first-start"
}

main "$@"
