#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge_validation_logger.sh
# Zone: release/package
# Version: 0.32.1
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Provide NoemaForge release functionality for the packaged local runtime.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
# NoemaForge 0.32.1 target-machine validation logger.
# Run after installing NoemaForge 0.32.1. It collects command output, GUI/API
# smoke results, selected NoemaForge state artifacts and a tar.gz bundle.
set -u -o pipefail

TS="$(date +%Y%m%d-%H%M%S)"
LOGROOT="${NOEMAFORGE_LOG_ROOT:-$HOME/noemaforge-03113-logs}"
LOGDIR="$LOGROOT/run-$TS"
CMDLOG="$LOGDIR/cmd"
APILOG="$LOGDIR/api"
STATEHOME="${NOEMAFORGE_STATE_HOME:-$HOME/.local/state/noemaforge-03113-validation}"
PORT="${NOEMAFORGE_TEST_PORT:-8765}"
mkdir -p "$CMDLOG" "$APILOG" "$STATEHOME"
test -n "$LOGDIR" && test -n "$STATEHOME"
test -d "$LOGDIR" && test -d "$STATEHOME"

exec > >(tee -a "$LOGDIR/session.log") 2>&1
PS4='+ [${SECONDS}s] ${BASH_SOURCE##*/}:${LINENO}: '
set -x

run_capture() {
  local name="$1"; shift
  local out="$CMDLOG/${name}.out"
  local rcfile="$CMDLOG/${name}.rc"
  echo
  echo "===== $name ====="
  echo "CMD: $*"
  "$@" >"$out" 2>&1
  local rc=$?
  printf '%s\n' "$rc" >"$rcfile"
  sed -n '1,240p' "$out" || true
  echo "RC: $rc"
  return 0
}

pretty_json_file() {
  local file="$1"
  python3 -m json.tool "$file" >"$file.pretty" 2>/dev/null || true
}

api_get() {
  local name="$1" endpoint="$2"
  local out="$APILOG/${name}.json"
  echo
  echo "===== API GET $endpoint ====="
  curl -fsS --max-time 120 "http://127.0.0.1:${PORT}${endpoint}" >"$out" 2>"$out.stderr"
  local rc=$?
  echo "$rc" >"$out.rc"
  pretty_json_file "$out"
  sed -n '1,180p' "$out.pretty" 2>/dev/null || sed -n '1,180p' "$out" || true
  echo "RC: $rc"
  return 0
}

api_post_file() {
  local name="$1" endpoint="$2" payload="$3"
  local out="$APILOG/${name}.json"
  echo
  echo "===== API POST $endpoint ====="
  echo "PAYLOAD: $payload"
  curl -fsS --max-time 180 -H 'Content-Type: application/json' -d "@$payload" "http://127.0.0.1:${PORT}${endpoint}" >"$out" 2>"$out.stderr"
  local rc=$?
  echo "$rc" >"$out.rc"
  pretty_json_file "$out"
  sed -n '1,220p' "$out.pretty" 2>/dev/null || sed -n '1,220p' "$out" || true
  echo "RC: $rc"
  return 0
}

make_payload() {
  local file="$1"; shift
  python3 - "$file" "$@" <<'PY'
import json, sys
out = sys.argv[1]
mode = sys.argv[2]
if mode == "admin_greeting":
    data = {"message": "Првиет!", "execute": True, "allow_degraded": True, "prepare_media": True, "locale": "ru"}
elif mode == "admin_code":
    data = {"message": "доработай код через dev team", "execute": True, "allow_degraded": True, "locale": "ru"}
elif mode == "admin_music":
    data = {"message": "создай музыку для приветственного демо NoemaForge", "execute": True, "allow_degraded": True, "prepare_media": True, "locale": "ru"}
elif mode == "admin_modify_pipeline_dry":
    data = {"pipeline": "dev_pipeline_member_cells", "add_stage": "gui_operator_review", "before": "review", "apply": False}
elif mode == "dev_write":
    project = sys.argv[3]
    data = {"project": project, "path": "README.md", "content": "# NoemaForge Dev Team GUI test\n\nstatus=created-by-gui-api\n", "apply": True}
elif mode == "dev_replace":
    project = sys.argv[3]
    data = {"project": project, "path": "README.md", "old": "status=created-by-gui-api", "new": "status=modified-by-dev-team", "once": True, "apply": True}
elif mode == "dev_set_version":
    project = sys.argv[3]
    data = {"project": project, "version": "0.32.1-gui-test", "apply": True}
elif mode == "model_evolution":
    data = {"request": "проведи эволюцию модели для ревью кода", "target_role": "dev.work/dev", "apply": True}
elif mode == "model_selection":
    data = {"request": "проведи оптимизацию используемой модели normal для dev team сначала покажи кандидатов", "mode": "normal", "scope": "dev team", "composite_top_n": 0, "apply": False}
elif mode == "shutdown":
    data = {}
else:
    raise SystemExit(f"unknown payload mode: {mode}")
with open(out, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False)
    f.write("\n")
PY
}

# Operator-writable runtime state for GUI/API scenario.
export XDG_STATE_HOME="$STATEHOME/xdg"
export NOEMAFORGE_PIPELINE_STATE="$STATEHOME/pipelines"
export NOEMAFORGE_PERSONA_STATE="$STATEHOME/personas"
export NOEMAFORGE_MODEL_EVOLUTION_STATE="$STATEHOME/model-evolution"
export NOEMAFORGE_MODEL_SELECTION_STATE="$STATEHOME/model-selection"
export NOEMAFORGE_DEV_TEAM_STATE="$STATEHOME/dev-team"
mkdir -p "$XDG_STATE_HOME" "$NOEMAFORGE_PIPELINE_STATE" "$NOEMAFORGE_PERSONA_STATE" "$NOEMAFORGE_MODEL_EVOLUTION_STATE" "$NOEMAFORGE_MODEL_SELECTION_STATE" "$NOEMAFORGE_DEV_TEAM_STATE"

# Basic machine and package checks.
run_capture 00-date date -Is
run_capture 01-uname uname -a
run_capture 02-os-release bash -lc 'cat /etc/os-release 2>/dev/null || true'
run_capture 03-which-noemaforge bash -lc 'command -v noemaforge; readlink -f "$(command -v noemaforge)" 2>/dev/null || true'
run_capture 04-noemaforge-version noemaforge version
run_capture 05-noemaforge-help bash -lc 'noemaforge help | sed -n "1,220p"'
run_capture 06-version-audit noemaforge version-audit --json
run_capture 07-consistency-audit noemaforge consistency-audit --json
run_capture 08-pipeline-validate noemaforge pipeline validate
run_capture 09-persona-gui noemaforge persona gui-status --json
run_capture 10-multimodal-status noemaforge multimodal status --json
run_capture 11-first-run-summary timeout 300 noemaforge first-run --summary --json
run_capture 12-first-run-failed timeout 300 noemaforge first-run --failed --reboot-ready
run_capture 13-first-start-help bash -lc 'noemaforge first-start --help | sed -n "1,220p"'
run_capture 14-model-selection-plan noemaforge model-selection plan --mode normal --scope 'dev team' --request 'оптимизируй модель' --json
run_capture 15-localized-user-docs bash -lc 'for loc in en ru uk es de pt it zh-CN ja ko; do for f in README.md HOW2START.md RELEASE_NOTES.md USER_GUIDE.md; do test -f /usr/local/share/noemaforge/docs/i18n/$loc/$f || test -f /opt/noemaforge/../docs/i18n/$loc/$f || exit 1; done; done; echo localized-docs-ok'
if [[ "${NOEMAFORGE_RUN_FIRST_START_DRYRUN:-0}" == "1" ]]; then
  run_capture 16-first-start-normal-dry-run sudo noemaforge first-start --normal --dry-run --show-candidates
else
  echo "NOEMAFORGE_RUN_FIRST_START_DRYRUN=0: skipped heavy first-start dry-run candidate selection" | tee "$CMDLOG/16-first-start-normal-dry-run.skipped"
fi

# Admin CLI route smoke.
run_capture 20-admin-route-greeting noemaforge admin route --message 'Првиет!' --json
run_capture 21-admin-route-code noemaforge admin route --message 'доработай код через dev team' --json
run_capture 22-admin-route-music noemaforge admin route --message 'создай музыку для демо' --json
run_capture 23-admin-route-evolution noemaforge admin route --message 'проведи эволюцию модели для ревью кода' --json
run_capture 24-admin-route-model-selection noemaforge admin route --message 'проведи оптимизацию используемой модели normal для dev team' --json
run_capture 25-admin-route-music-greeting-regression noemaforge admin route --message 'создай музыку для приветственного демо NoemaForge' --json
run_capture 26-admin-message-code-clarify noemaforge admin message --message 'доработай код через dev team' --execute --allow-degraded --json
run_capture 27-model-evolution-cli noemaforge model-evolution run --request 'проведи эволюцию модели для ревью кода' --target-role dev.work/dev --apply --json

# Start Admin GUI/API.
run_capture 30-dashboard-stop-before noemaforge dashboard stop
run_capture 31-dashboard-start noemaforge gui console start --port "$PORT"

READY=0
for i in $(seq 1 120); do
  if curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/api/health" >"$APILOG/health-ready.json" 2>"$APILOG/health-ready.stderr"; then
    READY=1
    break
  fi
  sleep 1
done
printf '%s\n' "$READY" >"$APILOG/health-ready.flag"
pretty_json_file "$APILOG/health-ready.json"
sed -n '1,120p' "$APILOG/health-ready.json.pretty" 2>/dev/null || true

if [[ "$READY" == "1" ]]; then
  api_get 40-health /api/health
  api_get 41-state-before /api/state
  api_get 41b-locales /api/locales

  make_payload "$APILOG/payload-admin-greeting.json" admin_greeting
  api_post_file 42-admin-greeting /api/admin/message "$APILOG/payload-admin-greeting.json"

  make_payload "$APILOG/payload-admin-code.json" admin_code
  api_post_file 43-admin-code /api/admin/message "$APILOG/payload-admin-code.json"

  make_payload "$APILOG/payload-admin-music.json" admin_music
  api_post_file 44-admin-music /api/admin/message "$APILOG/payload-admin-music.json"

  make_payload "$APILOG/payload-admin-modify-pipeline-dry.json" admin_modify_pipeline_dry
  api_post_file 45-admin-modify-pipeline-dry /api/admin/modify-pipeline "$APILOG/payload-admin-modify-pipeline-dry.json"

  TEST_PROJECT="$STATEHOME/test-project"
  mkdir -p "$TEST_PROJECT"
  printf '0.32.1-gui-test-before\n' > "$TEST_PROJECT/VERSION"

  make_payload "$APILOG/payload-dev-write.json" dev_write "$TEST_PROJECT"
  api_post_file 46-dev-write-file /api/dev-team/write-file "$APILOG/payload-dev-write.json"

  make_payload "$APILOG/payload-dev-replace.json" dev_replace "$TEST_PROJECT"
  api_post_file 47-dev-replace /api/dev-team/replace "$APILOG/payload-dev-replace.json"

  make_payload "$APILOG/payload-dev-set-version.json" dev_set_version "$TEST_PROJECT"
  api_post_file 48-dev-set-version /api/dev-team/set-version "$APILOG/payload-dev-set-version.json"

  make_payload "$APILOG/payload-model-evolution.json" model_evolution
  api_post_file 49-model-evolution /api/model-evolution/run "$APILOG/payload-model-evolution.json"

  make_payload "$APILOG/payload-model-selection.json" model_selection
  api_post_file 50-model-selection /api/model-selection/plan "$APILOG/payload-model-selection.json"

  api_get 51-state-after /api/state

  make_payload "$APILOG/payload-shutdown.json" shutdown
  api_post_file 52-shutdown /api/shutdown "$APILOG/payload-shutdown.json"
  sleep 2
fi

run_capture 52-dashboard-status-after noemaforge dashboard status

# Optional privileged pipeline overlay write. Disabled by default because it
# writes /opt/noemaforge/configs/pipelines.local.json.
if [[ "${NOEMAFORGE_RUN_SUDO_APPLY:-0}" == "1" ]]; then
  run_capture 60-sudo-admin-modify-pipeline-apply sudo noemaforge admin modify-pipeline dev_pipeline_member_cells --add-stage gui_operator_review --before review --apply --json
  run_capture 61-pipeline-validate-after-sudo-apply noemaforge pipeline validate
else
  echo "NOEMAFORGE_RUN_SUDO_APPLY=0: skipped privileged admin modify-pipeline --apply test" | tee "$CMDLOG/60-sudo-admin-modify-pipeline-apply.skipped"
fi

# Collect service/system state. Use non-interactive sudo only to avoid blocking.
run_capture 70-systemctl-noemaforge bash -lc 'systemctl list-units "noemaforge*" --all --no-pager 2>/dev/null || true'
if command -v journalctl >/dev/null 2>&1; then
  if sudo -n true 2>/dev/null; then
    run_capture 71-journal-noemaforge sudo journalctl --no-pager --since '24 hours ago' -u noemaforge-autostart-gui.service -u noemaforge-autostart-gui.timer -u noemaforge-autostart-wogui.service -u noemaforge-shutdown-stop.service
  else
    run_capture 71-journal-noemaforge-nosudo journalctl --no-pager --since '24 hours ago' -u noemaforge-autostart-gui.service -u noemaforge-autostart-gui.timer -u noemaforge-autostart-wogui.service -u noemaforge-shutdown-stop.service
  fi
fi

# Copy dashboard log and selected state paths.
mkdir -p "$LOGDIR/state-copy"
cp -a "$XDG_STATE_HOME/noemaforge/dashboard.log" "$LOGDIR/dashboard.log" 2>/dev/null || true
find "$STATEHOME" -maxdepth 5 -type f -size -5M -print > "$LOGDIR/state-files.txt" 2>/dev/null || true
# Store a compact state bundle separately inside logdir.
tar -C "$STATEHOME" -czf "$LOGDIR/state-home-snapshot.tar.gz" . 2>/dev/null || true

# Final bundle.
BUNDLE="$LOGROOT/noemaforge_03113_patched10_debug_bundle_${TS}.tar.gz"
tar -C "$LOGROOT" -czf "$BUNDLE" "$(basename "$LOGDIR")"
set +x
echo
echo "NoemaForge 0.32.1 pre-alpha validation log bundle: $BUNDLE"
echo "Attach this tar.gz if something failed or looked wrong. Avoid adding secrets/tokens to the log directory before sending."
