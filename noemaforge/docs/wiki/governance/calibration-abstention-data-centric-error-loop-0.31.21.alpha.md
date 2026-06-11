# Calibration, abstention and data-centric error loop

> **Status: historical snapshot (0.31.21.alpha era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

Version scope: runtime `0.32.1`, documentation reconciliation `0.32.1-docs-integrated`.  
Updated: 2026-05-18T20:33:59Z

## Calibration policy

NoemaForge routes should attach a confidence and action:

```text
>= 0.80  route or answer
0.50-0.79 ask clarification
< 0.50 abstain or open help
high risk always requires Admin/SR/SSR approval
```

## Abstention examples

- ambiguous pipeline command;
- missing project path for Dev Team;
- unknown SmartHome device;
- low-confidence model promotion;
- ungrounded RAG answer;
- unsafe tool request.

Executable seed:

- `noemaforge/configs/abstention-policy.json` defines deterministic route/ask/defer/block thresholds.
- `production_ai_contracts.decide_abstention(...)` emits an `AbstentionDecision`.
- `noemaforge/src/abstention_policy_runtime.py` validates threshold ordering, configured action names, action descriptions and policy scenario behavior.
- Admin routing now attaches `route.abstention`; Dev Team code requests without project context become `ask_clarification`.

Supported actions:

```text
route -> ask_clarification -> defer_admin -> defer_sr -> defer_ssr -> block
```

CLI smoke command:

```bash
python noemaforge/src/abstention_policy_runtime.py --project-root . --summary
```

The validation report must pass route, ask clarification, defer Admin, defer SR, defer SSR and block fixtures before the routing policy is treated as promotion-ready.

## Admin routing evaluation

Admin routing evaluation should report both route correctness and abstention correctness. A passing intent-router result means the selected route, interpreted intent and route/ask/defer/block abstention action all match the expected fixture for safety-sensitive commands.

## Data-centric error loop

Each observed failure now has an executable seed artifact in `noemaforge/src/production_ai_contracts.py`.

Core functions:

- `classify_error_observation(...)` assigns component, domain, error type, severity, review needs and labels.
- `build_data_error_loop_artifact(...)` emits a `DataCentricErrorLoopArtifact`.
- `append_error_loop_eval_case(...)` appends the generated eval case to compatible eval packs without duplicating case IDs.

Each observed failure becomes:

1. error taxonomy entry;
2. regression example;
3. task item;
4. eval case;
5. fix candidate;
6. SR/SSR review artifact.

Example:

```json
{
  "error_type": "intent_routing_false_conversation",
  "input": "Запусти evolution по стандартному сценарию",
  "expected": "pipeline:evolution",
  "actual": "smalltalk_fallback",
  "regression_test": "admin_route_evolution_standard"
}
```

Executable artifact shape:

```json
{
  "kind": "DataCentricErrorLoopArtifact",
  "error": {
    "domain": "router",
    "error_type": "intent_routing_mismatch"
  },
  "regression_case": {},
  "eval_case": {},
  "task_item": {},
  "fix_candidate": {},
  "review": {
    "required": true,
    "reviewers_required": ["SR"]
  }
}
```
