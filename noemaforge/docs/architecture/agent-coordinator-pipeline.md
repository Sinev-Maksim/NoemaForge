# Agent coordinator pipeline

Status: design note for 0.33.0 closeout and 0.33.1 implementation.

## Why this exists

NoemaForge uses long-running AI-assisted development loops. These loops can be
effectively infinite: an agent writes code, CI and review systems produce new
signals, another agent remediates, and the cycle repeats until the release gates
are clean. A safe system therefore needs explicit ownership, bounded leases,
durable handoff state, and deterministic validators.

The core lesson from the current 0.33.0 hardening cycle is that branch names are
useful safety rails but are not a complete coordination model. The final design
should be task-state driven: the idle capable agent claims work, writes or
reviews according to the lease it acquired, and hands off to a different agent
for review/remediation.

## Current 0.33.0 alignment

0.33.0 remains focused on finishing the production-ready install/re-entry lane.
Do not add a broad new coordinator runtime before the 0.33.0 release candidate is
closed. The allowed 0.33.0 pipeline work is limited to:

- keep `codex/**` and `claude/**` push routes deterministic;
- prevent stale autonomous workflow queues from growing without bound;
- ensure `codex-review` does not run on `claude/**` remediation branches;
- ensure trusted preflight validation runs for both `codex/**` and `claude/**`;
- keep pipeline validation, quality, acceptance, Semgrep, P0 ledger, and
  CodeRabbit as deterministic gates;
- document the 0.33.1 coordinator backlog.

## Current branch semantics

Until the 0.33.1 coordinator exists:

- `codex/**` is the writer/source lane.
- `claude/**` is the reviewer/remediation/integration lane.
- PRs from `claude/**` are the final integration candidates.
- PRs from `codex/**` may remain draft/source PRs and can be closed after the
  synchronized integration PR is merged.

This is a transitional rule, not the final architecture.

## Target 0.33.1 semantics

In 0.33.1, branch prefix should stop being the source of truth. The source of
truth becomes a task lease record:

```json
{
  "task": "pr-or-issue-number",
  "state": "review_requested",
  "head_sha": "required",
  "writer": {"agent": "codex", "lease_id": "w-1", "fence": 1},
  "reviewer": null,
  "expires_at": "timestamp",
  "audit": []
}
```

The key invariant is anti-self-review:

```text
writer.agent != reviewer.agent
```

A reviewer is allowed to write remediation commits. In NoemaForge terminology,
reviewer means reviewer + integrator + release-gate remediator.

## State machine

```text
unclaimed
  -> writer_claimed
  -> implementing
  -> review_requested
  -> reviewer_claimed
  -> reviewing
  -> remediating
  -> validating
  -> ready
```

Failure and loopback states:

```text
blocked
needs_human
changes_requested
back_to_writer
lease_expired
quality_failed
acceptance_failed
coderabbit_failed
semgrep_failed
merge_conflict
```

## Infinite-loop controls

Long-running agent loops must have bounded coordination even if the work itself
is open-ended.

Rules:

1. One active writer lease per task.
2. One active reviewer/remediator lease per task.
3. Every lease has an expiry and heartbeat.
4. Every state mutation carries `head_sha` and a monotonically increasing fence.
5. Stale workers may not write state after their fence expires.
6. Push workflows keep one active run and at most one latest pending run per
   branch/workflow.
7. Coordinator state transitions are serialized.
8. Validators are deterministic; agents only consume and remediate their output.

## 0.33.0 closeout gate

Do not switch the active development loop to 0.33.1 until all of these are true:

- final 0.33.0 integration PR is synchronized with the latest writer lane;
- quality gate is green;
- acceptance suite is green;
- Semgrep is green or explicitly documented as false positive;
- CodeRabbit actionable threads are resolved or outdated;
- pipeline validation passes through both Python entrypoint and installed CLI
  path;
- local artifact scan is clean;
- docs/TODO mention remaining 0.33.1 coordinator work;
- target-host runtime validation is recorded separately and not inferred from CI.

## 0.33.1 implementation backlog

The first 0.33.1 coordinator MVP should add:

1. serialized coordinator state;
2. `/claim`, `/handoff`, `/heartbeat`, `/release`, `/resolve` commands;
3. lease expiry and fencing;
4. anti-self-review enforcement;
5. writer/reviewer reusable workflows or runner modes;
6. stable check names consumed by the coordinator;
7. audit events in PR comments or a coordinator state branch;
8. optional protected environment for final ready/merge transition.

## What not to build yet

Do not introduce LangGraph, Temporal, A2A, Redis, or a full GitHub App during the
0.33.0 closeout. Those are valid later options, but the immediate release needs
deterministic branch routing, clean gates, and a documented transition point.
