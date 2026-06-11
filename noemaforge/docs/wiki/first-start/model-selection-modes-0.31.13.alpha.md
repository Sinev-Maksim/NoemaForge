# NoemaForge 0.32.1 — first-start model selection modes

> **Status: historical snapshot (0.31.13.alpha era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

0.32.1 introduces explicit first-start model-selection modes and warmup-gated scoring.

## Why

The 0.31.12 rerun showed that stock selection could score candidates while the backend still returned `http_503: Loading model`. This pre-alpha treats failed, empty, or loading backend calls as zero-score and not eligible for selection.

## Modes

```bash
sudo noemaforge first-start --fast
sudo noemaforge first-start --normal
sudo noemaforge first-start --full
sudo noemaforge first-start --full_composite 3
sudo noemaforge first-start --full_composite 0
```

- `--fast`: first measured suitable candidate; hard constraints such as QA != Developer remain active; no composite testing.
- `--normal`: keep at least two suitable candidates per critical role when available, then choose the measured best; no composite testing.
- `--full`: evaluate all runnable models and choose the measured best per role; no composite testing.
- `--full_composite N`: evaluate all runnable models, then build a composition plan from top N candidates. `N=0` removes the top-N limit before the safety enumeration cap.

## Warmup gate

For each candidate:

1. start backend;
2. wait for socket;
3. send READY probe;
4. require a non-empty READY answer;
5. only then run eval tasks.

If warmup fails, the candidate is marked `warmup_failed`. If calls are empty, failed, or still loading, the candidate receives `selection_status=invalid_backend_calls` and score zero.

## Artifacts

The canonical bootstrap directory records:

```text
candidate-selection-plan.json
role-candidate-map.json
model-run-records.json
model-selection-decision.json
rollback_plan.json
composite-selection-plan.json
```

## Chat bridge

`noemaforge model-selection plan|apply` creates review artifacts from GUI/chat and maps the operator’s selected mode to the equivalent `sudo noemaforge first-start ...` command.
