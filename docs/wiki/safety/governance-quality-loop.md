# Governance and quality loop (local-first)

NoemaForge treats governance, quality assurance, and sensing/telemetry as a single bounded loop rather than a set of independent features. The intent is to keep the system local-first and privacy-first while still making quality regressions, unknowns, and risky actions visible and reviewable.

## One loop, staged delivery

The loop can be implemented in three stages, each with explicit guardrails:

### P0 — foundation (governance + privacy)

- **Concept frame:** a small schema that captures the Admin/Architect intent, constraints, options, risks, and the decision record.
- **Policy gates for dangerous actions:** actions that change state, mutate pipelines, or export data must be guarded by explicit policy and role approval.
- **Sense layer:** coarse host/runtime signals are allowed, but they must be redactable by default.
- **Privacy filter:** redaction happens before persistence/export; raw paths, usernames, environment, and command lines are treated as sensitive by default.
- **Drive adapter (bounded):** any “urgency/pressure/fatigue/curiosity” signal is advisory only and must never override policy gates.
- **Honesty protocol:** templates and conventions for uncertainty (“unknown”), error attribution, and “needs research” states.

### P1 — quality + provenance (evidence)

- **Slop score:** a simple, explainable quality signal with thresholds and action policy.
- **Critic stack:** text-quality, provenance-quality, and slop checks combined into an evidence bundle.
- **Provenance hooks:** interfaces for attaching verification metadata and later pluggable provenance validators, while staying offline by default.
- **Research packet schema:** a structured container for “freshness/source policy + evidence” when internet scouting is enabled by explicit operator choice.
- **Modality critics:** image/video/audio critics are optional and can remain stubbed until the runtime supports them safely.

### P2 — controlled self-development (never automatic)

- **Pipeline RFC:** every pipeline change is proposed as a draft RFC with a diff, a dry-run, and evaluation evidence.
- **No automatic mutation:** pipeline/self-development changes require explicit approval; the system must be able to stop, rollback, and explain.
- **Trace/eval stack:** every RFC carries trace IDs, evaluation results, and a rollback pointer.

## Safety invariant

NoemaForge must not apply pipeline or self-development mutations directly. The only permitted path is:

```text
Pipeline_RFC -> dry-run -> eval evidence -> rollback plan -> explicit approval -> apply
```

This invariant is a release gate expectation: if anything bypasses the RFC/evidence/approval path, the build is not release-ready.

