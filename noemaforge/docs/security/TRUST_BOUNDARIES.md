# Trust Boundaries

NoemaForge's safety story is best understood as a set of **boundaries** and a short list of things
that **cannot happen automatically**. This page makes those explicit. It is the companion to
[`threat-model.md`](threat-model.md) (assets + adversaries) and the root
[`SECURITY.md`](../../../SECURITY.md) front page.

## Trust zones

```
                         ┌──────────────────────────────────────────┐
   TRUSTED              │  Operator (localhost, human-in-the-loop)   │
   (you + your machine) │  approves every privileged / GPU action    │
                         └───────────────────┬──────────────────────┘
                                             │ plan → review → apply
                         ┌───────────────────▼──────────────────────┐
   TRUSTED, localhost   │  Control plane — Admin GUI/API (127.0.0.1) │
   only                 │  plans + audits; never executes privilege  │
                         └───────────────────┬──────────────────────┘
                                             │ scoped, epoch-bound,
                                             │ expiring capability token
                         ┌───────────────────▼──────────────────────┐
   BOUNDARY             │  ToolProxy  —  deny-by-default gateway     │
                         └───────────────────┬──────────────────────┘
                                             │ one audited egress
                         ┌───────────────────▼──────────────────────┐
   UNTRUSTED output     │  Execution plane: models / tools / pipes   │
                         │  runs under the active immutable epoch     │
                         └───────────────────┬──────────────────────┘
                                             │ inspect → quarantine →
                                             │ scan → Pipeline_RFC → epoch
                         ┌───────────────────▼──────────────────────┐
   UNTRUSTED input      │  External content: skills, models, data    │
                         └────────────────────────────────────────────┘
```

## What CANNOT happen automatically

The core of NoemaForge's safety posture is that the high-consequence actions are **structurally
gated** — they require an explicit, auditable operator step. None of the following happen on their
own:

| It cannot happen automatically that… | Because |
|---|---|
| **A privileged change runs without operator approval** | Privileged actions are *plan-only* jobs: the control plane emits a reviewable plan + the exact `sudo noemaforge …` command; the operator runs it. |
| **Heavy model selection / GPU work starts and blanks the display** | Every such command must carry `--keep-display`; there is no implicit first-start. |
| **A tool is called that wasn't explicitly authorized** | ToolProxy is deny-by-default: no valid, scoped, epoch-bound, unexpired capability token → the call is rejected and logged. |
| **The set of allowed tools/models silently changes** | Capabilities are pinned to an **immutable contract epoch**; changing them requires an approved, rollback-able epoch switch. |
| **The Admin control plane is reachable off the machine** | It binds `127.0.0.1` by default; exposing it off-loopback is an explicit operator decision. |
| **Untrusted external content reaches the runtime** | Marketplace skills/models pass inspect → quarantine → scan → Pipeline_RFC → epoch before they can run. |
| **A heavy LLM backend auto-starts on a schedule** | `heavy_llm_autostart=manual_only`; the timer-driven manager runs `--plan` (reports drift, starts nothing) — applying is operator-initiated. |
| **An unverified release is installed** | `noema upgrade run` verifies the signed release-manifest **before** applying; `noema release verify` is the GO gate. |
| **A file is deleted or user state is overwritten on upgrade** | The upgrade planner never deletes and never overwrites protected paths (`context.md`, data/sessions/secrets/tokens). |

## Enforcement is checkable

Each boundary maps to a file you can read or a command you can run — see the
[Public verifiability](../../../README.md#public-verifiability--dont-trust-verify) table and
[`local-only-admin.md`](local-only-admin.md), [`capability-tokens.md`](capability-tokens.md),
[`contract-epochs`](../architecture/contract-epochs.md), and `noema policy test` (the deny-by-default
contract guard).
