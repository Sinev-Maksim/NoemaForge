# NoemaForge roadmap

Status date: 2026-06-10.
Shipped version: **0.32.2** (on `main` via PR #77).
Active development line: `release/0.33.0-dev`.

This is the forward-looking project roadmap. Task-level tracking lives in the
canonical [`noemaforge/docs/TODO.md`](../noemaforge/docs/TODO.md); historical
backlog in [`docs/backlog/ROADMAP_AND_TODO.md`](backlog/ROADMAP_AND_TODO.md).

## Where we are

0.32.2 was validated end-to-end on the production target host
(Debian 13 "Trixie", GNOME/GDM, RTX 3080 Ti) during the 2026-06-08/10 UAT
campaign — see [`docs/uat/`](uat/README.md):

| Layer | State |
|---|---|
| Cutover (BrainOS frozen → NoemaForge owns host) | PASS, reversible backup kept |
| Clean install from GitHub `main` + liveness | PASS (`LIVENESS_UAT_OK`) |
| First-start `--full_composite` real apply | PASS — epoch `00005`, runtime safety clean |
| Display safety during heavy runs | PASS — GDM preserved by default |
| Admin GUI / user-facing experience | **NOT production-ready** — major UI/routing defects |

The runtime core is solid; everything blocking a non-engineer operator sits in
the Admin GUI presentation/routing layer. Those findings (15 defects + 5
tooling/runtime items) are canonically tracked in
[`docs/uat/DEFECT-REGISTER-0.32.2.md`](uat/DEFECT-REGISTER-0.32.2.md).

## 0.33.0 — admin-gui-prod-readiness-fixpack (next up)

Goal: a non-engineer operator can install, start, run a pipeline and receive
the result entirely through the Admin GUI, with no JSON reading and no
filesystem digging. Driven directly by the UAT defect register:

- **P0 — trust and feedback loop:** deterministic glossary answers for known
  system states (D-003); pipeline confirm transfers the command into chat
  (D-005); visible per-run progress (D-007); artifacts delivered into chat as
  cards — the API metadata already exists (U-001/U-005); no silent no-ops —
  every command gets a visible response (U-002).
- **P1 — comprehension:** readable epoch/model-selection panel with tooltips
  and non-stale plan state (D-002); distinct personas, explicit selector,
  return-to-admin flow, pipeline greeting (U-003/D-009); iteration controls
  that visibly attach to the next message (D-008).
- **P2 — presentation polish:** hardware gauges (D-001), readable product
  metrics (D-004), rendered pipeline diagrams (D-006), repeat-launch guard
  (D-010).
- **Runtime/ops follow-ups:** root-cause the one-off
  `llm-backends-manager` failure (R-001); liveness-oriented shipped smoke
  (S-001); UAT helper fixes (O-001/O-002); document the no-TCP-by-default GUI
  posture (O-003).

Already merged on the 0.33.0 line: `noema` CLI suite (start / doctor /
release / upgrade / catalog / policy / ops-ref), presentation layer (README
v2, security front page, scenario pack, published evidence workflow), AAT
suite CI tier, OpenSSF Scorecard workflow, premerge-quality for 0.33.x.

## 0.33.1 — full system independence

NoemaForge runs identically on Linux, macOS and Windows: parity for paths,
service/process management, sockets, exec/sandbox, display safety and the
Admin GUI launcher (builds on the 0.32.2 `platform_paths` migration).
**Acceptance: the AAT suite plus the full test matrix pass identically on all
three OS families.**

## 0.33.2 — hybrid LLM usage

External/hosted LLMs usable alongside local models: a provider-runtime
resolver for the top ~10 providers behind ToolProxy capability tokens and
deny-by-default policy — local credentials, redaction-before-egress,
cost/rate ceilings, explicit operator opt-in. Nothing leaves the machine by
default.

## 0.33.3 — agent-OS maturation (strategic, post-0.32.x)

Promote NoemaForge from a set of **validation-contract runtimes** to a live,
governed multi-agent OS. Validated against the codebase, this milestone is
largely *maturation and enforcement* of subsystems that already exist as
contract validators — not greenfield — organised into nine tracks. The
task-level breakdown, with effort tiers and the existing foundation noted per
item, is in the canonical
[`TODO.md`](../noemaforge/docs/TODO.md#0333-strategic-roadmap-post-032x).

- **Agent governance** — Admin stays the only user-facing authority; specialists
  return results to Admin and cannot terminate conversations. Formal agent
  lifecycle states and an explicit handoff protocol (ownership, reasoning trace,
  confidence) on the existing task-workflow runtime and RoleFlow backlog.
- **Multi-model consensus** — fusion (parallel independent reasoning), a judge
  framework (answer scoring, hallucination/assumption detection) and debate mode,
  on the role-tournament scorer and the Sense/Critic governance backlog.
- **Context engineering** — a live context-budget manager (token accounting,
  memory prioritization, retrieval ranking), a compression pipeline (summarization,
  dedup, fact extraction) and context quality metrics — promoting the
  memory-budgeted and topic-adjacent retrieval contracts.
- **Evaluation framework** — internal SWE-bench / GAIA / AgentBench-inspired
  benchmarks and a regression harness over routing, memory, tools and artifacts,
  extending the AAT suite's LLM tier.
- **Artifact-centric workflows** — every generation pipeline emits artifacts; a
  unified artifact registry with lineage (creator, inputs, generation chain),
  promoting the artifact-registry-table contract and the in-chat artifact cards.
- **Sandbox & security** — per-agent sandbox execution, capability-based
  permissions, tool allowlists and resource quotas (RAM/CPU/GPU/network), hardening
  the existing ToolProxy capability tokens, `caps`/allowlist policy and `sandbox`
  rlimits.
- **Runtime intelligence** — dynamic model routing made cost-, latency- and
  quality-aware, extending the product model-routing surface and the 0.33.2 cost
  ceilings.
- **Observability** — agent execution traces, workflow replay, decision auditing,
  failure classification and a runtime dashboard, maturing the
  trace-observability-evaluation design and the telemetry dashboard.
- **Production readiness** — formal release process, a Stable/LTS channel, a
  migration framework with upgrade rollback, and an automated UAT suite —
  formalising `noema release` / `publish-evidence`, `noema upgrade` rollback and
  the AAT / U-004 track.

Sequencing: 0.33.3 follows 0.33.0–0.33.2, and several tracks (sandbox, hybrid-LLM
routing, AAT) share foundations with earlier milestones and advance incrementally
rather than as one big-bang release.

## Cross-cutting tracks

### Artifact-driven acceptance (AAT) suite

Spec: [`noemaforge/docs/quality/AAT_SUITE.md`](../noemaforge/docs/quality/AAT_SUITE.md).

- **Shipped (CI tier):** harness + workflow with gating cases for checksum
  validation, telemetry privacy, capability tokens, ToolProxy isolation,
  signed-manifest verification, epoch immutability, plus best-effort install
  dry-run. Nightly OpenSSF Scorecard.
- **Pending (target tier):** boot-safety cases (`no_hidden_autostart`,
  `model_warmup_modes`), live ToolProxy smoke, cosign/attestation verify —
  need the target host.
- **Pending (LLM tier):** `grounded_summary`, `safe_refusal_boundary`,
  `toolproxy_event_explainer`, `epoch_diff_interpreter`,
  `cost_ceiling_guard` — need a live model.
- **Pending (GUI tier, from UAT):** the all-pipeline test/demo mode (U-004)
  that runs every pipeline with safe built-in prompts and exports an AAT
  report — this is the operator-visible face of the suite.

### Hardening for non-engineer operators

One-button install/run, plain-language errors with guided recovery, no
terminal/YAML on the happy path, GUI-first flows, safe defaults. The 0.33.0
fixpack is the first concrete slice of this track.

### Documentation and project wiki rewrite

Bring docs and the GitHub wiki up to the current state (noema CLI, AAT,
Scorecard, security/governance front page, scenario pack); keep README v2 as
the landing; per-run UAT reports under [`docs/uat/`](uat/README.md) as the
evidence trail.

### Review pipeline

Keep CI ownership with Codex + Copilot + CodeRabbit; clear actionable review
threads before merge; fold recurring nits into the canonical TODO.

## Recently completed (0.32.x highlights)

- 0.32.2 hardening: Admin GUI session/event wiring, `/api/session/current` +
  `/api/events`, session-mode persistence, history restore, finally-block
  safety fix, cross-platform checksum script, display-safe model selection.
- Typed governance track (Concept_Frame → … → Pipeline_RFC), provenance/
  watermark verdicts, Research_Packet scouting, drag&drop pipeline editor,
  production GUI installer, package dry-run validation — see the closed items
  in [`noemaforge/docs/TODO.md`](../noemaforge/docs/TODO.md).
- 2026-06-08/10: BrainOS → NoemaForge cutover and the full 0.32.2 UAT
  campaign on the target host ([`docs/uat/`](uat/README.md)).

## Invariants that gate every milestone

- No production GitHub Release without explicit human GO + target validation.
- `noema upgrade` never removes/overwrites user or machine state.
- `RUNTIME_VERSION` is assigned only in `noemaforge_version.py`.
- Heavy GPU / model-selection commands always preserve the display by default.
- Self-modification stays lab-only behind Pipeline_RFC + explicit approval.
