#!/usr/bin/env bash
set -Eeuo pipefail

# NoemaForge 0.33.0 Codex prod-ready local runner
#
# Usage:
#   cd ~/src/NoemaForge
#   bash ~/Downloads/run_codex_033_prod_ready_loop.sh
#
# Optional:
#   MAX_CYCLES=20 bash ~/Downloads/run_codex_033_prod_ready_loop.sh
#   BASE_BRANCH=release/0.33.0-dev bash ~/Downloads/run_codex_033_prod_ready_loop.sh
#   ALLOW_GH_WRITE=0 bash ~/Downloads/run_codex_033_prod_ready_loop.sh
#
# Safety defaults:
# - does not start NoemaForge services;
# - does not enable systemd units;
# - does not start heavy LLM;
# - Codex works on code/docs/tests only.

REPO="${REPO:-$HOME/src/NoemaForge}"
GH_REPO="${GH_REPO:-Sinev-Maksim/NoemaForge}"
BASE_BRANCH="${BASE_BRANCH:-release/0.33.0-dev}"
WORK_BRANCH="${WORK_BRANCH:-codex/0.33.0-prod-ready-loop}"
ISSUES="${ISSUES:-212 213 214 215 216 217 218 219 220 221}"
UMBRELLA_ISSUE="${UMBRELLA_ISSUE:-221}"

MAX_CYCLES="${MAX_CYCLES:-6}"
ALLOW_GH_WRITE="${ALLOW_GH_WRITE:-1}"
ALLOW_PUSH="${ALLOW_PUSH:-1}"
ALLOW_PR="${ALLOW_PR:-1}"

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
PAUSE_MARKER="${PAUSE_MARKER:-$CODEX_HOME/runner-pause-until.txt}"

TASK_ROOT="$REPO/.codex/tasks/0.33.0-prod-ready"
ISSUE_DIR="$TASK_ROOT/issues"
LOG_DIR="$TASK_ROOT/logs"
PROMPT_FILE="$TASK_ROOT/codex-task.md"

mkdir -p "$CODEX_HOME" "$TASK_ROOT" "$ISSUE_DIR" "$LOG_DIR"

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*" | tee -a "$LOG_DIR/runner.log"
}

die() {
  log "ERROR: $*"
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

sleep_until_if_paused() {
  if [[ ! -s "$PAUSE_MARKER" ]]; then
    return 0
  fi

  local until_raw now_ts until_ts sleep_sec
  until_raw="$(tr -d '[:space:]' < "$PAUSE_MARKER" || true)"
  [[ -n "$until_raw" ]] || return 0

  now_ts="$(date -u +%s)"
  if until_ts="$(date -u -d "$until_raw" +%s 2>/dev/null)"; then
    if (( until_ts > now_ts )); then
      sleep_sec=$((until_ts - now_ts))
      log "Codex pause marker active until $until_raw; sleeping ${sleep_sec}s"
      sleep "$sleep_sec"
    fi
  fi

  rm -f "$PAUSE_MARKER"
}

extract_reset_time_or_fallback() {
  local logfile="$1"
  local reset

  reset="$(grep -Eio '20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z' "$logfile" | head -1 || true)"

  if [[ -n "$reset" ]]; then
    printf '%s\n' "$reset"
    return 0
  fi

  date -u -d '+1 hour' '+%Y-%m-%dT%H:%M:%SZ'
}

looks_like_rate_limit() {
  local logfile="$1"
  grep -Eiq 'rate.?limit|usage.?limit|quota|too many requests|tokens?.*(exhausted|limit)|limit.*reset|try again|retry after|429' "$logfile"
}

ensure_repo_ready() {
  need_cmd git
  cd "$REPO"

  log "repo: $REPO"
  git rev-parse --is-inside-work-tree >/dev/null || die "not a git repo: $REPO"

  log "fetching origin"
  git fetch origin --prune

  if git rev-parse --verify "$BASE_BRANCH" >/dev/null 2>&1; then
    git checkout "$BASE_BRANCH"
  else
    git checkout -B "$BASE_BRANCH" "origin/$BASE_BRANCH"
  fi

  git pull --ff-only origin "$BASE_BRANCH" || true

  if [[ -n "$(git status --porcelain)" ]]; then
    log "working tree is not clean; preserving local changes"
    git status --short | tee -a "$LOG_DIR/runner.log"
  fi

  if git rev-parse --verify "$WORK_BRANCH" >/dev/null 2>&1; then
    git checkout "$WORK_BRANCH"
    git rebase "$BASE_BRANCH" || {
      log "rebase failed; leaving branch as-is for manual inspection"
      git status --short
      exit 1
    }
  else
    git checkout -b "$WORK_BRANCH"
  fi
}

fetch_issue_context() {
  if ! command -v gh >/dev/null 2>&1; then
    log "gh not found; writing prompt without live issue bodies"
    return 0
  fi

  log "fetching GitHub issue context: $ISSUES"
  for n in $ISSUES; do
    gh issue view "$n" \
      --repo "$GH_REPO" \
      --json number,title,state,url,body,labels,comments \
      > "$ISSUE_DIR/issue-$n.json" \
      2> "$ISSUE_DIR/issue-$n.err" \
      || log "warning: failed to fetch issue #$n"
  done
}

write_prompt() {
  cat > "$PROMPT_FILE" <<'PROMPT_EOF'
You are Codex working locally in the NoemaForge repository.

Mission:
Drive NoemaForge 0.33.0 to prod-ready for the current install/re-entry hardening loop.

Primary target:
- Work from release/0.33.0-dev.
- Keep heavy LLM autostart disabled.
- Preserve max_active_llms=1.
- Preserve runtime_only semantics: gateway/toolproxy only; no main backend required.
- Do not make /opt/noemaforge mutable runtime state.
- Do not silently change boot persistence.
- Do not hide real failures as green. Expected degraded/skip states must be explicit and evidenced.

Issue set to resolve first:
- #212 installed payload loses executable bits for smoke/preflight/operator scripts.
- #213 installer installs /opt/noemaforge as invoking user and group-writable.
- #214 runtime_only smoke should not fail on intentionally missing main backend.
- #215 safe-start runtime_only mutates persistent systemd enablement despite manual boot mode.
- #216 installed systemd units rely on hotfix drop-ins and stale 0.32.1 metadata.
- #217 mvp-smoke reports failures without actionable stderr/artifact links.
- #218 pipeline catalog validation fails because media/admin pipelines reference missing media_team.
- #219 mvp-smoke lifecycle check is blocked by degraded_readonly under degraded_selected staffing.
- #220 pipeline validate emits JSON but rejects --json.
- #221 umbrella loop task.

Local evidence from re-entry:
- Trixie baseline is clean.
- runtime_only safe core starts successfully.
- /opt chmod/chown local repair confirmed install payload problems.
- pipeline validate currently fails on unknown team media_team.
- pipeline approve/advance in smoke state returns degraded_readonly under staffing_state=degraded_selected.
- pipeline validate --json currently rejects --json.
- manual boot-mode was restored by disabling gateway/toolproxy after diagnostic start.

Required work loop:
1. Inspect issue JSON files under .codex/tasks/0.33.0-prod-ready/issues/.
2. Fix all relevant source/install/test/docs problems for #212-#220.
3. Add/update tests.
4. Regenerate release manifests/checksums if this repository requires it.
5. Run focused validation.
6. If issues are fixed, update install/re-entry/operator docs.
7. Run automated recheck:
   - unit/source tests relevant to changes;
   - catalog validation;
   - noemaforge pipeline validate;
   - noemaforge pipeline validate --json if implemented;
   - mvp-smoke or test equivalent;
   - runtime_only/profile-aware smoke.
8. For newly discovered unfixed problems, create concise GitHub issues with evidence, link them from #221, and return to fixing.
9. Reconcile implementation against current 0.33.0 requirements:
   - implemented;
   - partial;
   - missing;
   - deferred;
   - safety-driven changes.
10. Convert gaps into TODO points:
   - 0.33.0 release blockers first;
   - post-0.33.0;
   - research/design;
   - target-host/manual validation.
11. Solve 0.33.0 TODOs first, then lower-priority TODOs.

Token/rate-limit behavior:
- Do not loop on repeated Codex failures.
- If rate/usage/token limit is hit, stop cleanly.
- The outer runner will write a pause marker and resume after reset/fallback time.
- Leave a compact status note in .codex/tasks/0.33.0-prod-ready/status.md.

GitHub behavior:
- If ALLOW_GH_WRITE=1, you may create/update issues/comments when new evidence is found.
- If ALLOW_PUSH=1 and tests pass, you may push the work branch.
- If ALLOW_PR=1 and a coherent change set exists, open or update a draft PR.
- Keep PRs bounded and reviewable.

Acceptance before declaring done:
- #212-#220 are fixed or explicitly closed with documented reason.
- Clean install/re-entry layout has correct /opt ownership and executable modes.
- runtime_only validation does not fail because backend is intentionally absent.
- manual boot mode remains manual unless persistence is explicitly requested.
- systemd unit surface is clean, current-versioned, and not dependent on undocumented hotfix drop-ins.
- pipeline validate passes with media/admin catalogs.
- degraded staffing behavior is intentionally represented by mvp-smoke.
- failed smoke checks include command, exit code, stdout/stderr/report paths.
- docs reflect actual operator flow.
- final recheck report is attached/linked.
- requirements reconciliation creates/updates TODOs for remaining gaps.

Start by reading:
- .codex/tasks/0.33.0-prod-ready/issues/issue-221.json
- then issue-212.json through issue-220.json
- current git status and relevant install scripts/systemd/config/test files.
PROMPT_EOF

  {
    echo
    echo "Runtime env passed by runner:"
    echo "- ALLOW_GH_WRITE=$ALLOW_GH_WRITE"
    echo "- ALLOW_PUSH=$ALLOW_PUSH"
    echo "- ALLOW_PR=$ALLOW_PR"
    echo "- GH_REPO=$GH_REPO"
    echo "- WORK_BRANCH=$WORK_BRANCH"
  } >> "$PROMPT_FILE"

  log "prompt written: $PROMPT_FILE"
}

run_codex_once() {
  need_cmd codex
  cd "$REPO"

  local cycle="$1"
  local out="$LOG_DIR/codex-cycle-$cycle.log"
  local prompt_text
  prompt_text="$(cat "$PROMPT_FILE")"

  log "starting Codex cycle $cycle"
  log "log: $out"

  set +e

  if codex exec --help >/dev/null 2>&1; then
    if codex exec --help 2>&1 | grep -q -- '--cd'; then
      ALLOW_GH_WRITE="$ALLOW_GH_WRITE" \
      ALLOW_PUSH="$ALLOW_PUSH" \
      ALLOW_PR="$ALLOW_PR" \
        codex exec --cd "$REPO" "$prompt_text" 2>&1 | tee "$out"
    elif codex exec --help 2>&1 | grep -q -- '-C'; then
      ALLOW_GH_WRITE="$ALLOW_GH_WRITE" \
      ALLOW_PUSH="$ALLOW_PUSH" \
      ALLOW_PR="$ALLOW_PR" \
        codex exec -C "$REPO" "$prompt_text" 2>&1 | tee "$out"
    else
      ALLOW_GH_WRITE="$ALLOW_GH_WRITE" \
      ALLOW_PUSH="$ALLOW_PUSH" \
      ALLOW_PR="$ALLOW_PR" \
        codex exec "$prompt_text" 2>&1 | tee "$out"
    fi
  else
    ALLOW_GH_WRITE="$ALLOW_GH_WRITE" \
    ALLOW_PUSH="$ALLOW_PUSH" \
    ALLOW_PR="$ALLOW_PR" \
      codex "$prompt_text" 2>&1 | tee "$out"
  fi

  local rc="${PIPESTATUS[0]}"
  set -e

  log "Codex cycle $cycle exit code: $rc"

  if (( rc != 0 )); then
    if looks_like_rate_limit "$out"; then
      local reset
      reset="$(extract_reset_time_or_fallback "$out")"
      printf '%s\n' "$reset" > "$PAUSE_MARKER"
      log "rate/token limit detected; wrote pause marker: $PAUSE_MARKER => $reset"
      return 75
    fi
    return "$rc"
  fi

  return 0
}

write_status_snapshot() {
  cd "$REPO"

  {
    echo "# NoemaForge 0.33.0 Codex runner status"
    echo
    echo "- timestamp: $(date -Is)"
    echo "- repo: $REPO"
    echo "- branch: $(git branch --show-current)"
    echo "- base: $BASE_BRANCH"
    echo "- work_branch: $WORK_BRANCH"
    echo "- umbrella_issue: #$UMBRELLA_ISSUE"
    echo
    echo "## Git status"
    echo
    echo '```text'
    git status --short
    echo '```'
    echo
    echo "## Latest commits"
    echo
    echo '```text'
    git log --oneline -10
    echo '```'
  } > "$TASK_ROOT/status.md"
}

maybe_comment_status_to_umbrella() {
  [[ "$ALLOW_GH_WRITE" == "1" ]] || return 0
  command -v gh >/dev/null 2>&1 || return 0

  local body
  body="$(cat "$TASK_ROOT/status.md")"

  gh issue comment "$UMBRELLA_ISSUE" \
    --repo "$GH_REPO" \
    --body "$body" \
    >/dev/null 2>&1 \
    && log "posted status comment to #$UMBRELLA_ISSUE" \
    || log "warning: failed to post status comment to #$UMBRELLA_ISSUE"
}

main() {
  ensure_repo_ready
  fetch_issue_context
  write_prompt

  local cycle rc
  for cycle in $(seq 1 "$MAX_CYCLES"); do
    sleep_until_if_paused

    rc=0
    run_codex_once "$cycle" || rc="$?"

    write_status_snapshot

    if [[ "$rc" == "75" ]]; then
      log "paused due to rate/token limit; will sleep and continue"
      sleep_until_if_paused
      continue
    fi

    if [[ "$rc" != "0" ]]; then
      log "Codex failed with rc=$rc; stopping to avoid repeated bad loop"
      maybe_comment_status_to_umbrella
      exit "$rc"
    fi

    log "cycle $cycle completed"

    if [[ -z "$(git status --porcelain)" ]]; then
      log "no working tree changes after cycle $cycle"
      if [[ ! -f "$TASK_ROOT/continue-loop" ]]; then
        log "no continue-loop marker; stopping"
        break
      fi
    fi
  done

  write_status_snapshot
  maybe_comment_status_to_umbrella

  log "done"
  log "task root: $TASK_ROOT"
  log "status: $TASK_ROOT/status.md"
  log "prompt: $PROMPT_FILE"
}

main "$@"
