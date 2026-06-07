# ADR-0002: Contract-epoch compatibility

- **Status:** Accepted (documents the 0.32.2 posture)
- **Date:** 2026-06-05

## Context

What the system is allowed to run — roles, model selection, enabled tools, compatibility contracts —
must be coherent and must not drift silently. Self-evolution and model-selection can propose changes;
those changes must not reach the active runtime implicitly, and version compatibility must be
visible and verifiable rather than assumed.

## Decision

Pin runtime compatibility to an immutable **contract epoch**:

1. An epoch is **immutable** once created; you do not edit a live epoch — you switch to a new one.
2. Switching is a **two-step, operator-approved** action: a plan (candidate selection / evolution
   proposal) is produced and reviewed, then applied as an epoch switch.
3. **Capability tokens are pinned** to a `contract_epoch`; a token issued under one epoch never
   authorizes calls under another.
4. The previous epoch is **retained for rollback**; if a switch fails smoke checks, the system can
   return to the prior epoch and keep artifacts for audit.

## Consequences

- **Positive:** version compatibility becomes an auditable, switchable, rollback-able contract;
  "works on my setup" becomes a named epoch; no implicit capability drift.
- **Negative / costs:** epoch switches are deliberate (not automatic); maintaining epoch artifacts +
  rollback adds storage and process overhead.
- **Follow-ups (0.33.0):** generate a public **epoch compatibility matrix** (enabled tools,
  role/model bindings, contracts per epoch) via knowledge projection, so external readers see the
  compatibility surface without internal RFCs.

## Related

- `../architecture/contract-epochs.md`, `../architecture/toolproxy-capabilities.md`.
