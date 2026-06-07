# ADR-0001: Control-plane boundary (localhost-only, plan-then-apply)

- **Status:** Accepted (documents the 0.32.2 posture)
- **Date:** 2026-06-05

## Context

NoemaForge runs AI models, tools, and pipelines that can have privileged, irreversible, or
display-affecting effects (GPU work, model selection, system services, epoch switches). An operator
needs to drive and audit the system without exposing a powerful surface to the network or running
privileged work implicitly.

## Decision

Separate a **control plane** from the **execution plane**, with these boundary rules:

1. The control plane (Admin GUI/API, `admin_gui_server.py`) binds **`127.0.0.1` by default** —
   localhost-only, not a public service.
2. Privileged actions are **plan-only jobs**: the control plane emits a reviewable plan + the exact
   `sudo noemaforge …` command (always with `--keep-display`); the operator approves the apply step.
   The control-plane process does not perform the privileged step itself.
3. All tool access — even from the control plane — goes through **ToolProxy** under a scoped,
   epoch-bound capability token (ADR is enforced by `capability-token.schema.json` + the ToolProxy
   policy).
4. Every action is **auditable** (event log; jobs/sessions/rollback metadata persisted per profile).

## Consequences

- **Positive:** minimal network attack surface; operator-in-the-loop for privileged actions; display
  safety by default; clear, reviewable boundary between "decide" and "do".
- **Negative / costs:** remote operation requires an explicit, operator-secured tunnel; the
  plan-then-apply step adds a deliberate manual approval for privileged actions.
- **Follow-ups (0.33.0):** publish `control-plane.openapi.yaml`; add a `noema doctor` readiness
  matrix; surface the audit timeline + rollback ledger in the UI.

## Related

- `../architecture/control-plane.md`, `../security/local-only-admin.md`,
  `../architecture/toolproxy-capabilities.md`.
