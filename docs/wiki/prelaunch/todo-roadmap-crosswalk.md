# TODO / Roadmap / Research Crosswalk

## Merge decision

0.32.1 treats `0.29.11 recovery/stability` as the executable baseline and merges research into GitHub wiki, prelaunch tooling, and issue-ready planning.

## P0 continuity

| Existing P0 item | Research/context merge | 0.32.1 action |
|---|---|---|
| Patch firstboot smoke under `pipefail` | Recovery reports confirm false-negative smoke risk | Keep as P0 runtime issue; document in wiki |
| Archive accepted degraded first-run baseline | Research emphasizes boring reliability | Keep as P0; add prelaunch forensic bundle direction |
| Confirm post-reboot health | Debug context stresses GUI/LLM separation | Keep as P0; link to recovery/stability notes |

## P0.1 quality semantics

Research reinforces that degraded-but-selected is a valid state. The TODO item should become a formal bootstrap state machine:

```text
unstaffed → degraded_selected → meets_target
```

Promotion should be blocked only when mandatory roles are unstaffed or all scorecards are zero.

## P0.2 inventory and evaluation

Merged additions:

- embedding/model versioning belongs to inventory metadata;
- CPU and GPU scorecards must be separate;
- runtime cost and model load/unload time should be captured;
- EvalPack format should become a contribution unit.

## P0.3 Trixie launcher

Merged additions:

- launcher must stay idempotent;
- must support mount normalization;
- must verify `llama-server` binary and shared libraries;
- must gate backend/gateway/toolproxy health before firstboot;
- must produce forensic bundle on failure;
- must avoid boot-time heavy model activation.

## P0.4 operator usability

Merged additions:

- NoemaShell Lite should expose pause/status/recovery;
- GUI rescue should be safe even when LLM was previously active;
- ChatGPT/browser memory mitigation should remain documented for low-RAM debugging.

## P1 public MWP

Merged additions:

- `noemaforge status` and `noemaforge doctor` should include plain-language explanations;
- model recommendations should be tiered by RAM/VRAM;
- role packs and role flows should be visible as GitHub wiki concepts;
- local TUI/web shell should use the same state machine as CLI.

## Evolve backlog

Merged additions:

- adapter-first mutation;
- safetensors provenance;
- EvalPack-based promotion gates;
- Scary hidden gates;
- Admin final approval;
- canary and rollback.

## Memory architecture backlog

New issue candidates:

- define memory layer schemas: working, personal, vault, events;
- add embedding/version metadata to indexed artifacts;
- document hybrid search policy;
- define router/reranker interface;
- decide local HNSW implementation for personal memory.
