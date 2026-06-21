<!--
=== NoemaForge File Header ===
File: noemaforge/docs/reference/LOOP_AWARE_ROLE_RUNTIME_AND_EVOLVER.md
Zone: docs/reference
Version: 0.33.0
Created: 2026-06-18
Modified: 2026-06-18
Purpose: Design reference for the "Loop-Aware Role Runtime + Evolver" strategic increment —
  LoopLM/Ouro-style latent-loop model support, an external Admin exit-gate loop, a registry of
  runtime-actor roles (not personas), and the Evolver role for controlled self-improvement.
Inputs: Owner design session 2026-06-18 (LoopLM support + external Admin-loop + role re-architecture).
Outputs: Roadmap formalization; the actionable checklist lives in noemaforge/docs/TODO.md.
Side effects: None (documentation only).
Tests: docs hygiene; wiki integrity not applicable (reference doc, not a wiki page).
Notes: Forward-looking design; sequence after the 0.33.0-0.33.2 line. English-only.
=== End NoemaForge File Header ===
-->

# Loop-Aware Role Runtime + Evolver

Strategic increment. **XL** umbrella (Fable-orchestrated, mixed executors); sequence after the
0.33.0-0.33.2 line. This document is the design reference; the tracked checklist is the
"Loop-Aware Role Runtime + Evolver" section of [`../TODO.md`](../TODO.md).

It extends and unifies the existing `0.33.3 strategic roadmap` umbrellas in `TODO.md`
(Agent governance, Multi-model consensus, Evaluation framework, Sandbox & security,
Observability) — implement it as the connective contract under them, not a parallel track.

## 1. Architectural goal — two levels of "thinking", never conflated

1. **Internal (model):** LoopLM / latent recurrent loop + a learned exit gate (Ouro-style). The
   model has internal reasoning depth; weights are unchanged at inference; it is not user-visible.
2. **External (system):** an Admin-driven loop between runtime actors —
   Admin -> Worker/Researcher/Coder/Tool -> Reviewer -> Judge -> Surgeon -> Evolver. Logged.

These two levels must never be mixed in logs or naming. An external agent loop is **not**
"latent reasoning."

## 2. Core principle — roles are runtime actors, not personas

A role is defined as:

```
role = responsibility + permissions + inputs + outputs + stop_conditions + audit_trail
```

Drop the idea that "personas differ only by tone." Two roles are load-bearing:

- **Surgeon** = controlled repair: a minimal-viable-incision patch with a rollback plan and the
  right to STOP an unproductive loop. Not "another commenting persona."
- **Evolver** = controlled self-improvement: proposes policy/routing/eval/manifest changes from
  accumulated experience. **Evolver is not Surgeon** — Surgeon fixes one concrete failure;
  Evolver improves future behavior. Evolver never edits prod, never bypasses Surgeon/Judge, and
  never changes model weights outside a training pipeline.

## 3. Loop taxonomy (must not be conflated in logs)

| loop_type | owner | visible | changes |
|---|---|---|---|
| `token_loop` | model | n/a | autoregressive generation |
| `cot_loop` | model | user | visible textual reasoning |
| `agent_loop` | admin | logs | actor handoffs (admin/worker/reviewer/tool) |
| `repair_loop` | surgeon | logs | artifact or config |
| `eval_loop` | judge | logs | score / verdict |
| `latent_loop` | model | **not** user | in-model recurrence; weights unchanged |
| `evolution_loop` | evolver | release process | policy/runtime rules (**proposed only**) |
| `training_loop` | trainer | n/a | weights (**not prod-allowed**) |

Every trace records `loop_type`, `model_architecture`, `external_iteration`, `latent_loop_observed`.

## 4. Role registry (25 runtime actors)

Each role carries a `RoleContract`: `role_id, role_type, permissions, cannot, inputs, outputs,
loop_awareness, stop_conditions, audit_requirements`.

### A. Orchestration
| Role | Responsibility | LoopLM awareness |
|---|---|---|
| Admin / Orchestrator | Owns the task | LoopLM is one backend type, not a replacement for orchestration |
| Intake | Understands the user request | Classifies reasoning vs factual-recall vs artifact vs repair |
| Planner / Architect | Decomposes hard tasks | Marks stages `requires_latent_reasoning` |
| Router / Model Selector | Picks model/role/backend | Picks LoopLM for reasoning/manipulation, not raw recall |
| Budget Controller | Watches cost/time/iterations | Caps external iterations AND LoopLM depth/threshold when available |

### B. Execution
| Role | Responsibility | LoopLM awareness |
|---|---|---|
| Worker / Executor | Primary execution | May use LoopLM as the reasoning backend |
| Researcher | Fetches external facts/sources | Never expects LoopLM to "recall" missing facts; LoopLM links what was found |
| Tool Operator | Calls shell/web/files/APIs | Feeds tool results in; does not trust LoopLM on tool-state without checks |
| Coder / Builder | Code, configs, manifests, scripts | Uses LoopLM for local reasoning over code/architecture |
| Artifact Generator | Documents, archives, reports, files | Uses LoopLM only as a reasoning engine; owns the physical artifact delivery |

### C. Quality
| Role | Responsibility | LoopLM awareness |
|---|---|---|
| Reviewer | Substantive review | Checks LoopLM gave better reasoning, not just confident prose |
| Judge / Evaluator | Score / verdict | Compares standard vs LoopLM vs external-loop by metrics |
| Fact Checker | Factual correctness | Does not trust LoopLM as a fact source; requires retrieval/citations |
| Test Runner / QA | Tests, smoke, regression | Checks the LoopLM backend does not break runtime/latency/memory/API contract |
| Benchmark Curator | Maintains eval sets | Splits memory vs reasoning vs coding vs repair vs multi-hop vs artifact tasks |

### D. Repair & safety
| Role | Responsibility | LoopLM awareness |
|---|---|---|
| Surgeon | Targeted repair | Fixes model manifest, routing, loop thresholds, broken artifacts, runtime failures |
| Security Gatekeeper | Sandbox/permissions/unsafe actions | Stops agents/LoopLM bypassing policy via "internal reasoning" |
| Rollback Manager | Reversible changes | Requires a rollback plan for LoopLM config, routing, Evolver patches |
| Runtime Monitor | Health/latency/errors | Catches max-loop overuse, early-exit failure, latency spikes, backend instability |
| Release Manager | Stable release | Keeps README/roadmap/manifests/registry/API-UI/versioning in sync; gates LoopLM support |

### E. Evolution
| Role | Responsibility | LoopLM awareness |
|---|---|---|
| Evolver | Improves the system from experience | Decides when LoopLM beats standard, when external loop beats LoopLM, when hybrid wins |
| Memory / Librarian | Stores patterns, failures, decisions | Records where LoopLM helped, where it did not, which thresholds worked |
| Policy Designer | Formalizes new rules | Turns Evolver findings into safe policy proposals |
| Model Curator | Owns the model catalog | Maintains capability metadata: loop_lm, early_exit, max_recurrent_steps, thinking_variant |
| Experiment Runner | Controlled experiments | Proves or disproves LoopLM value under controlled tests |

## 5. LoopLM capability schema (model manifest)

```yaml
architecture:
  type: loop_lm            # standard_transformer | reasoning_cot_model | loop_lm | tool_agent_model
  latent_loop: true
  early_exit: true
  weight_tied_recurrence: true
loop:
  min_steps: 1
  max_steps: 4
  default_policy: learned_exit_gate
  configurable_threshold: true
  telemetry_supported: true
fallback:
  if_loop_control_unavailable: run_as_standard_transformer
  mark_capability_degraded: true        # mark loop_control: unavailable
task_affinity:
  strong: [reasoning, math, logic, code_repair, multi_hop]
  weak:   [factual_recall, fresh_news, long_context_retrieval]
```

Backend adapter contract: `supports_loop_depth`, `supports_exit_threshold`,
`supports_early_exit`, `supports_loop_telemetry`. Admin compute modes map to loop control when
supported: `fast` -> lower depth / earlier exit, `balanced` -> default policy, `deep` -> max
useful depth. **Rule:** LoopLM manipulates known knowledge; it does not replace retrieval or
create missing facts. Telemetry per answer: `loop_steps_used`, `early_exit`, `exit_confidence`;
collect latency and quality by loop depth; warn `possible_exit_gate_collapse` when the model
almost always uses max depth.

## 6. Admin as the external exit gate

After each step Admin decides: `accept | retry_same_actor | revise | call_tool |
send_to_reviewer | send_to_surgeon | switch_model | stop_by_budget | escalate_to_user`.

Stop conditions: `min_quality_score`, `max_iterations`, `max_surgeon_passes`,
`max_reviewer_passes`, `max_cost`, `max_latency`, `no_progress_rounds`. **"Good enough" is a
valid terminal outcome** — do not improve forever.

Adaptive compute by difficulty: simple `Admin -> Worker -> Final`; complex
`Admin -> Planner -> Worker -> Reviewer -> Surgeon -> Judge -> Final`; artifacts
`Admin -> Generator -> Validator -> Surgeon -> Exporter -> link`; code
`Admin -> Implementer -> TestRunner -> Surgeon -> RegressionCheck -> patch`.

Admin maps the failure cause to the next actor: weak reasoning -> deeper/LoopLM; missing facts
-> Researcher/RAG; broken artifact -> Surgeon; unstable score -> Judge/TestRunner.

**Anti-loop protection:** `same_answer_detector`, a novelty score (each iteration must change the
solution), no-progress stop (2 rounds without score gain -> stop/escalate), and a `loop_budget`.
Log the stop reason: `accepted_by_judge | budget_exhausted | no_progress |
manual_escalation_required | runtime_error`.

## 7. Surgeon — repair actor on both levels

Inputs: task_context, model_manifest, backend_logs, loop_telemetry, judge_report, test_failures,
previous_attempts, diff, constraints. Can repair: model manifest, loop thresholds, routing
policy, backend adapter, telemetry mapping, artifact export pipeline, failed release config, and
code/configs/pipeline-registry/generated-docs/broken-exports.

Structured output (`surgeon_report`): diagnosis, patch[], risk, rollback[], requires_judge,
requires_release_manager — a controlled "minimal viable incision", diff-style (`Changed / Why /
Risk / Rollback`), never a full rewrite.

LoopLM diagnoses: always exits at max depth; exits too early; quality does not rise with depth;
latency spikes; backend ignores loop params. Safe fixes: change `exit_threshold`, lower
`max_steps`, switch routing policy, disable a loop-control override, revert to standard mode.
Never "fix" a backend/runtime config problem with a prompt. Surgeon may **stop** applying a
LoopLM backend in prod when quality is unstable, latency unpredictable, telemetry missing, early
exit not observable, or rollback unavailable — and may declare a problem architectural rather
than surgical.

## 8. Evolver — controlled self-improvement

```yaml
role_id: evolver
role_type: system_improvement
permissions: [read_traces, read_eval_results, propose_policy_change, propose_role_change, propose_model_routing_change]
cannot: [modify_prod_directly, bypass_surgeon, bypass_judge, change_model_weights_without_training_pipeline]
```

Analyzes task outcomes, role failures, routing mistakes, LoopLM usefulness, cost/quality
tradeoffs, surgeon/judge reports, rollback events. Emits an `evolution_proposal`
(observation, hypothesis, proposed_change, affected_roles, affected_models, expected_gain, risks,
evaluation_plan, rollback_plan). Evolver does not apply changes directly; a single good result is
not proof; never optimize to a single benchmark.

Promotion flow:

```
Evolver proposal
  -> Policy Designer formalizes
  -> Experiment Runner tests
  -> Judge evaluates
  -> Surgeon prepares patch
  -> Security Gatekeeper checks
  -> Release Manager packages
  -> Admin approves
```

## 9. Loop-aware architecture flow

```
User -> Intake -> Admin/Orchestrator
     -> Planner | Router | BudgetController
     -> Worker / Researcher / Coder / ToolOperator / ArtifactGenerator
     -> Reviewer -> Judge
     -> Admin decision { accept | retry | tool | surgeon | switch_model | stop }
     -> Surgeon (if repair needed) -> TestRunner/QA -> Exporter
     -> RuntimeMonitor + MemoryLibrarian
     -> Evolver -> PolicyDesigner -> ExperimentRunner -> Judge -> Surgeon
        -> SecurityGatekeeper -> ReleaseManager -> Admin approval
```

## 10. The loop family (the key correction)

- **Admin-loop** -> manages the task.
- **Latent LoopLM** -> gives the model internal reasoning depth.
- **Surgeon-loop** -> fixes concrete failures.
- **Eval-loop** -> checks quality.
- **Evolution-loop** -> improves the system itself.
- **Release-loop** -> introduces improvements into prod safely.

Evolver closes the gap between "we fixed it" and "we got better." Without it NoemaForge stays an
execution system; with it, it becomes a system of accumulated experience and controlled
self-improvement.

## 11. Common contracts

- **Role split:** Admin = orchestration, Worker = execution, Reviewer = meaning, Judge =
  score/verdict, Surgeon = repair/rollback/stabilize, Exporter = deliver the artifact.
- **Unified `loop_context` object:** `task_id, loop_type, iteration, actor, model_architecture,
  artifact_state, quality_score, blocking_issues, next_action`.
- **Per-loop diagnostics:** why it started, who started it, the goal, what changed, why it
  stopped. For Surgeon also: what broke, what was fixed, the risk, and how to roll back.
