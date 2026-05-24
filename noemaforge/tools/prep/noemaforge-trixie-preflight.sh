#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/prep/noemaforge-trixie-preflight.sh
# Zone: prep/trixie-launcher
# Purpose: Fast launcher preflight for Debian Trixie NoemaForge hosts.
# Safety: Read-only by default; emits JSON when --json is supplied; package remediation requires explicit apply gates.
# === End NoemaForge File Header ===
set -euo pipefail

JSON=0
STRICT=0
REQUIRE_RUNNING=0
SKIP_MODELSTORE=0
REMEDIATION_PLAN=0
APPLY_REMEDIATION=0
REMEDIATION_YES=0
FORENSICS_OUT=""
MODELSTORE_TIMEOUT="${NOEMAFORGE_PREFLIGHT_MODELSTORE_TIMEOUT:-8}"
ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
SHARE="${NOEMAFORGE_SHARE:-/mnt/noemaforge-share}"
DATASET="${NOEMAFORGE_ROLE_EVAL_DATASET:-/opt/noemaforge/datasets/role_eval_cases}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) JSON=1; shift ;;
    --strict) STRICT=1; shift ;;
    --require-running) REQUIRE_RUNNING=1; shift ;;
    --skip-modelstore) SKIP_MODELSTORE=1; shift ;;
    --remediation-plan) REMEDIATION_PLAN=1; shift ;;
    --apply-remediation) APPLY_REMEDIATION=1; REMEDIATION_PLAN=1; shift ;;
    --yes|--yes-i-understand-package-manager-changes) REMEDIATION_YES=1; shift ;;
    --root) ROOT="$2"; shift 2 ;;
    --share) SHARE="$2"; shift 2 ;;
    --dataset) DATASET="$2"; shift 2 ;;
    --forensics-out) FORENSICS_OUT="$2"; shift 2 ;;
    --modelstore-timeout) MODELSTORE_TIMEOUT="$2"; shift 2 ;;
    -h|--help|help)
      cat <<'EOH'
Usage: noemaforge-trixie-preflight.sh [--json] [--strict] [--require-running]
                                  [--root PATH] [--share PATH]
                                  [--dataset PATH] [--forensics-out DIR]
                                  [--modelstore-timeout SECONDS]
                                  [--remediation-plan]
                                  [--apply-remediation --yes-i-understand-package-manager-changes]

Checks:
  - Debian Trixie host hint
  - canonical share mount /mnt/noemaforge-share
  - canonical Vault path under the share
  - role eval dataset directory, including bundled fallback hint
  - llama launcher and llama-server executable
  - llama shared-library visibility through ldd
  - ModelStore GGUF shard safety unless --skip-modelstore is supplied
  - optional gateway/backend/toolproxy sockets when --require-running is used
  - distro family, package manager and missing dependency remediation plan

This preflight is read-only unless --apply-remediation is supplied together
with --yes-i-understand-package-manager-changes and
NOEMAFORGE_ALLOW_PACKAGE_REMEDIATION=1.  Use --forensics-out DIR to write a
small support bundle when a check fails or warns.
EOH
      exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

PASS=0
WARN=0
FAIL=0
RESULTS=()
check() {
  local id="$1" status="$2" message="$3"
  RESULTS+=("$id|$status|$message")
  case "$status" in
    pass) PASS=$((PASS+1)) ;;
    warn) WARN=$((WARN+1)) ;;
    fail) FAIL=$((FAIL+1)) ;;
    *) FAIL=$((FAIL+1)) ;;
  esac
}

is_mounted() { findmnt "$1" >/dev/null 2>&1; }

noemaforge_detect_distro_family() {
  local id_like
  id_like=" ${OS_ID,,} ${OS_ID_LIKE,,} "
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
    debian) printf 'apt-get\n' ;;
    fedora) if command -v dnf >/dev/null 2>&1; then printf 'dnf\n'; else printf 'yum\n'; fi ;;
    arch) printf 'pacman\n' ;;
    suse) printf 'zypper\n' ;;
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

noemaforge_missing_dependency_commands() {
  local cmd
  local missing=()
  for cmd in jq curl git rsync python3 bwrap ffmpeg v4l2-ctl cmake go findmnt systemctl; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  local IFS=,
  printf '%s' "${missing[*]:-}"
}

noemaforge_remediation_install_command() {
  local manager="$1" packages="$2"
  case "$manager" in
    apt-get) printf 'DEBIAN_FRONTEND=noninteractive apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y %s\n' "$packages" ;;
    dnf|yum) printf '%s install -y %s\n' "$manager" "$packages" ;;
    pacman) printf 'pacman -Sy --noconfirm %s\n' "$packages" ;;
    zypper) printf 'zypper --non-interactive refresh && zypper --non-interactive install %s\n' "$packages" ;;
    *) printf '\n' ;;
  esac
}

noemaforge_apply_remediation() {
  [[ "$APPLY_REMEDIATION" == "1" ]] || return 0
  if [[ "$REMEDIATION_YES" != "1" ]]; then
    check remediation_apply fail "--apply-remediation requires --yes-i-understand-package-manager-changes"
    return 0
  fi
  if [[ "${NOEMAFORGE_ALLOW_PACKAGE_REMEDIATION:-0}" != "1" ]]; then
    check remediation_apply fail "--apply-remediation requires NOEMAFORGE_ALLOW_PACKAGE_REMEDIATION=1"
    return 0
  fi
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    check remediation_apply fail "--apply-remediation requires root privileges"
    return 0
  fi
  if [[ -z "$PACKAGE_MANAGER" || -z "$REMEDIATION_PACKAGES" ]]; then
    check remediation_apply fail "no supported remediation package manager for distro_family=${DISTRO_FAMILY}"
    return 0
  fi
  if ! command -v "$PACKAGE_MANAGER" >/dev/null 2>&1; then
    check remediation_apply fail "package manager not found: $PACKAGE_MANAGER"
    return 0
  fi
  case "$PACKAGE_MANAGER" in
    apt-get)
      DEBIAN_FRONTEND=noninteractive apt-get update -y
      DEBIAN_FRONTEND=noninteractive apt-get install -y $REMEDIATION_PACKAGES
      ;;
    dnf|yum)
      "$PACKAGE_MANAGER" install -y $REMEDIATION_PACKAGES
      ;;
    pacman)
      pacman -Sy --noconfirm $REMEDIATION_PACKAGES
      ;;
    zypper)
      zypper --non-interactive refresh
      zypper --non-interactive install $REMEDIATION_PACKAGES
      ;;
    *)
      check remediation_apply fail "unsupported package manager for apply: $PACKAGE_MANAGER"
      return 0
      ;;
  esac
  check remediation_apply pass "package remediation completed with $PACKAGE_MANAGER"
}

OS_CODENAME=""
OS_VERSION=""
OS_ID=""
OS_ID_LIKE=""
OS_PRETTY=""
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  OS_ID="${ID:-}"
  OS_ID_LIKE="${ID_LIKE:-}"
  OS_PRETTY="${PRETTY_NAME:-}"
  OS_CODENAME="${VERSION_CODENAME:-}"
  OS_VERSION="${VERSION_ID:-}"
fi
DISTRO_FAMILY="$(noemaforge_detect_distro_family)"
PACKAGE_MANAGER="$(noemaforge_package_manager_for_family "$DISTRO_FAMILY")"
REMEDIATION_PACKAGES="$(noemaforge_packages_for_family "$DISTRO_FAMILY")"
MISSING_COMMANDS="$(noemaforge_missing_dependency_commands)"
REMEDIATION_INSTALL_COMMAND="$(noemaforge_remediation_install_command "$PACKAGE_MANAGER" "$REMEDIATION_PACKAGES")"

if [[ "$OS_CODENAME" == "trixie" || "$OS_VERSION" == "13" ]]; then
  check os pass "Debian Trixie detected or compatible VERSION_ID=13"
else
  check os warn "host is not clearly Debian Trixie; detected codename=${OS_CODENAME:-unknown} version=${OS_VERSION:-unknown}"
fi
case "$DISTRO_FAMILY" in
  debian|fedora|arch|suse)
    if [[ -n "$PACKAGE_MANAGER" ]]; then
      check distro_remediation pass "distro_family=$DISTRO_FAMILY package_manager=$PACKAGE_MANAGER missing_commands=${MISSING_COMMANDS:-none}"
    else
      check distro_remediation warn "distro_family=$DISTRO_FAMILY has no package manager command available"
    fi
    ;;
  *)
    check distro_remediation warn "unsupported distro remediation family for ID=${OS_ID:-unknown} ID_LIKE=${OS_ID_LIKE:-unknown}"
    ;;
esac
noemaforge_apply_remediation

if [[ -d "$SHARE" ]] && is_mounted "$SHARE"; then
  check mount pass "$SHARE is mounted"
else
  alt_count=0
  if [[ -d /media ]]; then
    alt_count=$(find /media -maxdepth 3 -type d \( -iname '*noemaforge*' -o -iname '*Vault*' \) 2>/dev/null | wc -l | tr -d ' ')
  fi
  if [[ "$alt_count" -gt 0 ]]; then
    check mount warn "$SHARE is not mounted; possible desktop automount candidates exist under /media; normalize to /mnt/noemaforge-share"
  else
    check mount fail "$SHARE is not mounted"
  fi
fi

if [[ -d "$SHARE/noemaforge-lab/data/Vault" ]]; then
  check vault pass "canonical Vault exists at $SHARE/noemaforge-lab/data/Vault"
elif [[ -d "$SHARE/Vault" ]]; then
  check vault warn "legacy Vault exists at $SHARE/Vault; prefer $SHARE/noemaforge-lab/data/Vault"
else
  check vault warn "canonical Vault path not found under $SHARE"
fi

if [[ -d "$DATASET" ]]; then
  check datasets pass "role_eval_cases dataset directory exists at $DATASET"
elif [[ -d "$ROOT/datasets/role_eval_cases" ]]; then
  check datasets warn "dataset is bundled at $ROOT/datasets/role_eval_cases but not installed at $DATASET"
else
  check datasets fail "missing role_eval_cases dataset at $DATASET"
fi

[[ -x "$ROOT/bin/noemaforge-llama-start" || -x /opt/noemaforge/bin/noemaforge-llama-start ]] \
  && check llama_start pass 'noemaforge-llama-start is executable' \
  || check llama_start fail 'missing executable noemaforge-llama-start'

LLAMA_BIN="$ROOT/bin/llama-server"
[[ -x "$LLAMA_BIN" ]] || LLAMA_BIN="/opt/noemaforge/bin/llama-server"
[[ -x "$LLAMA_BIN" ]] \
  && check llama_server pass "llama-server is executable at $LLAMA_BIN" \
  || check llama_server fail 'missing executable llama-server'

if [[ -x "$LLAMA_BIN" ]] && command -v ldd >/dev/null 2>&1; then
  if ldd "$LLAMA_BIN" 2>/dev/null | grep -q 'not found'; then
    check llama_libs fail 'llama-server has unresolved shared libraries'
  else
    check llama_libs pass 'llama-server shared libraries resolve'
  fi
elif [[ -x "$LLAMA_BIN" ]]; then
  check llama_libs warn 'ldd unavailable; cannot inspect llama-server shared libraries'
else
  check llama_libs fail 'cannot inspect llama-server shared libraries'
fi

GGUF_SELECT="$ROOT/src/gguf_select.py"
[[ -x "$GGUF_SELECT" || -r "$GGUF_SELECT" ]] || GGUF_SELECT="/opt/noemaforge/src/gguf_select.py"
MODELSTORE_REPORT="${NOEMAFORGE_PREFLIGHT_MODELSTORE_REPORT:-}"
if [[ -z "$MODELSTORE_REPORT" ]]; then
  if [[ -w /var/lib/noemaforge/bootstrap || ( ! -e /var/lib/noemaforge/bootstrap && -w /var/lib/noemaforge ) ]]; then
    MODELSTORE_REPORT="/var/lib/noemaforge/bootstrap/modelstore-validation.safe.json"
  else
    MODELSTORE_REPORT="${XDG_STATE_HOME:-$HOME/.local/state}/noemaforge/modelstore-validation.safe.json"
  fi
fi
MODELSTORE_STDERR="${MODELSTORE_REPORT}.stderr"
if [[ "$SKIP_MODELSTORE" == "1" ]]; then
  check modelstore warn 'ModelStore GGUF shard validation skipped by operator/test flag'
elif [[ -r "$GGUF_SELECT" ]]; then
  mkdir -p "$(dirname "$MODELSTORE_REPORT")" 2>/dev/null || true
  if command -v timeout >/dev/null 2>&1; then
    MODELSTORE_CMD=(timeout "$MODELSTORE_TIMEOUT" python3 "$GGUF_SELECT" validate-modelstore --root /var/lib/modelstore --json-out "$MODELSTORE_REPORT")
  else
    MODELSTORE_CMD=(python3 "$GGUF_SELECT" validate-modelstore --root /var/lib/modelstore --json-out "$MODELSTORE_REPORT")
  fi
  MODELSTORE_OUT="$("${MODELSTORE_CMD[@]}" 2>"$MODELSTORE_STDERR" || true)"
  rc=0
  if [[ -s "$MODELSTORE_REPORT" ]]; then
    if python3 - "$MODELSTORE_REPORT" <<'PYMS'
import json, sys
try:
    obj=json.load(open(sys.argv[1], encoding='utf-8'))
    sys.exit(0 if obj.get('ok') else 1)
except Exception:
    sys.exit(2)
PYMS
    then
      check modelstore pass "ModelStore GGUF shard safety validated; report=$MODELSTORE_REPORT"
    else
      rc=$?
      detail="$(python3 - "$MODELSTORE_REPORT" <<'PYMS' 2>/dev/null || true
import json, sys
obj=json.load(open(sys.argv[1], encoding='utf-8'))
print(obj.get('reason') or obj.get('message') or obj.get('error') or 'report ok=false')
unsafe=obj.get('unsafe') or obj.get('problems') or []
if unsafe: print('unsafe/probs:', unsafe[:3] if isinstance(unsafe, list) else unsafe)
PYMS
)"
      check modelstore fail "ModelStore GGUF shard validation failed; report=$MODELSTORE_REPORT; detail=${detail:-unknown}; stderr=$(tail -c 500 "$MODELSTORE_STDERR" 2>/dev/null || true)"
    fi
  else
    # Command failed before report creation, often because /var/lib path was not writable.
    rc=1
    if [[ -n "$MODELSTORE_OUT" ]]; then
      printf '%s\n' "$MODELSTORE_OUT" > "${MODELSTORE_REPORT}.stdout" 2>/dev/null || true
    fi
    if [[ "$MODELSTORE_OUT" == *'"ok": true'* ]]; then
      check modelstore pass "ModelStore GGUF shard safety validated via stdout fallback; report_path_unwritable=$MODELSTORE_REPORT"
    elif [[ -s "$MODELSTORE_STDERR" ]]; then
      check modelstore fail "ModelStore validation produced no report at $MODELSTORE_REPORT; stderr=$(tail -c 800 "$MODELSTORE_STDERR" 2>/dev/null || true)"
    else
      check modelstore fail "ModelStore GGUF shard validation failed or ModelStore is missing; no report at $MODELSTORE_REPORT"
    fi
  fi
else
  check modelstore fail 'missing gguf_select.py'
fi

if [[ "$REQUIRE_RUNNING" == "1" ]]; then
  [[ -S /run/noemaforge/llm/gateway.sock ]] && check gateway pass 'gateway socket exists' || check gateway fail 'gateway socket missing'
  [[ -S /run/noemaforge/llm/backends/main.sock ]] && check main_backend pass 'main backend socket exists' || check main_backend fail 'main backend socket missing'
  [[ -S /run/noemaforge/toolproxy.sock ]] && check toolproxy pass 'ToolProxy socket exists' || check toolproxy fail 'ToolProxy socket missing'
fi

if [[ "$STRICT" == "1" && "$WARN" -gt 0 ]]; then
  FAIL=$((FAIL+WARN))
fi

if [[ -n "$FORENSICS_OUT" && ( "$FAIL" -gt 0 || "$WARN" -gt 0 ) ]]; then
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  BUNDLE="$FORENSICS_OUT/trixie-preflight-$STAMP"
  mkdir -p "$BUNDLE"
  printf '%s\n' "root=$ROOT" "share=$SHARE" "dataset=$DATASET" > "$BUNDLE/inputs.txt"
  findmnt > "$BUNDLE/findmnt.txt" 2>&1 || true
  systemctl --failed --no-pager > "$BUNDLE/systemctl-failed.txt" 2>&1 || true
  systemctl is-enabled noemaforge-modelscan.timer noemaforge-llm-backends-manager.timer > "$BUNDLE/timer-enabled.txt" 2>&1 || true
  ls -lah /run/noemaforge /run/noemaforge/llm /run/noemaforge/llm/backends > "$BUNDLE/run-noemaforge.txt" 2>&1 || true
  tar -C "$FORENSICS_OUT" -czf "$BUNDLE.tar.gz" "$(basename "$BUNDLE")" 2>/dev/null || true
fi

if [[ "$JSON" == "1" ]]; then
  python3 - "$PASS" "$WARN" "$FAIL" "$STRICT" "$ROOT" "$SHARE" "$DATASET" "$OS_ID" "$OS_ID_LIKE" "$OS_PRETTY" "$OS_VERSION" "$OS_CODENAME" "$DISTRO_FAMILY" "$PACKAGE_MANAGER" "$REMEDIATION_PACKAGES" "$MISSING_COMMANDS" "$REMEDIATION_INSTALL_COMMAND" "$APPLY_REMEDIATION" "$REMEDIATION_PLAN" "${RESULTS[@]}" <<'PY'
import json, sys
passed=int(sys.argv[1]); warned=int(sys.argv[2]); failed=int(sys.argv[3]); strict=bool(int(sys.argv[4]))
root, share, dataset = sys.argv[5], sys.argv[6], sys.argv[7]
os_id, os_id_like, os_pretty, os_version, os_codename = sys.argv[8], sys.argv[9], sys.argv[10], sys.argv[11], sys.argv[12]
distro_family, package_manager = sys.argv[13], sys.argv[14]
packages, missing_commands, install_command = sys.argv[15], sys.argv[16], sys.argv[17]
apply_remediation, remediation_plan = bool(int(sys.argv[18])), bool(int(sys.argv[19]))
checks=[]
for raw in sys.argv[20:]:
    cid,status,msg=raw.split('|',2)
    checks.append({'id':cid,'status':status,'ok':status == 'pass','message':msg})
print(json.dumps({
    'ok': failed == 0,
    'strict': strict,
    'passed': passed,
    'warned': warned,
    'failed': failed,
    'root': root,
    'share': share,
    'dataset': dataset,
    'distro': {
        'id': os_id,
        'id_like': os_id_like,
        'pretty_name': os_pretty,
        'version_id': os_version,
        'codename': os_codename,
        'family': distro_family,
        'package_manager': package_manager,
    },
    'remediation': {
        'plan_requested': remediation_plan,
        'apply_requested': apply_remediation,
        'supported': bool(package_manager and packages),
        'package_manager': package_manager,
        'packages': packages.split(),
        'missing_commands': [item for item in missing_commands.split(',') if item],
        'install_command': install_command,
    },
    'checks': checks,
}, ensure_ascii=False, indent=2))
PY
else
  for raw in "${RESULTS[@]}"; do
    IFS='|' read -r id status msg <<<"$raw"
    printf '[%s] %s: %s\n' "$status" "$id" "$msg"
  done
  if [[ "$REMEDIATION_PLAN" == "1" ]]; then
    printf 'remediation: distro_id=%s family=%s package_manager=%s missing_commands=%s\n' "${OS_ID:-unknown}" "${DISTRO_FAMILY:-unknown}" "${PACKAGE_MANAGER:-none}" "${MISSING_COMMANDS:-none}"
    if [[ -n "$REMEDIATION_INSTALL_COMMAND" ]]; then
      printf 'remediation_install_command: %s\n' "$REMEDIATION_INSTALL_COMMAND"
    else
      printf 'remediation_install_command: unsupported distro family; install manually after reviewing docs\n'
    fi
  fi
  printf 'summary: pass=%s warn=%s fail=%s strict=%s\n' "$PASS" "$WARN" "$FAIL" "$STRICT"
fi

[[ "$FAIL" -eq 0 ]]
