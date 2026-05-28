# NoemaForge 0.32.1 — model evolution and model selection

Model evolution remains a measured control-plane process. It creates candidate artifacts and rollback instructions; it does not mutate production weights automatically.

0.32.1 adds a separate model-selection bridge for epoch optimization:

```bash
noemaforge model-selection plan --mode normal --scope "dev team" --json
noemaforge model-selection apply --mode normal --scope "dev team" --json
```

From GUI chat, model optimization is two-step:

1. show candidates and review artifacts;
2. apply epoch switch only after explicit confirmation.

Artifacts include:

```text
candidate-selection-plan.json
model-selection-decision.json
rollback_plan.json
```

Full first-start selection artifacts are produced by `sudo noemaforge first-start --<mode>`.
