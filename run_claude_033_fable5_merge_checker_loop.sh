#!/usr/bin/env bash
set -Eeuo pipefail

# NoemaForge 0.33.0 Claude Fable-5 merge/checker/docs loop
#
# Purpose:
#   Parallel Claude lane for the 0.33.0 prod-ready loop.
#   Compared to the docs-only Claude runner, this lane may also:
#     - maintain a separate integration worktree/branch;
#     - merge the 0.33.0 base branch and the Codex branch;
#     - resolve merge conflicts;
#     - process checker/reviewer feedback, including CodeRabbit;
#     - request a CodeRabbit review with '@coderabbit review';
#     - update docs/TODO/reconciliation;
#     - create issues for newly found problems;
#     - loop forever with pause-marker behavior on token/rate limits.
#
# Safe one-shot:
#   MAX_CYCLES=1 FORCE_CYCLE=1 ./run_claude_033_fable5_merge_checker_loop.sh
#
# Infinite default:
#   ./run_claude_033_fable5_merge_checker_loop.sh
#
# Important:
#   This script does not start NoemaForge services and does not enable systemd units.
#   It works only through git/GitHub/Claude unless validation commands are explicitly set.

MAIN_REPO="${MAIN_REPO:-$HOME/src/NoemaForge}"
WORKTREE_DIR="${WORKTREE_DIR:-$HOME/src/NoemaForge-claude-033-merge}"
GH_REPO="${GH_REPO:-Sinev-Maksim/NoemaForge}"

BASE_BRANCH="${BASE_BRANCH:-release/0.33.0-dev}"
CODEX_BRANCH="${CODEX_BRANCH:-codex/0.33.0-prod-ready-loop}"
CLAUDE_BRANCH="${CLAUDE_BRANCH:-claude/0.33.0-fable5-merge-checker}"

ISSUES="${ISSUES:-212 213 214 215 216 217 218 219 220 221}"
UMBRELLA_ISSUE="${UMBRELLA_ISSUE:-221}"

# MAX_CYCLES=0 => infinite.
MAX_CYCLES="${MAX_CYCLES:-0}"
POLL_SECONDS="${POLL_SECONDS:-900}"
FORCE_CYCLE="${FORCE_CYCLE:-0}"

# Merge/checker behavior.
MERGE_BASE_EACH_CYCLE="${MERGE_BASE_EACH_CYCLE:-1}"
MERGE_CODEX_BRANCH="${MERGE_CODEX_BRANCH:-1}"
PROCESS_CHECKER_FEEDBACK="${PROCESS_CHECKER_FEEDBACK:-1}"
REQUEST_CODERABBIT_REVIEW="${REQUEST_CODERABBIT_REVIEW:-1}"
CODERABBIT_COMMAND="${CODERABBIT_COMMAND:-@coderabbit review}"

# GitHub/write behavior.
ALLOW_GH_WRITE="${ALLOW_GH_WRITE:-1}"
ALLOW_PUSH="${ALLOW_PUSH:-1}"
ALLOW_PR="${ALLOW_PR:-1}"
AUTO_COMMIT="${AUTO_COMMIT:-1}"
DRAFT_PR="${DRAFT_PR:-1}"

# Claude may edit code in this runner because it resolves conflicts/checker findings.
# Keep this enabled only inside the separate Claude integration branch.
ALLOW_CODE_EDITS="${ALLOW_CODE_EDITS:-1}"
STRICT_DOCS_ONLY="${STRICT_DOCS_ONLY:-0}"

# Fable 5 preference. The script does not assume this model exists locally.
# It passes the model flag/env when the local Claude CLI appears to support it,
# and falls back to default only when CLAUDE_FALLBACK_TO_DEFAULT=1.
CLAUDE_MODEL_PREFERRED="${CLAUDE_MODEL_PREFERRED:-fable-5}"
CLAUDE_MODEL_ALIASES="${CLAUDE_MODEL_ALIASES:-fable-5 claude-fable-5 fable5 Fable-5 Fable5}"
CLAUDE_FALLBACK_TO_DEFAULT="${CLAUDE_FALLBACK_TO_DEFAULT:-1}"
CLAUDE_EXTRA_ARGS="${CLAUDE_EXTRA_ARGS:-}"
CLAUDE_CMD="${CLAUDE_CMD:-claude}"

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
PAUSE_MARKER="${PAUSE_MARKER:-$CLAUDE_HOME/runner-pause-until.txt}"

TASK_ROOT="${TASK_ROOT:-$WORKTREE_DIR/.claude/tasks/0.33.0-fable5-merge-checker}"
ISSUE_DIR="$TASK_ROOT/issues"
LOG_DIR="$TASK_ROOT/logs"
CHECKER_DIR="$TASK_ROOT/checker-feedback"
NEW_ISSUES_DIR="$TASK_ROOT/new-issues"
PROMPT_FILE="$TASK_ROOT/claude-task.md"
STATUS_FILE="$TASK_ROOT/status.md"
DIFF_FILE="$TASK_ROOT/codex-diff.patch"
MERGE_LOG="$TASK_ROOT/merge.log"
CHECKER_SUMMARY="$TASK_ROOT/checker-summary.md"
RECHECK_REPORT="$TASK_ROOT/recheck-report.md"

# Optional validation commands. Keep empty by default to avoid changing host runtime.
# Example:
#   VALIDATION_COMMANDS=$'python -m pytest tests/test_x.py\npython -m py_compile ...'
VALIDATION_COMMANDS="${VALIDATION_COMMANDS:-}"

mkdir -p "$CLAUDE_HOME" "$TASK_ROOT" "$ISSUE_DIR" "$LOG_DIR" "$CHECKER_DIR" "$NEW_ISSUES_DIR"

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

current_utc_epoch() {
  date -u +%s
}

parse_date_to_epoch() {
  date -u -d "$1" +%s 2>/dev/null
}

sleep_until_if_paused() {
  if [[ ! -s "$PAUSE_MARKER" ]]; then
    return 0
  fi

  local until_raw now_ts until_ts sleep_sec
  until_raw="$(tr -d '[:space:]' < "$PAUSE_MARKER" || true)"
  [[ -n "$until_raw" ]] || return 0

  now_ts="$(current_utc_epoch)"
  if until_ts="$(parse_date_to_epoch "$until_raw")"; then
    if (( until_ts > now_ts )); then
      sleep_sec=$((until_ts - now_ts))
      log "Claude pause marker active until $until_raw; sleeping ${sleep_sec}s"
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

  # Fallback: one hour, to avoid tight loops.
  date -u -d '+1 hour' '+%Y-%m-%dT%H:%M:%SZ'
}

looks_like_rate_limit() {
  local logfile="$1"
  grep -Eiq 'rate.?limit|usage.?limit|quota|too many requests|tokens?.*(exhausted|limit)|limit.*reset|try again|retry after|429|credit' "$logfile"
}

looks_like_model_unsupported() {
  local logfile="$1"
  grep -Eiq 'unknown model|invalid model|model .*not found|unsupported model|unrecognized.*model|model.*unavailable|does not exist' "$logfile"
}

ensure_worktree() {
  need_cmd git
  cd "$MAIN_REPO"
  git rev-parse --is-inside-work-tree >/dev/null || die "not a git repo: $MAIN_REPO"

  log "fetching origin in main repo"
  git fetch origin --prune

  if [[ -d "$WORKTREE_DIR/.git" || -f "$WORKTREE_DIR/.git" ]]; then
    log "worktree exists: $WORKTREE_DIR"
  else
    log "creating worktree: $WORKTREE_DIR from $BASE_BRANCH"
    if git rev-parse --verify "$BASE_BRANCH" >/dev/null 2>&1; then
      git worktree add "$WORKTREE_DIR" "$BASE_BRANCH"
    else
      git worktree add "$WORKTREE_DIR" "origin/$BASE_BRANCH"
    fi
  fi

  cd "$WORKTREE_DIR"
  git fetch origin --prune

  if git rev-parse --verify "$CLAUDE_BRANCH" >/dev/null 2>&1; then
    git checkout "$CLAUDE_BRANCH"
  elif git ls-remote --exit-code --heads origin "$CLAUDE_BRANCH" >/dev/null 2>&1; then
    git checkout -B "$CLAUDE_BRANCH" "origin/$CLAUDE_BRANCH"
  else
    git checkout -B "$CLAUDE_BRANCH" "origin/$BASE_BRANCH"
  fi
}

fetch_issue_context() {
  if ! command -v gh >/dev/null 2>&1; then
    log "gh not found; skipping live issue fetch"
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

codex_ref() {
  cd "$WORKTREE_DIR"
  git fetch origin --prune >/dev/null 2>&1 || true
  if git rev-parse --verify "$CODEX_BRANCH" >/dev/null 2>&1; then
    printf '%s\n' "$CODEX_BRANCH"
  elif git rev-parse --verify "origin/$CODEX_BRANCH" >/dev/null 2>&1; then
    printf '%s\n' "origin/$CODEX_BRANCH"
  else
    return 1
  fi
}

capture_codex_diff() {
  cd "$WORKTREE_DIR"
  : > "$DIFF_FILE"

  local ref
  if ! ref="$(codex_ref)"; then
    log "Codex branch not found locally/remotely: $CODEX_BRANCH"
    return 1
  fi

  log "capturing Codex diff from origin/$BASE_BRANCH to $ref"
  git diff --binary "origin/$BASE_BRANCH...$ref" > "$DIFF_FILE" || true

  if [[ ! -s "$DIFF_FILE" ]]; then
    log "Codex diff is empty"
    return 1
  fi

  log "Codex diff written: $DIFF_FILE ($(wc -c < "$DIFF_FILE") bytes)"
  return 0
}

find_pr_number() {
  if [[ -n "${PR_NUMBER:-}" ]]; then
    printf '%s\n' "$PR_NUMBER"
    return 0
  fi
  if ! command -v gh >/dev/null 2>&1; then
    return 1
  fi

  local number
  number="$(gh pr list --repo "$GH_REPO" --head "$CLAUDE_BRANCH" --json number --jq '.[0].number // empty' 2>/dev/null || true)"
  if [[ -n "$number" ]]; then
    printf '%s\n' "$number"
    return 0
  fi

  number="$(gh pr list --repo "$GH_REPO" --head "$CODEX_BRANCH" --json number --jq '.[0].number // empty' 2>/dev/null || true)"
  if [[ -n "$number" ]]; then
    printf '%s\n' "$number"
    return 0
  fi

  return 1
}

fetch_checker_feedback() {
  [[ "$PROCESS_CHECKER_FEEDBACK" == "1" ]] || return 0
  if ! command -v gh >/dev/null 2>&1; then
    log "gh not found; cannot fetch checker feedback"
    return 0
  fi

  mkdir -p "$CHECKER_DIR"
  local pr
  if ! pr="$(find_pr_number)"; then
    log "no PR found for $CLAUDE_BRANCH or $CODEX_BRANCH; checker feedback unavailable yet"
    return 0
  fi

  log "fetching checker feedback for PR #$pr"
  printf '%s\n' "$pr" > "$CHECKER_DIR/pr-number"

  gh pr view "$pr" --repo "$GH_REPO" \
    --json number,title,state,url,headRefName,baseRefName,comments,reviews,files,statusCheckRollup \
    > "$CHECKER_DIR/pr-$pr-view.json" \
    2> "$CHECKER_DIR/pr-$pr-view.err" \
    || log "warning: failed gh pr view #$pr"

  # Inline review comments.
  gh api "repos/$GH_REPO/pulls/$pr/comments" \
    --paginate > "$CHECKER_DIR/pr-$pr-inline-comments.json" \
    2> "$CHECKER_DIR/pr-$pr-inline-comments.err" \
    || true

  # Issue comments.
  gh api "repos/$GH_REPO/issues/$pr/comments" \
    --paginate > "$CHECKER_DIR/pr-$pr-issue-comments.json" \
    2> "$CHECKER_DIR/pr-$pr-issue-comments.err" \
    || true

  {
    echo "# Checker feedback summary"
    echo
    echo "- PR: #$pr"
    echo "- fetched_at: $(date -Is)"
    echo
    echo "## CodeRabbit / code-checker matches"
    echo
    grep -RInEi 'coderabbit|code.?rabbit|code-checker|reviewdog|sonar|codacy|lint|typecheck|pytest|failed|failure|regression|blocking|nit|suggestion' "$CHECKER_DIR" 2>/dev/null | head -300 || true
  } > "$CHECKER_SUMMARY"

  log "checker summary written: $CHECKER_SUMMARY"
}

write_prompt() {
  cat > "$PROMPT_FILE" <<EOF_PROMPT
You are Claude running the NoemaForge 0.33.0 Fable-5 merge/checker/docs lane.

Mode preference:
- Use Fable 5 if available in this Claude environment.
- If exact Fable 5 is not available, behave as close as possible to the intended Fable 5 working mode: rigorous, structured, careful, long-horizon, adversarial reviewer, strong conflict resolver, strong documentation editor, and requirements reconciler.
- Do not claim the actual model is Fable 5 unless the CLI confirms or the runner passes it successfully.

Branch/worktree:
- Worktree: $WORKTREE_DIR
- Branch: $CLAUDE_BRANCH
- Base branch: $BASE_BRANCH
- Codex branch: $CODEX_BRANCH
- Umbrella task: #$UMBRELLA_ISSUE

Role:
- Codex remains the primary implementer for the #212-#220 fix loop.
- Claude is allowed to resolve merge conflicts and checker/reviewer findings in this separate integration branch.
- Claude also owns review, audit, docs, TODOs, requirements reconciliation, recheck analysis, and new issue triage.

Hard safety constraints:
- Preserve runtime_only semantics: gateway/toolproxy only; no required main backend.
- Preserve max_active_llms=1.
- Preserve heavy LLM manual-only.
- Do not make /opt/noemaforge mutable runtime state.
- Do not silently change boot persistence.
- Do not mark real failures green unless explicitly classified as expected skip/degraded with evidence.
- Do not start or enable local NoemaForge services from this lane unless the operator explicitly adds validation commands.

Current evidence from Trixie re-entry:
- Trixie baseline is clean.
- NF runtime_only safe core starts successfully.
- /opt chmod/chown local repair confirmed install payload problems.
- pipeline validate fails on unknown team media_team.
- pipeline approve/advance in smoke state returns degraded_readonly under staffing_state=degraded_selected.
- pipeline validate --json rejects --json.
- manual boot-mode was restored by disabling gateway/toolproxy after diagnostics.

Issue set:
- #212 installed payload loses executable bits for smoke/preflight/operator scripts.
- #213 installer installs /opt/noemaforge as invoking user and group-writable.
- #214 runtime_only smoke should not fail on intentionally missing main backend.
- #215 safe-start runtime_only mutates persistent systemd enablement despite manual boot mode.
- #216 installed systemd units rely on hotfix drop-ins and stale 0.32.1 metadata.
- #217 mvp-smoke reports failures without actionable stderr/artifact links.
- #218 pipeline catalog validation fails because media/admin pipelines reference missing media_team.
- #219 mvp-smoke lifecycle check is blocked by degraded_readonly under degraded_selected staffing.
- #220 pipeline validate emits validation JSON but rejects --json.
- #221 umbrella prod-ready loop.

Inputs available:
- Issue JSON files: $ISSUE_DIR/issue-*.json
- Codex diff if available: $DIFF_FILE
- Checker feedback: $CHECKER_DIR/ and $CHECKER_SUMMARY
- Merge log: $MERGE_LOG
- Runner status: $STATUS_FILE

Required work for this pass:
1. Inspect the git state and current merge result.
2. If merge conflicts exist, resolve them correctly, preserving safety constraints and intent from both branches.
3. Review CodeRabbit/code-checker/reviewer feedback from $CHECKER_DIR and address valid findings.
4. If a checker finding is invalid, record a concise rationale in .claude/tasks/0.33.0-fable5-merge-checker/checker-disposition.md.
5. Review Codex changes against #212-#221 acceptance criteria.
6. Apply small integration fixes only when needed for conflict/checker/acceptance resolution.
7. Update docs/TODO/reconciliation after code/config behavior changes.
8. Create or prepare GitHub issues for new problems that are not fixed in this pass.
9. Maintain:
   - .claude/tasks/0.33.0-fable5-merge-checker/claude-review-report.md
   - .claude/tasks/0.33.0-fable5-merge-checker/checker-disposition.md
   - .claude/tasks/0.33.0-fable5-merge-checker/requirements-reconciliation.md
   - .claude/tasks/0.33.0-fable5-merge-checker/recheck-report.md
   - .claude/tasks/0.33.0-fable5-merge-checker/new-issues/ if needed
10. Do one bounded pass and return control to the runner. Do not loop inside Claude.

GitHub behavior:
- ALLOW_GH_WRITE=$ALLOW_GH_WRITE
- ALLOW_PUSH=$ALLOW_PUSH
- ALLOW_PR=$ALLOW_PR
- REQUEST_CODERABBIT_REVIEW=$REQUEST_CODERABBIT_REVIEW
- CodeRabbit command requested by operator: $CODERABBIT_COMMAND

If ALLOW_GH_WRITE=1, you may use gh to create/update issues/comments when new evidence is found.
If a PR exists, prepare a concise PR status note and checker disposition.
If no PR exists, leave a PR-ready summary in the task folder.

Verification expectations:
- Do not run heavy/runtime-host validation unless explicitly configured by VALIDATION_COMMANDS.
- Prefer static/source checks, config validation, unit tests, and documentation consistency checks.
- If a command cannot run locally, record why and what should be run on the Trixie host.

Important output style:
- Be explicit about blockers vs non-blockers.
- Include exact commands for the next recheck.
- Preserve issue references (#212-#221).
EOF_PROMPT

  log "prompt written: $PROMPT_FILE"
}

claude_help_has() {
  "$CLAUDE_CMD" --help 2>&1 | grep -q -- "$1"
}

build_model_args() {
  if claude_help_has '--model'; then
    printf '%s\n' "--model" "$CLAUDE_MODEL_PREFERRED"
  fi
}

run_claude_prompt_once() {
  local prompt_file="$1"
  local out="$2"
  local prompt_text model_args
  prompt_text="$(cat "$prompt_file")"

  export ANTHROPIC_MODEL="$CLAUDE_MODEL_PREFERRED"
  export CLAUDE_MODEL="$CLAUDE_MODEL_PREFERRED"
  export CLAUDE_CODE_MODEL="$CLAUDE_MODEL_PREFERRED"

  mapfile -t model_args < <(build_model_args)

  set +e
  if claude_help_has '-p' || claude_help_has '--print'; then
    if claude_help_has '-p'; then
      "$CLAUDE_CMD" ${model_args[@]+"${model_args[@]}"} $CLAUDE_EXTRA_ARGS -p "$prompt_text" 2>&1 | tee "$out"
    else
      "$CLAUDE_CMD" ${model_args[@]+"${model_args[@]}"} $CLAUDE_EXTRA_ARGS --print "$prompt_text" 2>&1 | tee "$out"
    fi
  else
    "$CLAUDE_CMD" ${model_args[@]+"${model_args[@]}"} $CLAUDE_EXTRA_ARGS "$prompt_text" 2>&1 | tee "$out"
  fi
  local rc="${PIPESTATUS[0]}"
  set -e
  return "$rc"
}

run_claude_prompt() {
  local label="$1"
  local prompt_file="$2"
  local out="$LOG_DIR/claude-${label}-$(date -u +%Y%m%dT%H%M%SZ).log"
  local rc

  need_cmd "$CLAUDE_CMD"
  cd "$WORKTREE_DIR"
  log "starting Claude pass: $label; log=$out; preferred_model=$CLAUDE_MODEL_PREFERRED"

  rc=0
  run_claude_prompt_once "$prompt_file" "$out" || rc="$?"

  if (( rc != 0 )) && looks_like_model_unsupported "$out" && [[ "$CLAUDE_FALLBACK_TO_DEFAULT" == "1" ]]; then
    log "preferred model appears unsupported; retrying once with default Claude model"
    unset ANTHROPIC_MODEL CLAUDE_MODEL CLAUDE_CODE_MODEL
    local fallback_out="$LOG_DIR/claude-${label}-fallback-$(date -u +%Y%m%dT%H%M%SZ).log"
    set +e
    if claude_help_has '-p'; then
      "$CLAUDE_CMD" $CLAUDE_EXTRA_ARGS -p "$(cat "$prompt_file")" 2>&1 | tee "$fallback_out"
    elif claude_help_has '--print'; then
      "$CLAUDE_CMD" $CLAUDE_EXTRA_ARGS --print "$(cat "$prompt_file")" 2>&1 | tee "$fallback_out"
    else
      "$CLAUDE_CMD" $CLAUDE_EXTRA_ARGS "$(cat "$prompt_file")" 2>&1 | tee "$fallback_out"
    fi
    rc="${PIPESTATUS[0]}"
    set -e
    out="$fallback_out"
  fi

  log "Claude pass $label exit code: $rc"

  if (( rc != 0 )) && looks_like_rate_limit "$out"; then
    local reset
    reset="$(extract_reset_time_or_fallback "$out")"
    printf '%s\n' "$reset" > "$PAUSE_MARKER"
    log "rate/token limit detected; wrote pause marker: $PAUSE_MARKER => $reset"
    return 75
  fi

  return "$rc"
}

write_conflict_prompt() {
  local file="$TASK_ROOT/claude-conflict-resolution.md"
  cat > "$file" <<EOF_CONFLICT
You are Claude in the NoemaForge 0.33.0 Fable-5 merge/conflict lane.

The current git worktree has merge conflicts.

Resolve them now.

Rules:
- Preserve the intent of $BASE_BRANCH, $CODEX_BRANCH, and the Claude integration branch.
- Keep safety invariants:
  - runtime_only means gateway/toolproxy only;
  - max_active_llms=1;
  - heavy LLM manual-only;
  - /opt/noemaforge is immutable installed payload, not mutable state;
  - safe-start must not silently change persistent boot mode unless explicitly requested.
- Do not use conflict markers as comments.
- Do not discard Codex fixes unless clearly wrong; if you reject something, record why.
- After editing, run git status and ensure no unmerged paths remain.
- Update .claude/tasks/0.33.0-fable5-merge-checker/merge-resolution-notes.md.

Helpful commands:
- git status --short
- git diff --name-only --diff-filter=U
- git diff
EOF_CONFLICT
  printf '%s\n' "$file"
}

resolve_conflicts_with_claude() {
  cd "$WORKTREE_DIR"
  if [[ -z "$(git diff --name-only --diff-filter=U)" ]]; then
    return 0
  fi

  local prompt_file rc
  prompt_file="$(write_conflict_prompt)"
  rc=0
  run_claude_prompt "conflicts" "$prompt_file" || rc="$?"
  if [[ "$rc" == "75" ]]; then
    return 75
  fi
  if [[ "$rc" != "0" ]]; then
    return "$rc"
  fi

  if [[ -n "$(git diff --name-only --diff-filter=U)" ]]; then
    log "conflicts remain after Claude pass"
    git diff --name-only --diff-filter=U | tee -a "$LOG_DIR/runner.log"
    return 2
  fi

  return 0
}

merge_ref_safely() {
  local ref="$1"
  local label="$2"
  cd "$WORKTREE_DIR"

  log "merging $label: $ref"
  {
    echo "=== merge $label: $ref @ $(date -Is) ==="
    git status --short
  } >> "$MERGE_LOG"

  set +e
  git merge --no-ff --no-edit "$ref" >> "$MERGE_LOG" 2>&1
  local rc="$?"
  set -e

  if (( rc == 0 )); then
    log "merge $label succeeded"
    return 0
  fi

  if [[ -n "$(git diff --name-only --diff-filter=U)" ]]; then
    log "merge $label has conflicts; invoking Claude"
    local crc=0
    resolve_conflicts_with_claude || crc="$?"
    if [[ "$crc" == "75" ]]; then
      return 75
    fi
    if [[ "$crc" != "0" ]]; then
      log "Claude failed to resolve conflicts for $label"
      return "$crc"
    fi

    git add -A
    git commit -m "Resolve $label merge conflicts for 0.33.0" >> "$MERGE_LOG" 2>&1 || true
    log "merge conflict resolution committed for $label"
    return 0
  fi

  log "merge $label failed without unmerged paths; inspect $MERGE_LOG"
  return "$rc"
}

perform_merges() {
  cd "$WORKTREE_DIR"
  git fetch origin --prune

  if [[ "$MERGE_BASE_EACH_CYCLE" == "1" ]]; then
    if git rev-parse --verify "origin/$BASE_BRANCH" >/dev/null 2>&1; then
      merge_ref_safely "origin/$BASE_BRANCH" "base-$BASE_BRANCH" || return "$?"
    fi
  fi

  if [[ "$MERGE_CODEX_BRANCH" == "1" ]]; then
    local ref
    if ref="$(codex_ref)"; then
      merge_ref_safely "$ref" "codex-$CODEX_BRANCH" || return "$?"
    else
      log "skipping Codex merge; branch not found: $CODEX_BRANCH"
    fi
  fi
}

run_validation_commands() {
  cd "$WORKTREE_DIR"
  : > "$RECHECK_REPORT"

  {
    echo "# Claude lane recheck report"
    echo
    echo "- timestamp: $(date -Is)"
    echo "- branch: $(git branch --show-current)"
    echo
  } >> "$RECHECK_REPORT"

  if [[ -z "$VALIDATION_COMMANDS" ]]; then
    {
      echo "## Validation"
      echo
      echo "No VALIDATION_COMMANDS configured. Runtime-host checks were intentionally not run."
      echo
      echo "Suggested target-host recheck after merge:"
      echo
      echo '```bash'
      echo 'noemaforge trixie-preflight --json'
      echo 'noemaforge pipeline validate'
      echo 'noemaforge pipeline validate --json'
      echo 'noemaforge mvp-smoke --json'
      echo 'noemaforge smoke --profile runtime_only || noemaforge smoke --gateway-only'
      echo '```'
    } >> "$RECHECK_REPORT"
    return 0
  fi

  log "running configured validation commands"
  {
    echo "## Validation commands"
    echo
    echo '```bash'
    printf '%s\n' "$VALIDATION_COMMANDS"
    echo '```'
    echo
  } >> "$RECHECK_REPORT"

  local rc=0
  while IFS= read -r cmd; do
    [[ -n "$cmd" ]] || continue
    log "validation: $cmd"
    {
      echo "### $cmd"
      echo
      echo '```text'
    } >> "$RECHECK_REPORT"
    set +e
    bash -lc "$cmd" >> "$RECHECK_REPORT" 2>&1
    local cmd_rc="$?"
    set -e
    {
      echo '```'
      echo
      echo "exit_code: $cmd_rc"
      echo
    } >> "$RECHECK_REPORT"
    if (( cmd_rc != 0 )); then
      rc="$cmd_rc"
    fi
  done <<< "$VALIDATION_COMMANDS"

  return "$rc"
}

safety_scan() {
  cd "$WORKTREE_DIR"
  local report="$TASK_ROOT/safety-scan.md"
  {
    echo "# Safety scan"
    echo
    echo "- timestamp: $(date -Is)"
    echo
    echo "## Git diff check"
    echo
    echo '```text'
    git diff --check 2>&1 || true
    echo '```'
    echo
    echo "## Suspicious changed lines"
    echo
    echo '```text'
    git diff -U0 "origin/$BASE_BRANCH...HEAD" 2>/dev/null \
      | grep -E 'heavy_llm_autostart.*true|max_active_llms.*[2-9]|systemctl enable|WantedBy=.*multi-user|/opt/noemaforge.*(write|state|mutable)' \
      || true
    echo '```'
  } > "$report"

  if git diff --check >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

write_status_snapshot() {
  cd "$WORKTREE_DIR"
  {
    echo "# NoemaForge 0.33.0 Claude Fable-5 merge/checker runner status"
    echo
    echo "- timestamp: $(date -Is)"
    echo "- main_repo: $MAIN_REPO"
    echo "- worktree: $WORKTREE_DIR"
    echo "- branch: $(git branch --show-current)"
    echo "- base_branch: $BASE_BRANCH"
    echo "- codex_branch: $CODEX_BRANCH"
    echo "- umbrella_issue: #$UMBRELLA_ISSUE"
    echo "- preferred_model: $CLAUDE_MODEL_PREFERRED"
    echo "- allow_code_edits: $ALLOW_CODE_EDITS"
    echo "- request_coderabbit_review: $REQUEST_CODERABBIT_REVIEW"
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
  } > "$STATUS_FILE"
}

auto_commit_if_needed() {
  [[ "$AUTO_COMMIT" == "1" ]] || return 0
  cd "$WORKTREE_DIR"
  if [[ -z "$(git status --porcelain)" ]]; then
    log "no changes to commit"
    return 0
  fi

  git add -A
  git commit -m "Claude Fable-5 0.33.0 merge/checker/docs pass" || {
    log "commit failed; status follows"
    git status --short | tee -a "$LOG_DIR/runner.log"
    return 1
  }
}

push_and_pr_if_allowed() {
  cd "$WORKTREE_DIR"
  [[ "$ALLOW_PUSH" == "1" ]] || return 0

  log "pushing branch $CLAUDE_BRANCH"
  git push -u origin "$CLAUDE_BRANCH"

  [[ "$ALLOW_PR" == "1" ]] || return 0
  command -v gh >/dev/null 2>&1 || return 0

  local pr
  pr="$(gh pr list --repo "$GH_REPO" --head "$CLAUDE_BRANCH" --json number --jq '.[0].number // empty' 2>/dev/null || true)"
  if [[ -z "$pr" ]]; then
    local draft_flag=()
    [[ "$DRAFT_PR" == "1" ]] && draft_flag=(--draft)
    gh pr create \
      --repo "$GH_REPO" \
      --base "$BASE_BRANCH" \
      --head "$CLAUDE_BRANCH" \
      "${draft_flag[@]}" \
      --title "Claude Fable-5 merge/checker/docs pass for 0.33.0" \
      --body-file "$STATUS_FILE" \
      >/tmp/claude-pr-create.out 2>/tmp/claude-pr-create.err \
      || log "warning: failed to create PR; see /tmp/claude-pr-create.err"
  fi
}

comment_status_to_umbrella() {
  [[ "$ALLOW_GH_WRITE" == "1" ]] || return 0
  command -v gh >/dev/null 2>&1 || return 0

  gh issue comment "$UMBRELLA_ISSUE" \
    --repo "$GH_REPO" \
    --body-file "$STATUS_FILE" \
    >/dev/null 2>&1 \
    && log "posted status comment to #$UMBRELLA_ISSUE" \
    || log "warning: failed to post status comment to #$UMBRELLA_ISSUE"
}

request_coderabbit_review_if_needed() {
  [[ "$REQUEST_CODERABBIT_REVIEW" == "1" ]] || return 0
  [[ "$ALLOW_GH_WRITE" == "1" ]] || return 0
  command -v gh >/dev/null 2>&1 || return 0

  local pr marker
  pr="$(gh pr list --repo "$GH_REPO" --head "$CLAUDE_BRANCH" --json number --jq '.[0].number // empty' 2>/dev/null || true)"
  [[ -n "$pr" ]] || return 0

  marker="$TASK_ROOT/coderabbit-review-requested-pr-$pr"
  if [[ -f "$marker" ]]; then
    log "CodeRabbit review already requested for PR #$pr"
    return 0
  fi

  gh pr comment "$pr" --repo "$GH_REPO" --body "$CODERABBIT_COMMAND" \
    >/dev/null 2>&1 \
    && { touch "$marker"; log "requested CodeRabbit review on PR #$pr with: $CODERABBIT_COMMAND"; } \
    || log "warning: failed to request CodeRabbit review on PR #$pr"
}

run_one_cycle() {
  local cycle="$1"
  log "=== cycle $cycle start ==="

  ensure_worktree
  fetch_issue_context
  capture_codex_diff || true
  fetch_checker_feedback || true
  write_prompt

  local rc=0
  perform_merges || rc="$?"
  if [[ "$rc" == "75" ]]; then
    return 75
  fi
  if [[ "$rc" != "0" ]]; then
    log "merge phase failed rc=$rc"
    return "$rc"
  fi

  rc=0
  run_claude_prompt "main" "$PROMPT_FILE" || rc="$?"
  if [[ "$rc" == "75" ]]; then
    return 75
  fi
  if [[ "$rc" != "0" ]]; then
    log "Claude main pass failed rc=$rc"
    return "$rc"
  fi

  safety_scan || log "warning: safety scan found issues; inspect $TASK_ROOT/safety-scan.md"
  run_validation_commands || log "warning: validation commands failed; inspect $RECHECK_REPORT"
  write_status_snapshot

  auto_commit_if_needed || return "$?"
  write_status_snapshot
  push_and_pr_if_allowed || true
  request_coderabbit_review_if_needed || true
  comment_status_to_umbrella || true

  log "=== cycle $cycle done ==="
}

main() {
  local cycle=1 rc=0

  while :; do
    sleep_until_if_paused

    if [[ "$FORCE_CYCLE" != "1" && "$cycle" != "1" ]]; then
      log "sleeping $POLL_SECONDS before next cycle"
      sleep "$POLL_SECONDS"
      sleep_until_if_paused
    fi

    rc=0
    run_one_cycle "$cycle" || rc="$?"

    if [[ "$rc" == "75" ]]; then
      log "paused due to Claude rate/token limit; will resume after marker"
      sleep_until_if_paused
    elif [[ "$rc" != "0" ]]; then
      log "cycle failed rc=$rc; stopping to avoid bad loop"
      write_status_snapshot || true
      comment_status_to_umbrella || true
      exit "$rc"
    fi

    if [[ "$MAX_CYCLES" != "0" && "$cycle" -ge "$MAX_CYCLES" ]]; then
      log "MAX_CYCLES=$MAX_CYCLES reached; stopping"
      break
    fi

    cycle=$((cycle + 1))
  done

  log "done"
  log "task root: $TASK_ROOT"
  log "status: $STATUS_FILE"
}

main "$@"
