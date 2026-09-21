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
