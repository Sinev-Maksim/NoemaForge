# Agent loop budgets and trajectory evaluation

Version scope: runtime `0.32.1`, documentation reconciliation `0.32.1-docs-integrated`.  
Updated: 2026-05-18T20:33:59Z

## Budget contract

Agentic loops must be bounded:

```json
{
  "max_steps": 10,
  "time_budget_minutes": 30,
  "max_tool_calls": 50,
  "stop_on_no_improvement": true,
  "checkpoint_every": 1,
  "human_interrupt": true
}
```

## Applies to

- Dev Team improvement loops;
- Model Evolution;
- self-optimization from seed version;
- SmartHome automation planning;
- pipeline editor draft generation;
- RAG answer repair.

## Trajectory evaluation

Evaluate the full path, not only the final text:

```text
intent -> plan -> tool call -> artifact -> eval -> retry -> approval -> final
```

Executable seed:

- `noemaforge/configs/trajectory-eval-suite.json` defines core thresholds and safe final states.
- `production_ai_contracts.evaluate_trajectory(...)` emits a `TrajectoryEvalReport`.
- `production_ai_contracts.trajectory_eval_report_to_gate_evidence(...)` converts the report into EvaluationGate-compatible checks.
- `noemaforge/contracts/trajectory_eval_suite.schema.json` defines the eval-pack shape.

Current checks:

- `trajectory_step_success_rate`;
- `trajectory_artifact_coverage`;
- `trajectory_budget_compliance`;
- `trajectory_safety_flags`;
- `trajectory_safe_final_state`.

## Safe final states

- completed_budget_exhausted;
- completed_time_exhausted;
- stopped_by_operator;
- no_further_improvement_found;
- blocked_by_safety_gate;
- waiting_for_operator_approval.
