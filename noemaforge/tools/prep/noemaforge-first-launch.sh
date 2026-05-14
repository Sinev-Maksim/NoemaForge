#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/prep/noemaforge-first-launch.sh
# Zone: prep/spinal
# Purpose: Aggregate first-start command for the real Debian host: package checks, safe GGUF selection, optional soft headless switch, firstboot orchestration, service/timer reconciliation, and smoke tests.
# Callers: bin/noemaforge first-start, operator shell after bootstrap.
# Inputs: --share-root, --vault-root, --top-k, --candidate-limit, optional shortlist/mirror flags, optional --soft-headless.
# Outputs: bootstrap JSON reports under /var/lib/noemaforge/bootstrap and bootreports under /workspace/outbox/bootreports.
# Safety notes:
#   - GUI sessions should use `sudo noemaforge first-start`; it rehomes the work into systemd before stopping display-manager.
#   - Fails early before starting services when mount/model/runtime prerequisites are absent.
#   - Uses safe GGUF discovery; non-head shards are rejected.
#   - Soft headless mode keeps GNOME installed and is reversible with `sudo noemaforge headless off`.
# === End NoemaForge File Header ===
set -euo pipefail

SHARE_ROOT="/mnt/noemaforge-share"
VAULT_ROOT=""
TOP_K="2"
CANDIDATE_LIMIT="0"
SHORTLIST_FILE=""
INCLUDE_DOWNLOAD_MIRROR="0"
ALLOW_INCOMPLETE_SHARDS="0"
ALLOW_GRAPHICAL="0"
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
  --shortlist-file PATH          Optional text shortlist filter.
  --include-download-mirror      Also scan Vault/download-mirror/**/models*.
  --allow-incomplete-shards      Unsafe fallback: allow first shard even if other shards are missing.
  --soft-headless                After prep succeeds, set default target to multi-user and stop display-manager.
  --allow-graphical              Do not refuse GUI session. Not recommended unless also using --soft-headless via noemaforge CLI.
  --skip-packages                Skip apt package installation/check block.
  --reboot-after-apply           Allow firstboot orchestrator to schedule reboot after epoch apply.
  --from-noemaforge-cli             Internal marker used by /opt/noemaforge/bin/noemaforge.

Selection modes for 0.31.13.alpha:
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
    --shortlist-file) SHORTLIST_FILE="$2"; shift 2 ;;
    --include-download-mirror) INCLUDE_DOWNLOAD_MIRROR="1"; shift ;;
    --allow-incomplete-shards) ALLOW_INCOMPLETE_SHARDS="1"; shift ;;
    --allow-graphical) ALLOW_GRAPHICAL="1"; shift ;;
    --skip-packages) SKIP_PACKAGES="1"; shift ;;
    --reboot-after-apply) REBOOT_AFTER_APPLY="1"; shift ;;
    --soft-headless) SOFT_HEADLESS="1"; shift ;;
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

The wrapper moves the long-running work into a systemd job, then softly stops
the display manager only after preparation/model discovery succeeds.
EOF
    exit 20
  fi
}

install_packages() {
  [[ "$SKIP_PACKAGES" == "0" ]] || { log "Package block skipped."; return 0; }
  command -v apt-get >/dev/null 2>&1 || fail "apt-get not found; unsupported host."
  log "Installing/checking required host packages."
  DEBIAN_FRONTEND=noninteractive apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    jq curl git rsync ca-certificates procps findutils coreutils util-linux \
    python3 python3-yaml python3-venv bubblewrap \
    ffmpeg alsa-utils pipewire pipewire-bin pipewire-audio wireplumber v4l-utils \
    golang-go build-essential cmake ntfs-3g
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
  [[ -f /opt/noemaforge/src/vault_inventory.py ]] || fail "Missing /opt/noemaforge/src/vault_inventory.py; apply 0.28.5 role-aware patch first."
  [[ -f /opt/noemaforge/src/role_tournament.py ]] || fail "Missing /opt/noemaforge/src/role_tournament.py; apply 0.28.5 role-aware patch first."
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

ensure_llama_server() {
  if [[ -x /opt/noemaforge/bin/llama-server ]]; then log "llama-server present: /opt/noemaforge/bin/llama-server"; return 0; fi
  if [[ "$DRY_RUN" == "1" ]]; then
    fail "dry-run selection requires /opt/noemaforge/bin/llama-server to already exist; refusing to install or copy binaries in dry-run mode."
  fi
  log "llama-server missing in /opt/noemaforge/bin; searching local disks/share."
  local cand=""
  cand="$(find "$SHARE_ROOT" /srv /home/cat -type f -name 'llama-server' -perm -111 -print -quit 2>/dev/null || true)"
  if [[ -n "$cand" ]]; then install -m 0755 "$cand" /opt/noemaforge/bin/llama-server; log "Installed llama-server from: $cand"; return 0; fi
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
  [[ "$SOFT_HEADLESS" == "1" ]] || return 0
  if [[ "$DRY_RUN" == "1" ]]; then
    log "Dry-run requested; skipping soft headless switch."
    return 0
  fi
  log "Preparation checks passed; switching to soft headless mode before runtime start."
  log "GNOME/display-manager will be stopped, but packages remain installed. Restore later with: sudo noemaforge headless off"
  /opt/noemaforge/tools/prep/noemaforge-headless.sh on --reason first-start
}

run_firstboot_orchestrator() {
  local safe_shortlist="/var/lib/noemaforge/bootstrap/noemaforge-firstboot-shortlist.safe.txt"
  local args=(--share-root "$SHARE_ROOT" --vault-root "$VAULT_ROOT" --candidate-limit "$CANDIDATE_LIMIT" --top-k "$TOP_K" --shortlist-file "$safe_shortlist" --selection-mode "$SELECTION_MODE" --composite-top-n "$COMPOSITE_TOP_N")
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
    echo "share_root=$SHARE_ROOT"; echo "vault_root=$VAULT_ROOT"; echo "top_k=$TOP_K"; echo "candidate_limit=$CANDIDATE_LIMIT"; echo "soft_headless=$SOFT_HEADLESS"; echo "selection_mode=$SELECTION_MODE"; echo "composite_top_n=$COMPOSITE_TOP_N"; echo "dry_run=$DRY_RUN"; echo "per_model_timeout=$PER_MODEL_TIMEOUT"; echo "total_timeout=$TOTAL_TIMEOUT"; echo "include_unverified=$INCLUDE_UNVERIFIED"; echo "retry_failed_models=$RETRY_FAILED_MODELS"; echo "clear_model_health=$CLEAR_MODEL_HEALTH"; echo "strict_any_fail=$STRICT_ANY_FAIL"
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
