# NoemaForge Evolve Lab Roadmap

## Core invariant

The Evolve contour must not allow NoemaForge to mutate production without external gates.

Allowed flow:

```text
Admin → Surgeon → Scary → Evolver/Darwin → Surgeon → Scary → Admin
                          ↓
                         SR
```

## Role boundaries

| Role | Does | Does not do |
|---|---|---|
| Admin | Owns rights, task admission, final approval | Does not blindly auto-promote mutations |
| Surgeon | Frames experiment, prepares lab, verifies result, writes promotion proposal | Does not mutate and approve its own work |
| Scary | Safety/SSR guard, hidden gates, constraints, final safety verdict | Does not optimize for usefulness at safety expense |
| Evolver/Darwin | Executes mutation inside the lab | Does not touch production directly |
| SR | Scores usefulness, cost, role contribution, next-task priority | Does not replace Admin approval |

## Preferred mutation strategy

Prelaunch should prefer adapter-first mutation:

- LoRA / PEFT adapters;
- small `safetensors` patches;
- explicit provenance metadata;
- eval harness before promotion;
- canary and rollback.

## PEFT/LoRA readiness gate

The first PEFT/LoRA implementation slice is a disabled readiness contract, not
a training backend:

- `noemaforge/configs/peft-lora-lab-policy.json`
- `noemaforge/contracts/peft_lora_lab_policy.schema.json`
- `noemaforge/src/peft_lora_lab_runtime.py`
- `noemaforge/tests/test_peft_lora_lab_runtime.py`

The policy requires EvaluationGate evidence, a rollback manifest, dataset
classification, resource guard, trace IDs and Admin/SR/SSR review. It also keeps
`training_enabled=false`, `weight_mutation_enabled=false`, network denied, and
`writes_production_weights=false` until a future explicit backend adapter is
approved.

Local validation:

```bash
python noemaforge/src/peft_lora_lab_runtime.py --project-root . --summary
```

This closes the roadmap item as an executable readiness gate while preserving
the rule that no production weights or adapters are created by the prelaunch
archive.

## Promotion dossier

Every promotion proposal should include:

- mutation goal;
- changed artifacts;
- dataset/eval pack used;
- quality deltas;
- runtime/cost impact;
- safety results;
- rollback command;
- Admin decision.

## Forbidden shortcut

```text
Surgeon designs → Surgeon mutates → Surgeon evaluates → Surgeon promotes
```

This collapses separation of duties and must remain disallowed.
