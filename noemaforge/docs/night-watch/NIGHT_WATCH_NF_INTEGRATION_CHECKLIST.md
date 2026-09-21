# Night Watch -> NoemaForge Integration Preparation Checklist

**Classification:** `UAT request findings resolution`

## Architecture preparation

- [x] NF remains the canonical control plane.
- [x] Existing read-only Night Watch adapter is the Phase-1 boundary.
- [x] Existing `noemaforge.evolution-execution/v1` contracts are the integration language.
- [x] Single-writer / dual-observer migration rule is defined.
- [x] Shadow -> proposal -> bounded execution -> native rollout is defined.
- [x] Private operator context is excluded from GitHub artifacts.
- [ ] Decide exact module/config names for the first integration slice.
- [ ] Define the shadow-result disagreement contract.
- [ ] Define the exact state/evidence root layout for integrated runs.
- [ ] Define feature-flag/config schema and invalid transition behavior.

## First implementation slice

- [ ] Add integration mode policy: `off|observe|shadow|proposal`.
- [ ] Add NF-owned Night Watch coordinator.
- [ ] Accept one canonical `EvolutionWorkItem`.
- [ ] Emit canonical `EvolutionEvent`.
- [ ] Emit canonical `EvolutionAgentResult`.
- [ ] Bind exact base/head and evidence hashes.
- [ ] Prove repeat run byte-idempotence.
- [ ] Prove repository zero-write.
- [ ] Prove observed Night Watch state zero-write.
- [ ] Add disagreement reporting between NF native and Night Watch shadow results.
- [ ] Add UAT runner with evidence outside repository/state roots.
- [ ] Keep mutation disabled.

## Promotion to proposal mode

- [ ] Proposal artifact schema/mapping defined.
- [ ] Allowed changed-path set enforced.
- [ ] Immutable tests/evidence rejection enforced.
- [ ] Base FAIL / candidate PASS / negative control proven.
- [ ] Scope-aware independent review proven.
- [ ] Rollback identity defined before any future mutation.

## Promotion to bounded execution

- [ ] ToolProxy/capability lease designed.
- [ ] One work item / exact base / worktree / path scope / expiry enforced.
- [ ] Pre-attempt exact patch identity persisted.
- [ ] Exact rollback verified.
- [ ] Provider/resource lease integrated.
- [ ] Merge/tag/release/deploy remains impossible for executor.
- [ ] Target-host UAT completed.
- [ ] Independent exact-head review completed.
- [ ] Human GO required for activation.

