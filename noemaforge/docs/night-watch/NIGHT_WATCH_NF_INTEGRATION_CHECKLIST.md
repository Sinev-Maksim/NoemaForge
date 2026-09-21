# Night Watch -> NoemaForge Code-Evolution Integration Checklist

**Classification:** `UAT request findings resolution`

## Architecture

- [x] Night Watch identified as the **code-evolution part of the NF Evolution pipeline**.
- [x] Model mutation/evolution separated as a second, future branch.
- [x] NF remains the higher-level canonical Controller/state authority.
- [x] `noemaforge.evolution-execution/v1` remains the cross-system contract family.
- [x] Existing read-only adapter remains an observation/projection boundary.
- [x] Night Watch bounded code mutation is distinct from read-only observation.
- [x] Night Watch has no model-mutation authority.
- [x] Independent review and human release authority remain outside Night Watch.
- [ ] Define the canonical lane discriminator for code vs future model Evolution work.
- [ ] Define exact NF -> Night Watch run-binding schema.
- [ ] Define Night Watch -> NF event/result projection for resumable attempts.
- [ ] Define canonical restart/idempotency key semantics if existing contracts are insufficient.

## Code-evolution binding

- [ ] Accept one canonical code `EvolutionWorkItem`.
- [ ] Reject/defer model-evolution work items.
- [ ] Bind exact base SHA.
- [ ] Create isolated worktree/workspace.
- [ ] Create stable Night Watch run/work-item mapping.
- [ ] Pass only canonical granted capability/scope.
- [ ] Execute diagnostic/scout stage.
- [ ] Execute bounded code implementer stage where authorized.
- [ ] Aggregate deterministic product gates.
- [ ] Run logically separate local review.
- [ ] Run reproducer / negative control where a repair claim is made.
- [ ] Preserve immutable tests/evidence.
- [ ] Persist exact candidate/evidence SHA.
- [ ] Project progress/evidence back into NF canonical state.
- [ ] Prove stop/restart/resume without duplicate product attempts.
- [ ] Prove unrelated NF state remains unchanged.

## Existing Night Watch semantics to preserve

- [x] SUCCESS_FIRST_MAX_EVIDENCE.
- [x] product-plane / control-plane separation.
- [x] structured verdicts.
- [x] exact candidate/evidence identity.
- [x] bounded mutation and exact rollback.
- [x] immutable tests.
- [x] stagnation/progress accounting.
- [x] root-cause extrapolation.
- [x] fault/regression qualification.
- [x] cumulative evidence/handoff integrity.
- [x] external independent-review boundary.
- [x] durable GitHub WIP checkpoints.

## Explicitly deferred: model evolution

- [ ] Model mutation state machine.
- [ ] Model mutation scope/rollback semantics.
- [ ] Training/fine-tuning/evolution resource policy.
- [ ] Model candidate identity/versioning.
- [ ] Model evaluation/acceptance contract.
- [ ] Model-specific independent review.
- [ ] Model promotion/rollback policy.

These items are intentionally **not blockers for Night Watch code-evolution integration**. They belong to the second Evolution branch and will be designed separately.
