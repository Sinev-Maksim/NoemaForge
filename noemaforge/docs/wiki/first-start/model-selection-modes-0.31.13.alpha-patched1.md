# NoemaForge 0.31.13.alpha-patched1 — first-start model selection modes

0.31.13.alpha-patched1 introduces explicit first-start model-selection modes and warmup-gated scoring.

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

## What does optimize model for Dev Team mean?

“Optimize model for Dev Team” means choosing the best local model profile for developer workflows, including code-oriented prompts, tool-use readiness, safe rollback context and trace evidence. The Admin/chat bridge should answer this as a model-selection planning request, not as an immediate pipeline launch.

The answer must preserve the selected mode, candidate evidence, rollback plan and `trace_id` so the operator can audit why a model was recommended for Dev Team work.

## CPU/GPU matrix readiness

The full canonical model evaluation matrix is a target-machine evidence task, not a local prelaunch shortcut. `canonical-model-eval-matrix-readiness-core` keeps the item in `blocked_until_canonical_model_matrix_evidence` until NoemaForge has both CPU and GPU scorecards for the canonical model list, with the scorecards stored in their device-qualified namespaces.

The offline contract verifies the shape of the future run before the machine is available: canonical model inventory must resolve through `model-profiles.yaml` and `model-eval-suite.yaml`; CPU and GPU runs must be recorded separately through the scorecard separation policy; role coverage and eval-suite coverage must be traceable through firstboot evaluation and role tournament artifacts; failed or excluded candidates must stay out of selected role maps; and the final bundle must record transcript, scorecard hash and operator review evidence. The local validator only checks that manifest, registry and documentation surface. It does not run model evaluations or claim the matrix is complete.
