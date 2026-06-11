# NoemaForge Typed Control Plane, Sense Layer, Critics and Pipeline RFC Roadmap — 0.32.1

> **Status: historical snapshot (0.31.13.alpha era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

Tracking ID: `NFG-ARCH-0.32.1-typed-governance-sense-critics-rfc`
Status: alpha-prep backlog/wiki inclusion only. Runtime impact: none.

This page incorporates the latest research pack into the NoemaForge alpha roadmap after the global rename. It extends the existing Sense / Privacy / Honesty / Critics / Pipeline-RFC roadmap with a stricter architecture order and data-contract emphasis.

## Dependency order

```text
Concept_Frame
  -> Sense_Layer / Privacy_Filter
  -> Honesty Protocol / Slop_Score
  -> Critic_Stack / Provenance / Detection_Verdict
  -> Internet_Scout / Research_Packet
  -> Pipeline_RFC / self-development gates
```

## P0 foundation

- `Concept_Frame` schema for Admin and Architect role requests.
- Policy gates for dangerous role actions.
- Coarse host telemetry only: CPU, RAM, disk, network and load.
- `Privacy_Filter` before persistence/export.
- Bounded `Drive_Adapter`: pressure, fatigue, urgency, curiosity with clipping, hysteresis and cooldown.
- `Honesty Protocol`: `Unknown`, `Need-Research`, and traceable `Error_Attribution`.

## P1 quality/provenance layer

- `Slop_Score` v1 with thresholds and `allow/revise/abstain/escalate`.
- `Critic_Stack` v1 for text, provenance and slop.
- C2PA / Content Credentials hooks where applicable.
- Watermark hooks where applicable.
- `Detection_Verdict` as an aggregate advisory result, never as a single-detector truth claim.
- `Research_Packet` with source allowlist, freshness window and citation bundle.
- Modality critics for image/video/audio.

## P2 self-development layer

- `Pipeline_RFC` for every pipeline mutation.
- Dry-run, static review, eval report, rollback pointer and explicit approval.
- Self-development must not apply changes directly; it can draft/simulate without approval.
- All accepted RFCs must have trace IDs and release evidence.

## Candidate contracts

```text
Concept_Frame.yaml
Sense_State.yaml
Drive_State.yaml
Slop_Score.yaml
Detection_Verdict.yaml
Research_Packet.yaml
Pipeline_RFC.yaml
```

## Invariants

- No pipeline self-modification without `Pipeline_RFC` + explicit user approval.
- No raw paths, usernames, environment variables or command lines exported without allowlist.
- No single AI-generation detector is treated as authoritative.
- Provenance and critics are layered advisory signals unless policy explicitly blocks action.
- Internet scouting is packetized, cited, freshness-bounded and source-allowlisted.

## Source

See `docs/source_reports/deep-research-report-8-typed-governance-sense-critics-rfc.md`.
