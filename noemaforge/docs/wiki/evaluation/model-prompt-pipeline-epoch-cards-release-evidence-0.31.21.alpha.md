# Model, Prompt, Pipeline, Epoch cards and Release Evidence

> **Status: historical snapshot (0.31.21.alpha era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

Version scope: runtime `0.32.1`, documentation reconciliation `0.32.1-docs-integrated`.  
Updated: 2026-05-18T20:33:59Z

## Cards

NoemaForge now has an executable seed contract for reviewable cards generated from Unified Registry entries:

- `ModelCard`;
- `PromptCard`;
- `PipelineCard`;
- `EpochCard`;
- `ToolPolicyCard`;

The implementation lives in `noemaforge/src/production_ai_contracts.py`:

- `build_artifact_card(...)` creates one card from a registry entry.
- `build_registry_cards(...)` creates a `ProductionAICardSet` and reports card coverage.
- `normalize_artifact_card(...)` validates the executable shape before persistence or review.

Future card families remain planned:

- Dataset Datasheet;
- RAG Index Card.

## Shared card fields

```json
{
  "apiVersion": "noemaforge.production-ai/v1",
  "kind": "ModelCard|PromptCard|PipelineCard|EpochCard|ToolPolicyCard",
  "card_id": "registry-kind:id:version",
  "artifact": {
    "kind": "model|prompt|pipeline|epoch|tool-policy",
    "id": "...",
    "version": "...",
    "status": "draft|shadow|canary|promoted|rolled_back",
    "refs": [],
    "eval_pack_refs": []
  },
  "evaluation": {
    "eval_pack_refs": [],
    "latest_gate": {}
  },
  "rollout": {
    "status": "shadow|canary|promoted",
    "latest_rollout": {}
  },
  "rollback": {
    "available": true,
    "plan": "..."
  },
  "release_evidence_refs": []
}
```

## Release Evidence

Every release or promoted epoch should include:

- manifests and checksums;
- version audit;
- consistency audit;
- eval gates;
- registry deltas;
- boot/display safety evidence;
- rollback evidence;
- SR/SSR review status.
