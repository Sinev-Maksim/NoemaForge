# Model Evolution Control Plane — 0.31.12

> **Status: historical snapshot (0.31.12 era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

NoemaForge `0.31.12` introduces an invokable, auditable model-evolution control cycle.

Command:

```bash
noemaforge model-evolution run --request 'improve dev role code quality' --json
```

Admin/GUI route:

```bash
noemaforge admin message --execute --message 'эволюция модели для dev роли' --json
```

## What the cycle conducts

The runtime writes a run directory under `/var/lib/noemaforge/model-evolution/runs/` by default and emits:

- `baseline_snapshot.json`
- `mutation_plan.json`
- `scorecard.json`
- `rollback_plan.json`
- `candidate_profile.json`

The cycle is intentionally measured and conservative:

- no implicit training;
- no implicit weight writes;
- no hidden backend start;
- rollback plan required before candidate activation;
- pipeline artifact registration when called with `--pipeline-run-id`.

## Apply semantics

`--apply` writes a local candidate profile only. It does not train, fine-tune, mutate weights or switch production models. Future backend adapters can extend this with explicit LoRA/fine-tune actions once backend-specific rollback manifests exist.

## GUI entrypoint

The Admin GUI exposes `POST /api/model-evolution/run`. It calls the same measured runtime and returns the generated artifact paths inside the browser result panel.

## Target replay evidence

`final-gui-scenario-replay-readiness-core` records the model-evolution leg of the final Admin GUI replay as `blocked_until_target_final_gui_scenario_replay_evidence`. Completion requires the target transcript to show the GUI-routed model-evolution request, response JSON, artifact manifest and rollback plan reference alongside the Admin greeting, routed pipeline and Dev Team evidence. This is a target-machine evidence gate only; the local validator does not execute model-evolution, start a backend or apply a candidate profile.
