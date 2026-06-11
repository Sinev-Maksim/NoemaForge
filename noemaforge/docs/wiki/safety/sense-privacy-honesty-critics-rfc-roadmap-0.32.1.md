# NoemaForge Sense / Privacy / Honesty / Critics / Pipeline-RFC Roadmap — 0.32.1

> **Status: historical snapshot (0.32.1 era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

Tracking ID: `NFG-PROP-0.32.1-sense-quality-governance-pack`
Status: candidate alpha backlog pack; documentation only in `0.32.1`
Runtime impact: none. This does not add OpenTelemetry, OPA, C2PA, watermarking, DVC, MLflow, Langfuse, psutil, Internet access or new detectors to the active install.

## Goal

Unify seven safety/quality ideas into a controlled NoemaForge governance layer:

```text
Concept_Frame -> Sense_Layer/Privacy -> Honesty/Slop -> Critic_Stack/Provenance -> Internet_Scout -> Pipeline_RFC
```

## P0 foundation

- `Concept_Frame` schema for Admin and Architect.
- Rule/policy gates for dangerous role actions.
- Coarse host telemetry: CPU, RAM, disk, network, load.
- Privacy filter and redaction before persistence/export.
- Bounded Drive Adapter: pressure, fatigue, urgency, curiosity.
- Honesty Protocol with `Unknown`, `Need-Research`, and traceable `Error_Attribution`.

## P1 quality and provenance

- `Slop_Score` v1 with action policy: allow, revise, abstain, escalate.
- `Critic_Stack` v1 for text, provenance and slop.
- C2PA/Content Credentials hooks where applicable.
- Watermark hooks where applicable.
- `Detection_Verdict` as an advisory aggregate, not a single-detector truth claim.
- `Research_Packet` with freshness windows, source allowlists and citation bundles.
- Critics for image/video/audio.

## P2 self-development governance

- `Pipeline_RFC` process for pipeline changes.
- Dry-run, eval gates, rollback and explicit user approval.
- Self-development only through RFC artifacts.
- Trace/eval/postmortem stack for regressions and experiments.

## Candidate schemas

- `Concept_Frame.yaml`
- `Sense_State.yaml`
- `Slop_Score.yaml`
- `Detection_Verdict.yaml`
- `Research_Packet.yaml`
- `Pipeline_RFC.yaml`

## Invariants

- No pipeline self-modification without RFC + explicit user approval.
- No raw paths, usernames, env or command lines persisted/exported without allowlist.
- No single AI-detector verdict is treated as definitive.
- Critic/provenance layers are advisory unless policy explicitly blocks action.
- Internet search is packetized, cited, freshness-bounded and source-allowlisted.

## Source material

See `docs/source_reports/deep-research-report-7-sense-privacy-honesty-critics-rfc.md`.

## Research update for alpha

The later typed-governance research pack strengthens this roadmap with explicit `Concept_Frame`, `Sense_State`, `Drive_State`, `Slop_Score`, `Detection_Verdict`, `Research_Packet` and `Pipeline_RFC` contracts. It also confirms the sequencing rule: sensing/privacy and honesty must land before critics/provenance, and self-development must remain RFC-gated.

Additional source: `docs/source_reports/deep-research-report-8-typed-governance-sense-critics-rfc.md`.
