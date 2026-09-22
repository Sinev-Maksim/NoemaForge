# Night Watch Canonical Change Log

## 2026-09-21 — repository-first durability

Classification: `UAT request findings resolution`

- Created dedicated development/checkpoint branch `night-watch` from canonical exact base `a3c172f5d60113876f0c103010de411fc30b8c38`.
- Added mandatory intermediate-result remote persistence.
- Added marker `unstable, saved for context` for incomplete GitHub checkpoints.
- Superseded the old blanket no-commit/no-push behavior for durability checkpoints; merge/release/deploy authority remains separate.
- Made repository Markdown canonical for all non-secret development rules/context/status/recovery information.
- Added explicit secret-context exclusion from ordinary repository docs, evidence, and handoffs.
- Reconciled old v3.8.5 status with later 2026-09-16 release evidence: frozen/build qualification and cumulative handoff replay are PASS.
- Preserved unresolved external trust boundaries: exact-final real Windows PowerShell 5.1 execution, remote exact-SHA independent review/CodeRabbit, and human release GO are not confirmed by available evidence.
- Recorded documentation drift in `ENGINEERING_SELF_CHECK.md`: several freeze-gate boxes remained unchecked after later machine-readable PASS evidence.


## 2026-09-21 — exact frozen artifact recovered and rerun

Classification: `UAT request findings resolution`

- Recovered the exact frozen v3.8.5 installer artifact from Library history.
- Verified outer SHA-256 `6adbcabac444c393cb40b7f4cb495b6a78d410c2adefe2ce81cbd74aad3dbd5d`.
- Verified nested sealed-release SHA-256 `16e11736e5241e310b56f84acdd3a71e1d95b9a27f3a29d9ee26f221b45e371c`.
- Completed independent ZIP/manifest/package-closure/encoding/source compilation audit: PASS.
- Observed five successful release-mode full pre-send reruns across the exact frozen bytes.
- Reran host-runtime mode: PASS.
- Reran deployment self-test 5/5, 34 checks each, zero failures.
- Reran startup-hardening, provider-role degradation, harness regression, and 21 routing-contract tests: PASS.
- Confirmed self-pollution guard with an ad-hoc bytecode negative control; immutable frozen archive bytes were unchanged and clean re-extraction returned PASS.
- Preserved a durable Library copy at `/NightWatch-Recovered/NightWatch-Agent-Self-Heal.zip`.
- Target-host execution of this exact outer SHA remains the next operator gate.


## 2026-09-21 — NoemaForge seamless-integration preparation

Classification: `UAT request findings resolution`

- Added the public Night Watch -> NoemaForge seamless-integration method.
- Selected a shadow -> proposal -> bounded execution -> native migration with NF as the single authoritative writer.
- Reused `noemaforge.evolution-execution/v1` as the canonical integration language.
- Defined SSK2-based public engineering instructions and phase gates.
- Selected first-slice module/config/test/UAT paths.
- Defined shadow disagreement classes and external evidence layout.
- Kept all operator-private/secret directives outside GitHub; public code is not allowed to depend on them for correctness or authority.
- First code slice remains intentionally non-mutating.


## 2026-09-21 — architecture correction: Night Watch is code evolution

Classification: `UAT request findings resolution`

- Corrected the integration architecture after restoring earlier design context.
- Night Watch is now explicitly canonicalized as the **code-evolution repair/qualification component** of the NoemaForge Evolution pipeline.
- Superseded the mistaken target architecture in which Night Watch would become a permanent shadow/coordinator beside another code-evolution implementation.
- Preserved `night_watch_readonly.py` as an observation/projection/UAT boundary, not the production mutation entry point.
- Bound future Night Watch integration to canonical **code** Evolution work items, bounded isolated code mutation, qualification and evidence projection.
- Explicitly separated **model mutation/evolution** as the second Evolution branch whose architecture will be designed later.
- Night Watch has no model-mutation authority.


## 2026-09-22 — real Windows target-host run

Classification: `UAT request findings resolution`

- Real v3.8.5 Windows target-host deployment PASS.
- Windows PowerShell `5.1.26100.9444` native AST/closure/runtime preflight PASS.
- Exact frozen inner sealed-release SHA `16e11736e5241e310b56f84acdd3a71e1d95b9a27f3a29d9ee26f221b45e371c` confirmed by installer evidence.
- Target-host pre-send PASS with `SKIP_COUNT=0`.
- Self-heal implementation completed after 5 charged PRODUCT repair attempts and 3 infrastructure recovery attempts.
- Final candidate patch SHA: `38882b33058de4f2ce3b16bdcbe293b8bf6c8c541090882c2a4e3b54fd59a020`.
- Local deterministic gates and final local co-check PASS.
- Final acceptance remains pending because no distinct independent provider was available; Claude transport failed while Codex remained usable.
- Live immutable-test guard rejected attempted test-path proposals and recovered through the control plane.
- Uploaded `history.zip` is hash-consistent but stale (generated 2026-08-15) and does not contain the current v3.8.5 run/candidate.
- Canonical evidence is persisted to GitHub; current candidate bytes still require recovery from the current handoff/run directory to satisfy the no-lost-work code checkpoint rule.


## 2026-09-22 — recovered candidate review and fail-closed correction

Classification: `UAT request findings resolution`

- Recovered the exact current cumulative handoff and verified all 1196 content-addressed objects.
- Recovered/persisted exact original candidate patch SHA-256 `38882b33058de4f2ce3b16bdcbe293b8bf6c8c541090882c2a4e3b54fd59a020`.
- Independently reran the original focused routing suite: 21/21 PASS.
- Adversarial review nevertheless found three blocking defects: unknown scope fail-open around CodeRabbit policy, non-strict provider/persona field validation, and route-envelope semantic contradictions that could validate as PASS.
- Original candidate verdict changed to `REQUEST_CHANGES`; its prior local green state is not treated as acceptance.
- Implemented a corrected WIP with closed scope/route domains, strict provider/persona contracts, independent-review capability enforcement, typed malformed-input rejection, and semantic route-envelope verification.
- Added regression coverage; corrected focused routing suite: 26/26 PASS; Python compile PASS; schema JSON parse PASS.
- Persisted corrected source directly to `night-watch`, plus original candidate, review report, machine-readable review evidence and correction patch.
- Full repository regression, remote exact-candidate review, CodeRabbit and human release GO remain pending.
