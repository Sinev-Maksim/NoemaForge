# Trace, EvaluationGate and Safe Rollout operations

Version scope: runtime `0.31.13.alpha-patched1`, documentation reconciliation `0.31.21.alpha-docs-integrated`.  
Updated: 2026-05-18T20:33:59Z

## Trace-first contract

Every operator-visible action should generate a trace envelope. The executable seed now starts this in:

- Admin GUI messages: persisted message records include `trace_id`.
- Admin GUI job plans: persisted job records include `trace_id`.
- Model-selection plans: `candidate-selection-plan.json`, `model-selection-decision.json` and `rollback_plan.json` include `trace_id`.
- Pipeline runs: run stdout, `manifest.json` and the `pipeline_created` event include `trace_id`.
- Pre-start epoch promotion: `brainctl prestart apply-epoch` writes `release_evidence.json` with the carried or generated `trace_id`.
- ToolProxy requests: request `meta.trace_id` is preserved in tool responses and telemetry records.

```json
{
  "trace_id": "trace_...",
  "conversation_id": "conv_...",
  "message_id": "msg_...",
  "job_id": "job_...",
  "persona": "Admin",
  "model_id": "...",
  "prompt_version": "...",
  "pipeline_id": "...",
  "tool_calls": [],
  "artifacts": [],
  "metrics": {}
}
```

Executable trace coverage validator:

- `noemaforge/src/trace_coverage_runtime.py` checks the Admin GUI message/job, Admin runtime, model-selection, pipeline, epoch apply, ToolProxy and telemetry surfaces.
- `noemaforge/contracts/trace_coverage_report.schema.json` records the expected report shape.
- `noemaforge/tests/test_trace_coverage_runtime.py` verifies the workspace coverage and a failing fixture.

CLI smoke command:

```bash
python noemaforge/src/trace_coverage_runtime.py --project-root . --summary
```

## EvaluationGate

NoemaForge should use one promotion gate shape for:

- code changes;
- prompt changes;
- model/epoch changes;
- RAG index and retriever changes;
- pipeline graph changes;
- routing changes;
- SmartHome action policies.

Executable seed:

- contract module: `noemaforge/src/production_ai_contracts.py`;
- schema: `noemaforge/contracts/production_ai_contracts.schema.json`;
- gate validator: `noemaforge/src/evaluation_gate_runtime.py`;
- validator schema: `noemaforge/contracts/evaluation_gate_validation.schema.json`;
- seed registry: `noemaforge/configs/unified-registry.json`;
- tests: `noemaforge/tests/test_production_ai_contracts.py` and `noemaforge/tests/test_trace_contracts.py`.

Epoch promotion currently wraps the existing `prestart_build_report.json` and `scary_report.json` checks into an `EvaluationGateResult` before release evidence is written.

Prompt and routing promotion now use the same executable contract through `promote_registry_entry(...)`. The helper derives the change domain from the Unified Registry entry, evaluates the required checks, computes a rollout decision, and only updates the registry status when the generated ReleaseEvidence is passing.

CLI smoke command:

```bash
python noemaforge/src/evaluation_gate_runtime.py --summary
```

The validator covers the required checks for code, prompt, model, RAG, pipeline and router changes. It also verifies that missing checks, failed checks and score-below-threshold checks block promotion even when a fixture tries to present itself as passed.

## Safe rollout

The NoemaForge rollout sequence is:

```text
candidate -> offline_eval -> shadow -> canary -> Admin approval -> active -> rollback-ready
```

Shadow/canary are task-class based, not traffic-percentage based, because NoemaForge is local-first and often single-user.

For candidate epoch promotion, `apply-epoch` now maps the final pre-start canary state to:

```text
canary -> promoted
```

and refuses promotion if the release-evidence gate or rollout decision is not passing.

For prompt and routing entries, `promote_registry_entry(...)` enforces:

```text
shadow -> canary -> promoted
```

`promoted` requires a passing gate plus explicit approval. Failed gates leave the registry entry at its previous status.

## ReleaseEvidence

Every promoted epoch should carry:

- `trace_id`;
- change id and domain;
- gate decision and failures;
- rollout decision;
- active registry refs from `unified-registry.json`;
- pointers to build/canary reports.

Current artifact path for epoch promotion:

```text
<candidate_epoch_dir>/release_evidence.json
```

For registry-backed prompt/routing promotion, the evidence is returned as a `RegistryPromotionResult.release_evidence` payload so callers can persist it beside their plan or review artifact before applying a promoted registry file.

## Display and boot safety

Model selection and first-start must preserve display-manager by default. Any headless/display-stop path remains explicit opt-in only and must be excluded from GUI-triggered model-selection jobs.
