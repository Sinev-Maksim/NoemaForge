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
