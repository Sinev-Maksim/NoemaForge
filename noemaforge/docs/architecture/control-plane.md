# Control Plane

NoemaForge separates a **control plane** (decide, plan, approve, audit) from the **execution
plane** (run models, tools, pipelines). The control plane is **localhost-only by default**.

## Surface

- **Admin GUI / JSON API** — `noemaforge/src/admin_gui_server.py`, bound to `127.0.0.1` (default
  port `8765`). It serves the operator dashboard and the `/api/*` endpoints (session, events, jobs,
  model-selection, vault, telemetry, health). It is **not** exposed off-loopback by default.
- **JobManager** — `job_manager.py`: file-backed, idempotency-keyed job registry with PID/cancel
  tracking. Heavy/privileged actions are created as **plan-only jobs** that emit a reviewable
  command; they are not executed by the GUI process itself.

## Principles

1. **Localhost-only by default.** The control plane is an operator surface, not a public service.
2. **Plan, then apply.** Privileged actions (model-selection continue, vault re-inventory,
   epoch apply) produce an operator-reviewable plan + the exact `sudo noemaforge …` command
   (always carrying `--keep-display`); the operator approves the apply step.
3. **Idempotent actions.** Duplicate operator clicks return the same job (`idempotency_key`), so the
   control plane is safe under refresh/retry.
4. **Auditable.** Every action appends to the event log; sessions, jobs, and rollback metadata are
   persisted under per-profile data roots (`platform_paths`).

## Boundary

The control plane never grants tool access directly — all tool calls go through **ToolProxy**
(see `toolproxy-capabilities.md`) under a scoped, epoch-bound capability token. Compatibility of
what may run is pinned by the active **contract epoch** (see `contract-epochs.md`).

## Why it matters

A localhost-only, plan-then-apply, auditable control plane is a rare trust signal: the operator can
see and approve what the system will do before it does it, and nothing privileged runs implicitly.
