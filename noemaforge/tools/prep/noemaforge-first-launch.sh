#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/prep/noemaforge-first-launch.sh
# Zone: prep/spinal
# Purpose: Aggregate first-start command for the real Debian host: package checks, safe GGUF selection, explicit-opt-in soft headless switch, firstboot orchestration, service/timer reconciliation, and smoke tests.
# Callers: bin/noemaforge first-start, operator shell after bootstrap.
# Inputs: --share-root, --vault-root, --top-k, --candidate-limit, optional shortlist/mirror flags, optional --soft-headless plus required --allow-display-stop.
# Outputs: bootstrap JSON reports under /var/lib/noemaforge/bootstrap and bootreports under /workspace/outbox/bootreports.
# Safety notes:
#   - GUI sessions keep display-manager running by default; display stop requires explicit --allow-display-stop.
#   - Fails early before starting services when mount/model/runtime prerequisites are absent.
#   - Uses safe GGUF discovery; non-head shards are rejected.
#   - Soft headless mode is explicit opt-in only and is reversible with `sudo noemaforge first-start abort`.
# === End NoemaForge File Header ===
set -euo pipefail

SHARE_ROOT="/mnt/noemaforge-share"
VAULT_ROOT=""
TOP_K="2"
CANDIDATE_LIMIT="0"
MODEL_PROFILE="minimal"
SHORTLIST_FILE=""
INCLUDE_DOWNLOAD_MIRROR="0"
ALLOW_INCOMPLETE_SHARDS="0"
ALLOW_GRAPHICAL="0"
ALLOW_DISPLAY_STOP="0"
KEEP_DISPLAY="${NOEMAFORGE_FIRST_START_KEEP_DISPLAY:-1}"
SKIP_PACKAGES="0"
REBOOT_AFTER_APPLY="0"
SOFT_HEADLESS="0"
FROM_NOEMAFORGE_CLI="0"
SELECTION_MODE="normal"
COMPOSITE_TOP_N="-1"
DRY_RUN="0"
SHOW_CANDIDATES="0"
SHOW_COMPOSITIONS="0"
PER_MODEL_TIMEOUT="0"
TOTAL_TIMEOUT="0"
INCLUDE_UNVERIFIED="0"
YES_UNVERIFIED_RISK="0"
RETRY_FAILED_MODELS="0"
CLEAR_MODEL_HEALTH="0"
STRICT_ANY_FAIL="0"
ALLOW_FAILED_SELECTION="0"

usage() {
  cat <<'EOF'
Usage:
  sudo noemaforge first-start [options]
  sudo /opt/noemaforge/tools/prep/noemaforge-first-launch.sh [options]

Options:
  --share-root PATH              Mounted NOEMAFORGE_SHARE path. Default: /mnt/noemaforge-share
  --vault-root PATH              Vault root. Auto-detects Vault and noemaforge-lab/data/Vault.
  --top-k N                      Number of role candidates to keep. Default: 2
  --candidate-limit N            Compatibility GGUF discovery limit. Default: 0/all; first-start selects top-8 per role after tests.
  --model-profile NAME           minimal|balanced|writer|research|gpu-heavy profile; writes a profile manifest and keeps downloads manual.
  --shortlist-file PATH          Optional text shortlist filter.
  --include-download-mirror      Also scan Vault/download-mirror/**/models*.
  --allow-incomplete-shards      Unsafe fallback: allow first shard even if other shards are missing.
  --soft-headless                Request soft headless mode. Requires --allow-display-stop.
  --allow-display-stop           Explicitly permit display-manager stop. Dangerous; not used by default.
  --allow-headless-display-stop  Alias for --allow-display-stop.
  --keep-display                 Preserve display-manager/GDM; this is the default.
  --allow-graphical              Do not refuse GUI session. Patched1 preserves GUI by default.
  --skip-packages                Skip apt package installation/check block.
  --reboot-after-apply           Allow firstboot orchestrator to schedule reboot after epoch apply.
  --from-noemaforge-cli             Internal marker used by /opt/noemaforge/bin/noemaforge.

Selection modes for 0.32.1:
  --fast                         First valid measured candidate per role; no composite testing.
  --normal                       Keep at least two candidates per role where available; choose best; no composite testing.
  --full                         Evaluate all runnable models; choose best per role; no composite testing.
  --full_composite [N]           Evaluate all runnable models and build composition plan from top N candidates; N=0 means no top-limit.
  --dry-run                      Stop after model selection artifacts; no services, epoch switch or reboot.
  --show-candidates              Emit/retain candidate-selection artifacts for operator review.
  --show-compositions            Emit/retain composite-selection artifacts when using --full_composite.
  TTY status                    Non-dry-run prints periodic progress to /dev/console; disable with NOEMAFORGE_FIRST_START_TTY_STATUS=0.
  Interrupt/recover              Ctrl+C on direct TTY stops first-start and restores GUI; systemd jobs can be stopped with: sudo noemaforge first-start abort.
  --per-model-timeout SEC        Hard per-model watchdog for first-start tournament.
  --total-timeout SEC            Hard total watchdog for first-start tournament.
  --include-unverified           Include models blocked by default safety-name filter.
  --yes-i-understand-unverified-risk
                                  Required when using --include-unverified in real/apply mode.
  --retry-failed-models          Retry models previously marked failed in model-health-registry.json.
  --clear-model-health           Clear persisted failed-model registry before this run.
  --strict-any-fail              Globally disqualify a model on any failed/no-pass role result.
  --allow-failed-selection       Compatibility escape hatch; do not exclude failed models from selection.
  -h, --help                     Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --share-root) SHARE_ROOT="$2"; shift 2 ;;
    --vault-root) VAULT_ROOT="$2"; shift 2 ;;
    --top-k) TOP_K="$2"; shift 2 ;;
    --candidate-limit) CANDIDATE_LIMIT="$2"; shift 2 ;;
    --model-profile) MODEL_PROFILE="$2"; shift 2 ;;
    --shortlist-file) SHORTLIST_FILE="$2"; shift 2 ;;
    --include-download-mirror) INCLUDE_DOWNLOAD_MIRROR="1"; shift ;;
    --allow-incomplete-shards) ALLOW_INCOMPLETE_SHARDS="1"; shift ;;
    --allow-graphical) ALLOW_GRAPHICAL="1"; shift ;;
    --skip-packages) SKIP_PACKAGES="1"; shift ;;
    --reboot-after-apply) REBOOT_AFTER_APPLY="1"; shift ;;
    --soft-headless) SOFT_HEADLESS="1"; KEEP_DISPLAY="0"; shift ;;
    --allow-display-stop|--allow-headless-display-stop) ALLOW_DISPLAY_STOP="1"; KEEP_DISPLAY="0"; shift ;;
    --keep-display|--no-display-stop) KEEP_DISPLAY="1"; SOFT_HEADLESS="0"; ALLOW_DISPLAY_STOP="0"; shift ;;
    --from-noemaforge-cli) FROM_NOEMAFORGE_CLI="1"; shift ;;
    --fast) SELECTION_MODE="fast"; shift ;;
    --normal) SELECTION_MODE="normal"; shift ;;
    --full) SELECTION_MODE="full"; shift ;;
    --full_composite) SELECTION_MODE="full_composite"; if [[ $# -gt 1 && "$2" =~ ^[0-9]+$ ]]; then COMPOSITE_TOP_N="$2"; shift 2; else COMPOSITE_TOP_N="0"; shift; fi ;;
    --dry-run) DRY_RUN="1"; shift ;;
    --show-candidates) SHOW_CANDIDATES="1"; shift ;;
    --show-compositions) SHOW_COMPOSITIONS="1"; shift ;;
    --per-model-timeout) PER_MODEL_TIMEOUT="$2"; shift 2 ;;
    --total-timeout) TOTAL_TIMEOUT="$2"; shift 2 ;;
    --include-unverified) INCLUDE_UNVERIFIED="1"; shift ;;
    --yes-i-understand-unverified-risk) YES_UNVERIFIED_RISK="1"; shift ;;
    --retry-failed-models) RETRY_FAILED_MODELS="1"; shift ;;
    --clear-model-health) CLEAR_MODEL_HEALTH="1"; shift ;;
    --strict-any-fail) STRICT_ANY_FAIL="1"; shift ;;
    --allow-failed-selection) ALLOW_FAILED_SELECTION="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[noemaforge-first-launch][ERROR] unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$MODEL_PROFILE" in minimal|balanced|writer|research|gpu-heavy) : ;; *) echo "[noemaforge-first-launch][ERROR] unsupported model profile: $MODEL_PROFILE" >&2; exit 2 ;; esac

# Patched1 display safety: model selection must not blank the local monitor by
# default. A display stop is allowed only when the operator explicitly passes
# --allow-display-stop together with --soft-headless.
if [[ "${KEEP_DISPLAY}" == "1" ]]; then
  SOFT_HEADLESS="0"
fi
if [[ "${SOFT_HEADLESS}" == "1" && "${ALLOW_DISPLAY_STOP}" != "1" ]]; then
  echo "[noemaforge-first-launch][ERROR] --soft-headless now requires explicit --allow-display-stop; default first-start preserves Debian GUI/display-manager." >&2
  exit 22
fi

log(){ printf '[noemaforge-first-launch] %s\n' "$*"; }
fail(){ printf '[noemaforge-first-launch][ERROR] %s\n' "$*" >&2; exit 1; }

STATUS_MONITOR_PID=""
FIRST_START_INTERRUPTED="0"
RESTORE_GUI_ON_EXIT="1"

console_line() {
  local msg="$*" ts
  ts="$(date -Is 2>/dev/null || date)"
  printf '[NoemaForge first-start][%s] %s\n' "$ts" "$msg"
  if [[ -w /dev/console ]]; then
    printf '[NoemaForge first-start][%s] %s\n' "$ts" "$msg" >/dev/console 2>/dev/null || true
  fi
}

restore_graphical_after_first_start() {
  local reason="${1:-complete}"
  [[ "$DRY_RUN" == "1" ]] && return 0
  [[ "${NOEMAFORGE_RESTORE_GUI_AFTER_FIRST_START:-1}" == "0" ]] && return 0
  console_line "restoring Debian GUI after first-start reason=${reason} via minimal non-blocking recovery"
  # patched10: do not call high-level headless off as the first recovery step.
  # In emergency/degraded systemd states it may block on display-manager jobs.
  if [[ -x /opt/noemaforge/tools/prep/noemaforge-gui-recover-minimal.sh ]]; then
    /opt/noemaforge/tools/prep/noemaforge-gui-recover-minimal.sh --reason "first-start-${reason}" 2>/dev/null || true
  else
    systemctl daemon-reload 2>/dev/null || true
    systemctl reset-failed 2>/dev/null || true
    systemctl set-default graphical.target 2>/dev/null || true
    systemctl start --no-block systemd-user-sessions.service 2>/dev/null || true
    rm -f /run/nologin 2>/dev/null || true
    systemctl start --no-block display-manager.service 2>/dev/null || true
    systemctl start --no-block gdm.service 2>/dev/null || true
    systemctl start --no-block gdm3.service 2>/dev/null || true
    systemctl isolate --no-block graphical.target 2>/dev/null || true
  fi
  systemctl reset-failed noemaforge-autostart-gui.service noemaforge-first-start.service 2>/dev/null || true
}

stop_status_monitor() {
  if [[ -n "${STATUS_MONITOR_PID:-}" ]]; then
    kill "$STATUS_MONITOR_PID" 2>/dev/null || true
    wait "$STATUS_MONITOR_PID" 2>/dev/null || true
    STATUS_MONITOR_PID=""
  fi
}

start_status_monitor() {
  [[ "$DRY_RUN" == "1" ]] && return 0
  [[ "${NOEMAFORGE_FIRST_START_TTY_STATUS:-1}" == "0" ]] && return 0
  local interval="${NOEMAFORGE_FIRST_START_TTY_STATUS_INTERVAL:-20}"
  (
    while true; do
      local line ts
      line="$('/usr/bin/python3' - <<'PY_STATUS' 2>/dev/null || true
import json
from pathlib import Path
boot=Path('/var/lib/noemaforge/bootstrap')
status={}
progress={}
try:
    status=json.loads((boot/'firstboot-status.json').read_text())
except Exception:
    pass
try:
    progress=json.loads((boot/'role-tournament-progress.json').read_text())
except Exception:
    pass
step=status.get('step') or progress.get('phase') or 'preflight'
state=status.get('state') or progress.get('phase') or 'running'
model=progress.get('model_id') or '-'
role=progress.get('role_key') or '-'
task=progress.get('task_index')
total=progress.get('total_tasks')
left=progress.get('deadline_remaining_sec')
msg=f"step={step} state={state} model={model} role={role}"
if task is not None and total is not None:
    msg += f" task={task}/{total}"
if left is not None:
    msg += f" left={left}s"
msg += " | abort: Ctrl+C on direct TTY or sudo noemaforge first-start abort"
print(msg)
PY_STATUS
)"
      ts="$(date -Is 2>/dev/null || date)"
      printf '[NoemaForge first-start][%s] %s\n' "$ts" "$line"
      if [[ -w /dev/console ]]; then
        printf '[NoemaForge first-start][%s] %s\n' "$ts" "$line" >/dev/console 2>/dev/null || true
      fi
      sleep "$interval"
    done
  ) &
  STATUS_MONITOR_PID=$!
}

stop_first_start_processes() {
  pkill -TERM -f 'firstboot_orchestrator.py|role_tournament.py|llama-server|noemaforge-llama-start' 2>/dev/null || true
  sleep 5
  pkill -KILL -f 'firstboot_orchestrator.py|role_tournament.py|llama-server|noemaforge-llama-start' 2>/dev/null || true
  systemctl list-units --type=service --all 'noemaforge-llama@*.service' --no-legend 2>/dev/null | awk '{print $1}' | xargs -r systemctl stop 2>/dev/null || true
}

on_interrupt() {
  local sig="$1"
  FIRST_START_INTERRUPTED="1"
  console_line "interrupt ${sig} received; stopping first-start and restoring GUI"
  trap - INT TERM EXIT
  stop_status_monitor
  stop_first_start_processes
  restore_graphical_after_first_start "interrupt-${sig}"
  exit 130
}

on_exit() {
  local rc="$?"
  stop_status_monitor
  if [[ "$DRY_RUN" != "1" ]]; then
    if [[ "$FIRST_START_INTERRUPTED" == "1" ]]; then
      restore_graphical_after_first_start "interrupt"
    elif [[ "$rc" == "0" ]]; then
      restore_graphical_after_first_start "complete"
    else
      restore_graphical_after_first_start "error-rc-${rc}"
    fi
  fi
}

trap 'on_interrupt INT' INT
trap 'on_interrupt TERM' TERM
trap 'on_exit' EXIT

require_root() { [[ $EUID -eq 0 ]] || fail "Run as root: sudo noemaforge first-start"; }

is_graphical_session() {
  [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]] && return 0
  [[ "${XDG_SESSION_TYPE:-}" == "x11" || "${XDG_SESSION_TYPE:-}" == "wayland" ]] && return 0
  [[ -n "${XDG_CURRENT_DESKTOP:-}" ]] && return 0
  return 1
}

guard_graphical_by_default() {
  [[ "$ALLOW_GRAPHICAL" == "1" ]] && return 0
  [[ "$DRY_RUN" == "1" ]] && return 0
  [[ "$SOFT_HEADLESS" == "1" ]] && return 0
  if is_graphical_session; then
    cat >&2 <<'EOF'
[noemaforge-first-launch][WARNING]
This script refuses direct graphical sessions by default.
Use the simple wrapper instead:
  sudo noemaforge first-start

The wrapper moves long-running work into a systemd job while preserving
the display manager by default. Display stop requires explicit --allow-display-stop.
EOF
    exit 20
  fi
}

noemaforge_detect_distro_family() {
  local os_id="" os_id_like="" id_like
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    os_id="${ID:-}"
    os_id_like="${ID_LIKE:-}"
  fi
  id_like=" ${os_id,,} ${os_id_like,,} "
  case "$id_like" in
    *" debian "*|*" ubuntu "*|*" linuxmint "*|*" raspbian "*) printf 'debian\n' ;;
    *" fedora "*|*" rhel "*|*" centos "*|*" rocky "*|*" almalinux "*) printf 'fedora\n' ;;
    *" arch "*|*" manjaro "*) printf 'arch\n' ;;
    *" opensuse "*|*" suse "*|*" sles "*) printf 'suse\n' ;;
    *) printf 'unknown\n' ;;
  esac
}

noemaforge_package_manager_for_family() {
  case "$1" in
    debian) command -v apt-get >/dev/null 2>&1 && printf 'apt-get\n' ;;
    fedora)
      if command -v dnf >/dev/null 2>&1; then
        printf 'dnf\n'
      elif command -v yum >/dev/null 2>&1; then
        printf 'yum\n'
      fi
      ;;
    arch) command -v pacman >/dev/null 2>&1 && printf 'pacman\n' ;;
    suse) command -v zypper >/dev/null 2>&1 && printf 'zypper\n' ;;
    *) printf '\n' ;;
  esac
}

noemaforge_packages_for_family() {
  case "$1" in
    debian)
      printf '%s\n' 'jq curl git rsync ca-certificates procps findutils coreutils util-linux python3 python3-yaml python3-venv bubblewrap ffmpeg alsa-utils pipewire pipewire-bin pipewire-audio wireplumber v4l-utils golang-go build-essential cmake ntfs-3g'
      ;;
    fedora)
      printf '%s\n' 'jq curl git rsync ca-certificates procps-ng findutils coreutils util-linux python3 python3-pyyaml bubblewrap ffmpeg alsa-utils pipewire wireplumber v4l-utils golang gcc gcc-c++ make cmake ntfs-3g'
      ;;
    arch)
      printf '%s\n' 'jq curl git rsync ca-certificates procps-ng findutils coreutils util-linux python python-yaml bubblewrap ffmpeg alsa-utils pipewire wireplumber v4l-utils go base-devel cmake ntfs-3g'
      ;;
    suse)
      printf '%s\n' 'jq curl git rsync ca-certificates procps findutils coreutils util-linux python3 python3-PyYAML python3-venv bubblewrap ffmpeg alsa-utils pipewire wireplumber v4l-utils go gcc gcc-c++ make cmake ntfs-3g'
      ;;
    *) printf '\n' ;;
  esac
}

install_packages() {
  [[ "$SKIP_PACKAGES" == "0" ]] || { log "Package block skipped."; return 0; }
  local family manager packages
  family="$(noemaforge_detect_distro_family)"
  manager="$(noemaforge_package_manager_for_family "$family")"
  packages="$(noemaforge_packages_for_family "$family")"
  [[ -n "$manager" && -n "$packages" ]] || fail "supported package manager not found for distro_family=${family}; run noemaforge trixie-preflight --remediation-plan for manual dependency remediation."
  log "Installing/checking required host packages with ${manager} for distro_family=${family}."
  case "$manager" in
    apt-get)
      DEBIAN_FRONTEND=noninteractive apt-get update -y
      DEBIAN_FRONTEND=noninteractive apt-get install -y $packages
      ;;
    dnf|yum)
      "$manager" install -y $packages
      ;;
    pacman)
      pacman -Sy --noconfirm $packages
      ;;
    zypper)
      zypper --non-interactive refresh
      zypper --non-interactive install $packages
      ;;
    *)
      fail "unsupported package manager for first-launch dependency remediation: ${manager}"
      ;;
  esac
}

find_vault_root() {
  if [[ -n "$VAULT_ROOT" ]]; then [[ -d "$VAULT_ROOT" ]] || fail "--vault-root does not exist: $VAULT_ROOT"; return 0; fi
  for d in "$SHARE_ROOT/noemaforge-lab/data/Vault" "$SHARE_ROOT/Vault"; do
    if [[ -d "$d" ]]; then VAULT_ROOT="$d"; return 0; fi
  done
  fail "Could not auto-detect Vault under $SHARE_ROOT. Provide --vault-root."
}

ensure_setup() {
  [[ -f /var/lib/noemaforge/.sys/setup.done ]] || fail "NoemaForge bootstrap marker missing: /var/lib/noemaforge/.sys/setup.done"
  [[ -f /opt/noemaforge/src/firstboot_orchestrator.py ]] || fail "Missing /opt/noemaforge/src/firstboot_orchestrator.py"
  [[ -f /opt/noemaforge/src/gguf_select.py ]] || fail "Missing /opt/noemaforge/src/gguf_select.py; apply the model-safe patch first."
  [[ -f /opt/noemaforge/src/vault_inventory.py ]] || fail "Missing /opt/noemaforge/src/vault_inventory.py; apply 0.32.2 role-aware patch first."
  [[ -f /opt/noemaforge/src/role_tournament.py ]] || fail "Missing /opt/noemaforge/src/role_tournament.py; apply 0.32.2 role-aware patch first."
  [[ -f /opt/noemaforge/configs/role-catalog.yaml ]] || fail "Missing /opt/noemaforge/configs/role-catalog.yaml."
  [[ -x /opt/noemaforge/bin/noemaforge-llama-start ]] || fail "Missing executable /opt/noemaforge/bin/noemaforge-llama-start"
  [[ -x /opt/noemaforge/tools/prep/noemaforge-firstboot-from-share.sh ]] || fail "Missing executable firstboot helper."
  [[ -x /opt/noemaforge/tools/prep/noemaforge-firstboot-smoke.sh ]] || fail "Missing executable smoke helper."
  [[ -x /opt/noemaforge/tools/prep/noemaforge-headless.sh ]] || fail "Missing executable headless helper."
  install -d -m 0750 -o noemaforge -g noemaforge /run/noemaforge /run/noemaforge/llm /run/noemaforge/llm/backends
  install -d -m 0755 /var/lib/noemaforge/bootstrap /workspace/outbox/bootreports
}

ensure_share_mount() {
  [[ -d "$SHARE_ROOT" ]] || fail "share root directory missing: $SHARE_ROOT"
  findmnt "$SHARE_ROOT" >/dev/null 2>&1 || fail "$SHARE_ROOT is not mounted. Fix NOEMAFORGE_SHARE mount before first launch."
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
  if [[ "$DRY_RUN" == "1" ]]; then
    fail "dry-run selection requires /opt/noemaforge/bin/llama-server to already exist; refusing to install or copy binaries in dry-run mode."
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
  cat >&2 <<'EOF'
[noemaforge-first-launch][ERROR]
/opt/noemaforge/bin/llama-server is required but was not found.
Place an executable llama-server on NOEMAFORGE_SHARE, /srv, or /home/cat, or build llama.cpp and install:
  sudo install -m 0755 <path-to-llama-server> /opt/noemaforge/bin/llama-server
Then rerun first start:
  sudo noemaforge first-start
EOF
  exit 70
}

install_modelsafe_unit_override() {
  log "Installing systemd override for model-safe llama launcher."
  install -d /etc/systemd/system/noemaforge-llama@.service.d
  cat >/etc/systemd/system/noemaforge-llama@.service.d/20-modelsafe-wrapper.conf <<'EOF'
[Service]
ExecStart=
ExecStart=/opt/noemaforge/bin/noemaforge-llama-start %i /run/noemaforge/llm/backends/%i.sock
ExecStartPre=/bin/rm -f /run/noemaforge/llm/backends/%i.sock
EOF
  systemctl daemon-reload
  systemd-tmpfiles --create /etc/tmpfiles.d/noemaforge.conf >/dev/null 2>&1 || true
}

safe_model_discovery() {
  local report="/var/lib/noemaforge/bootstrap/model-candidates.safe.json"
  local safe_shortlist="/var/lib/noemaforge/bootstrap/noemaforge-firstboot-shortlist.safe.txt"
  local args=(discover --vault-root "$VAULT_ROOT" --candidate-limit "$CANDIDATE_LIMIT" --json-out "$report" --shortlist-out "$safe_shortlist")
  [[ -n "$SHORTLIST_FILE" ]] && args+=(--shortlist-file "$SHORTLIST_FILE")
  [[ "$INCLUDE_DOWNLOAD_MIRROR" == "1" ]] && args+=(--include-download-mirror)
  [[ "$ALLOW_INCOMPLETE_SHARDS" == "1" ]] && args+=(--allow-incomplete-shards)
  log "Building safe GGUF candidate list."
  /usr/bin/python3 /opt/noemaforge/src/gguf_select.py "${args[@]}"
  local count
  count="$(/usr/bin/python3 - <<PY
import json
obj=json.load(open('$report','r',encoding='utf-8'))
print(obj.get('candidate_count', 0))
PY
)"
  [[ "$count" -gt 0 ]] || fail "Safe model candidate list is empty. See $report"
  log "Safe GGUF candidates: $count. Report: $report"
}


role_aware_preflight() {
  log "Building full model inventory and role eval packs before stopping GUI."
  /usr/bin/python3 /opt/noemaforge/src/vault_inventory.py scan \
    --share-root "$SHARE_ROOT" \
    --vault-root "$VAULT_ROOT" \
    --json-out /var/lib/noemaforge/bootstrap/model-inventory.json
  /usr/bin/python3 /opt/noemaforge/src/dataset_inventory.py scan \
    --share-root "$SHARE_ROOT" \
    --vault-root "$VAULT_ROOT" \
    --json-out /var/lib/noemaforge/bootstrap/dataset-inventory.json
  /usr/bin/python3 /opt/noemaforge/src/dataset_inventory.py build-packs \
    --role-catalog /opt/noemaforge/configs/role-catalog.yaml \
    --out-root /var/lib/noemaforge/eval-packs/first-start-light \
    --dataset-inventory /var/lib/noemaforge/bootstrap/dataset-inventory.json
  /usr/bin/python3 /opt/noemaforge/src/role_tournament.py eligibility \
    --inventory /var/lib/noemaforge/bootstrap/model-inventory.json \
    --role-catalog /opt/noemaforge/configs/role-catalog.yaml \
    --json-out /var/lib/noemaforge/bootstrap/role-eligibility-matrix.json
}

apply_soft_headless_if_requested() {
  [[ "$SOFT_HEADLESS" == "1" ]] || { log "Display-manager preserved; soft headless not requested."; return 0; }
  [[ "$ALLOW_DISPLAY_STOP" == "1" ]] || fail "display stop denied: rerun with --allow-display-stop only if you intentionally want headless mode."
  if [[ "$DRY_RUN" == "1" ]]; then
    log "Dry-run requested; skipping soft headless switch."
    return 0
  fi
  log "Preparation checks passed; switching to explicit soft headless mode before runtime start."
  log "GNOME/display-manager will be stopped because --allow-display-stop was supplied. Restore later with: sudo noemaforge first-start abort"
  /opt/noemaforge/tools/prep/noemaforge-headless.sh on --reason first-start
}

run_firstboot_orchestrator() {
  local safe_shortlist="/var/lib/noemaforge/bootstrap/noemaforge-firstboot-shortlist.safe.txt"
  local args=(--share-root "$SHARE_ROOT" --vault-root "$VAULT_ROOT" --candidate-limit "$CANDIDATE_LIMIT" --top-k "$TOP_K" --shortlist-file "$safe_shortlist" --model-profile "$MODEL_PROFILE" --selection-mode "$SELECTION_MODE" --composite-top-n "$COMPOSITE_TOP_N")
  [[ "$INCLUDE_DOWNLOAD_MIRROR" == "1" ]] && args+=(--include-download-mirror)
  [[ "$ALLOW_INCOMPLETE_SHARDS" == "1" ]] && args+=(--allow-incomplete-shards)
  [[ "$REBOOT_AFTER_APPLY" == "0" ]] && args+=(--no-reboot)
  [[ "$DRY_RUN" == "1" ]] && args+=(--dry-run)
  [[ "$SHOW_CANDIDATES" == "1" ]] && args+=(--show-candidates)
  [[ "$SHOW_COMPOSITIONS" == "1" ]] && args+=(--show-compositions)
  [[ "$PER_MODEL_TIMEOUT" != "0" ]] && args+=(--per-model-timeout "$PER_MODEL_TIMEOUT")
  [[ "$TOTAL_TIMEOUT" != "0" ]] && args+=(--total-timeout "$TOTAL_TIMEOUT")
  [[ "$INCLUDE_UNVERIFIED" == "1" ]] && args+=(--include-unverified)
  [[ "$YES_UNVERIFIED_RISK" == "1" ]] && args+=(--yes-i-understand-unverified-risk)
  [[ "$RETRY_FAILED_MODELS" == "1" ]] && args+=(--retry-failed-models)
  [[ "$CLEAR_MODEL_HEALTH" == "1" ]] && args+=(--clear-model-health)
  [[ "$STRICT_ANY_FAIL" == "1" ]] && args+=(--strict-any-fail)
  [[ "$ALLOW_FAILED_SELECTION" == "1" ]] && args+=(--allow-failed-selection)
  log "Running firstboot orchestrator."
  /opt/noemaforge/tools/prep/noemaforge-firstboot-from-share.sh "${args[@]}"
}

start_orchestrators_and_services() {
  log "Enabling core services and orchestrator timers."
  systemctl enable --now noemaforge-bootdoctor.service 2>/dev/null || true
  systemctl enable --now noemaforge-memsentinel.service noemaforge-llm-gateway.service noemaforge-toolproxy.service
  systemctl enable --now noemaforge-modelscan.timer noemaforge-llm-backends-manager.timer
  systemctl start noemaforge-modelscan.service || true
  systemctl start noemaforge-llm-backends-manager.service || true
}

validate_and_smoke() {
  log "Validating ModelStore GGUF shard safety."
  /usr/bin/python3 /opt/noemaforge/src/gguf_select.py validate-modelstore --root /var/lib/modelstore --json-out /var/lib/noemaforge/bootstrap/modelstore-validation.safe.json
  log "Running firstboot smoke."
  /opt/noemaforge/tools/prep/noemaforge-firstboot-smoke.sh
}

write_summary() {
  local out="/workspace/outbox/bootreports/first-launch-summary.txt"
  {
    echo "NoemaForge first launch summary"; date -Is
    echo "share_root=$SHARE_ROOT"; echo "vault_root=$VAULT_ROOT"; echo "top_k=$TOP_K"; echo "candidate_limit=$CANDIDATE_LIMIT"; echo "model_profile=$MODEL_PROFILE"; echo "soft_headless=$SOFT_HEADLESS"; echo "keep_display=$KEEP_DISPLAY"; echo "allow_display_stop=$ALLOW_DISPLAY_STOP"; echo "selection_mode=$SELECTION_MODE"; echo "composite_top_n=$COMPOSITE_TOP_N"; echo "dry_run=$DRY_RUN"; echo "per_model_timeout=$PER_MODEL_TIMEOUT"; echo "total_timeout=$TOTAL_TIMEOUT"; echo "include_unverified=$INCLUDE_UNVERIFIED"; echo "retry_failed_models=$RETRY_FAILED_MODELS"; echo "clear_model_health=$CLEAR_MODEL_HEALTH"; echo "strict_any_fail=$STRICT_ANY_FAIL"
    echo "candidate_report=/var/lib/noemaforge/bootstrap/model-candidates.safe.json"
    echo "model_inventory=/var/lib/noemaforge/bootstrap/model-inventory.json"
    echo "role_tournament=/var/lib/noemaforge/bootstrap/role-tournament-results.json"
    echo "role_candidate_map=/var/lib/noemaforge/bootstrap/role-candidate-map.json"
    echo "modelstore_validation=/var/lib/noemaforge/bootstrap/modelstore-validation.safe.json"
    echo; echo "== headless status =="; /opt/noemaforge/tools/prep/noemaforge-headless.sh status || true
    echo; echo "== units =="; systemctl --no-pager --failed || true
    echo; echo "== noemaforge status =="; systemctl status noemaforge-llm-gateway noemaforge-toolproxy noemaforge-llama@main --no-pager || true
  } >"$out"
  log "Summary written: $out"
}

main() {
  require_root
  if [[ "$INCLUDE_UNVERIFIED" == "1" && "$DRY_RUN" != "1" && "$YES_UNVERIFIED_RISK" != "1" ]]; then
    fail "real first-start with --include-unverified requires --yes-i-understand-unverified-risk; use --dry-run first."
  fi
  if [[ "$DRY_RUN" == "1" && "$SKIP_PACKAGES" == "0" ]]; then
    log "Dry-run requested; forcing package block skip to keep first-start selection-only."
    SKIP_PACKAGES="1"
  fi
  guard_graphical_by_default
  install_packages
  ensure_setup
  ensure_share_mount
  find_vault_root
  ensure_llama_server
  if [[ "$DRY_RUN" == "1" ]]; then
    log "Dry-run requested; skipping systemd unit override installation."
  else
    install_modelsafe_unit_override
  fi
  start_status_monitor
  console_line "preflight complete; building safe model discovery"
  safe_model_discovery
  console_line "safe model discovery complete; building role-aware inventory/eval packs"
  role_aware_preflight
  apply_soft_headless_if_requested
  console_line "starting firstboot orchestrator selection_mode=${SELECTION_MODE} composite_top_n=${COMPOSITE_TOP_N} total_timeout=${TOTAL_TIMEOUT}"
  run_firstboot_orchestrator
  console_line "firstboot orchestrator finished"
  if [[ "$DRY_RUN" == "1" ]]; then
    write_summary
    log "First start dry-run completed. No services, epoch switch, headless switch, smoke or reboot were performed."
    return 0
  fi
  start_orchestrators_and_services
  validate_and_smoke
  write_summary
  log "First start completed. Debian GUI restore requested automatically; reboot manually only if needed: sudo reboot"
}

main "$@"
