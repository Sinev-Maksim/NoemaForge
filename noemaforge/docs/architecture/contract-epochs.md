# Contract Epochs

A **contract epoch** is an immutable, versioned snapshot of what the system is allowed to run and
how its parts must agree — roles, model selection, enabled tools, and compatibility contracts. It
makes version compatibility **visible and verifiable** instead of implicit, and it is one of
NoemaForge's strongest native differentiators.

## Model

- **Immutable.** An epoch is frozen once created; you do not edit a live epoch, you switch to a new
  one. State lives under the epoch/contracts data roots (`epoch.py`, `_pp.data_root/"contracts"`).
- **Two-step switch.** Changing the active epoch is a deliberate, operator-approved action: a plan
  (candidate selection / evolution proposal) is produced and reviewed, then applied as an epoch
  switch — never an implicit change.
- **Pinned authorization.** ToolProxy capability tokens are bound to a `contract_epoch`; a token
  issued under one epoch does not authorize calls under another (see `toolproxy-capabilities.md`).
- **Rollback.** The previous epoch is retained; if a switch fails smoke checks, the system can
  return to the prior epoch and keep artifacts for audit.

## Where it shows up

- Model selection: `full_composite` mode evaluates candidates and plans role compositions, then an
  epoch-switch request artifact is written for approval (`model_selection_runtime.py`).
- Self-evolution: code/model evolution proposes changes that only reach the active runtime via an
  epoch switch (the `inspect → quarantine → scan → Pipeline_RFC → epoch` path).

## Compatibility artifact (planned)

A published **epoch compatibility matrix** (0.33.0 knowledge-projection) will surface, per epoch,
the enabled tools, role/model bindings, and compatibility contracts — so external readers can see
the compatibility surface without reading internal RFCs.

## Why it matters

Epochs turn "it works on my setup" into an auditable, switchable, rollback-able compatibility
contract: every privileged capability is scoped to a specific, immutable epoch.
