# Evaluation metrics and observability research merge

Status: merged in `0.29.14`.
Sources: `deep-research-report.md`, previous metrics pages.

## Main principle

NoemaForge evaluation must separate:

- model quality,
- retrieval quality,
- tool execution quality,
- agent workflow quality,
- user outcome quality,
- safety and governance quality.

A single aggregate score is not enough.

## Recommended metric groups

| Area | Metrics | Why it matters |
|---|---|---|
| Retrieval | recall@k, precision@k, MRR, nDCG, citation coverage | Prevents semantic garbage in RAG-like flows. |
| Generation | factuality, groundedness, coherence, completeness | Measures answer quality. |
| Code tasks | pass rate, test success, patch size, regression rate | Measures real software usefulness. |
| Agent workflows | task completion, step count, tool error rate, recovery rate | Measures autonomy without hiding failures. |
| Safety | denied unsafe actions, policy hits, capability-token violations | Measures protection layer. |
| Operations | latency, RAM/VRAM use, failed units, restart count | Keeps local-first system usable. |
| Human value | accepted suggestions, edited suggestions, time saved | Connects system metrics to user value. |

## Visualization set

- Retrieval funnel: query → candidates → rerank → cited answer.
- Agent trace timeline: plan → tool calls → failures → recovery.
- Model/provider scorecard: quality, cost, latency, local/cloud, privacy.
- Safety incident board: attempted action, policy rule, result, owner decision.
- Local resource dashboard: RAM, VRAM, swap, failed units, LLM process state.

## Integration with 0.29.x state

The current legacy live-validation host operating context makes resource metrics release-critical: GUI/NVIDIA should start cleanly, NoemaForge LLM should not autostart, and heavy Qwen runs should be manual until a delayed/limited manager policy is implemented.

