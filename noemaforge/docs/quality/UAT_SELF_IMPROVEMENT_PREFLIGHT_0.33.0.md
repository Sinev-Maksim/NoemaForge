# Self-improvement preflight at UAT start — 0.33.0

Status: mandatory UAT request findings resolution gate for issues `#302` and `#316`.

The code-evolution pipeline must be exercised before the main target-host scenarios and again through the authenticated Admin GUI at the beginning of interactive UAT. Neither execution may apply, commit, push, merge, release or alter the source tree.

## Why it runs first

The UAT is intended to validate a system capable of orchestrating its own improvement workflow. Testing that workflow only after the rest of UAT would leave an important failure mode undiscovered: the improvement pipeline might be unable to analyze a task, create a proposal, execute its bounded checks or preserve the worktree before any normal operator scenario begins.

The preflight exercises the real `CodeEvolutionLoop` stages:

1. create a synthetic UAT task;
2. analyze the task against the current source tree;
3. write a proposal artifact into isolated state;
4. execute the fixed bounded test set;
5. record the outcome;
6. compare source and git snapshots taken before and after.

`apply`, `commit` and `publish` are hard-coded to `false`.

## Phase A — before the Admin GUI UAT

Run from the exact checked-out candidate:

```bash
STATE_DIR="$(mktemp -d)"
python3 noemaforge/src/code_evolution_uat_preflight.py \
  --root "$PWD" \
  --state-dir "$STATE_DIR" \
  --json | tee "$STATE_DIR/preflight-result.json"
```

A non-zero exit code blocks UAT. The report must show:

```text
ok=true
status=pass
mode=proposal_test_only
apply=false
commit=false
publish=false
tree_unchanged=true
git_unchanged=true
proposal_not_applied=true
proposal_not_committed=true
bounded_tests_ok=true
tests_executed=true
```

Allowed changes are limited to the supplied isolated state directory: proposal, log, pycache, state and preflight-report artifacts.

## Phase B — beginning of authenticated GUI UAT

1. Start the dashboard using the standard launcher.
2. Establish the owner session through the one-time launcher bootstrap URL.
3. Invoke:

```http
POST /api/code-evolution/uat-preflight
```

No request fields can enable apply or select arbitrary tests. The endpoint uses the same fixed preflight implementation and is protected by the universal Admin GUI owner-session guard.

Expected result: HTTP `200` with `ok=true`. HTTP `409` means the pipeline or a non-mutation invariant failed and the remaining UAT must stop.

## Negative scenarios

The UAT evidence bundle must also show:

- the endpoint is denied without the owner-session cookie;
- forged, stale, cross-session and cross-origin cookies are denied before proposal creation;
- an unlisted POST route is denied even with a valid owner session;
- an intentionally instrumented source mutation changes the fingerprint and forces `ok=false`;
- restart/session rotation invalidates the old cookie;
- downstream approval, manual-marker and ToolProxy checks remain unchanged.

## Evidence to retain

Retain without secrets:

- exact git head and base;
- preflight report JSON;
- proposal ID and task ID;
- bounded test counts and failures;
- before/after tree fingerprints;
- before/after git status hashes;
- owner-session guard reason codes;
- task/job/pipeline/repository/provider/credential before-and-after snapshots;
- explicit confirmation that trusted-trigger policy remained inactive unless a separate activation gate was approved.

Bootstrap tokens and owner-session cookie values must never enter the evidence bundle.
