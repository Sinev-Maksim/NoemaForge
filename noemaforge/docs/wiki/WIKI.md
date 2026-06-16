# NoemaForge wiki hub

The single entry point into the NoemaForge knowledge base. Articles live one
per page under category folders; this hub indexes all of them. Three statuses:

- **Maintained** — current-state articles; updated in the same PR as the
  behavior they describe.
- **Evergreen reference** — unversioned design/reference pages; expected to
  stay broadly accurate, reviewed when touched.
- **Historical archive** — versioned snapshots (`-0.31.12`, `-0.32.1`, …);
  banner-marked, kept as release-evidence history, never edited for content.

Editing rules live in [README.md](README.md); research material enters only
via the [Deep Research Integration Policy](governance/deep-research-integration-policy.md).
The premerge wiki integrity check fails on broken links or pages missing from
this hub; merges to `main` auto-publish this tree to the GitHub Wiki.

## Maintained current-state articles

| Article | What it covers |
|---|---|
| [System overview](architecture/system-overview.md) | The current architecture: services, sockets, invariants, epochs, roles, operator surfaces |
| [Admin GUI — current state](gui/admin-gui-current-state.md) | Honest GUI status after the 2026-06-10 target-host UAT, fixpack P0/P1/P2 |
| [Desktop app shell decision](architecture/desktop-app-shell.md) | Accepted lightweight path to a windowed-app experience (app-mode launcher + PWA) |
| [noema CLI](operations/noema-cli.md) | The operator front door: start / doctor / release / upgrade / policy / catalog |
| [Acceptance testing (AAT)](qa/acceptance-testing-aat.md) | The artifact-driven acceptance suite: shipped CI tier, pending target/LLM/GUI tiers |
| [Release engineering](release/release-engineering.md) | Branch model, CI gates, release evidence, provenance, hard rules |
| [Deep Research Integration Policy](governance/deep-research-integration-policy.md) | How research dumps become wiki prose; why consolidated dumps are retired |

## Evergreen reference

<!-- wiki-index:evergreen:start -->
- [AI OS Memory Architecture: Embeddings, Vector DBs, and Routing](architecture/memory-vector-architecture.md)
- [Product Kernel, Shell, and Contribution Units](architecture/product-kernel-and-shell.md)
- [Self-improvement test and telemetry loop](architecture/self-improvement-test-telemetry-loop.md)
- [Self-improvement architecture: test cases + telemetry + regression gates](architecture/self-improvement-test-telemetry.md)
- [Mender Update Module placeholder](edge/mender-module-model-update-readme.md)
- [RAUC Bundle Notes](edge/rauc-bundle-notes.md)
- [NoemaForge Evolve Lab Roadmap](evolve/evolve-lab-roadmap.md)
- [Repository hardening (public repo)](governance/repository-hardening.md)
- [Evaluation, Observability, and Team Metrics](metrics/eval-observability-metrics.md)
- [Self-test resource metrics](metrics/selftest-resource-metrics.md)
- [Testbench and regression metrics](metrics/testbench-and-regression-metrics.md)
- [Recovery/Stability Notes for Debian Trixie](operations/recovery-stability-trixie.md)
- [NoemaForge Pipelines](pipelines/README.md)
- [Pipeline: code_dev_qa_subteam](pipelines/code-dev-qa-subteam.md)
- [Self-improvement pipelines](pipelines/self-improvement-pipelines.md)
- [Wiki incremental patch pipeline](pipelines/wiki-incremental-patch-pipeline.md)
- [Prelaunch Tooling](prelaunch/prelaunch-tooling.md)
- [TODO / Roadmap / Research Crosswalk](prelaunch/todo-roadmap-crosswalk.md)
- [Code-dev QA sub-team](qa/code-dev-qa-subteam.md)
- [GUI recovery from TTY on Debian Trixie](recovery/gui-recovery-tty-trixie.md)
- [Governance and quality loop (local-first)](safety/governance-quality-loop.md)
- [Tool gap matrix and feature import backlog](tools/tool-gap-matrix.md)
<!-- wiki-index:evergreen:end -->

## Historical archive

Versioned snapshots grouped by category. Each page carries a status banner;
filenames keep their original release markers.

<!-- wiki-index:archive:start -->
### (root)

- [Strict Markdown placement](strict-markdown-placement-0.31.21.alpha.md) — `0.31.21.alpha`

### agents

- [Agent loop budgets and trajectory evaluation](agents/agent-loop-budgets-and-trajectory-evaluation-0.31.21.alpha.md) — `0.31.21.alpha`

### architecture

- [NoemaForge consolidated MVP kernel and shell roadmap](architecture/consolidated-mvp-kernel-roadmap-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge consolidated MVP kernel and shell roadmap](architecture/consolidated-mvp-kernel-roadmap-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge consolidated MVP kernel and shell roadmap](architecture/consolidated-mvp-kernel-roadmap-0.32.1.md) — `0.32.1`
- [Production AI lifecycle integration for NoemaForge](architecture/production-ai-lifecycle-registry-trace-evaluation-0.31.21.alpha.md) — `0.31.21.alpha`
- [NoemaForge Typed Control Plane, Sense Layer, Critics and Pipeline RFC Roadmap — 0.32.1](architecture/typed-control-plane-sense-critics-rfc-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge Typed Control Plane, Sense Layer, Critics and Pipeline RFC Roadmap — 0.32.1](architecture/typed-control-plane-sense-critics-rfc-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge Typed Control Plane, Sense Layer, Critics and Pipeline RFC Roadmap — 0.32.1](architecture/typed-control-plane-sense-critics-rfc-0.32.1.md) — `0.32.1`

### edge

- [NFG-PROP-0.32.1-edge-ml-pack — Edge / TinyML / OTA backlog](edge/edge-tinyml-ota-roadmap-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NFG-PROP-0.32.1-edge-ml-pack — Edge / TinyML / OTA backlog](edge/edge-tinyml-ota-roadmap-0.31.13.alpha.md) — `0.31.13.alpha`
- [NFG-PROP-0.32.1-edge-ml-pack — Edge / TinyML / OTA backlog](edge/edge-tinyml-ota-roadmap-0.32.1.md) — `0.32.1`

### evaluation

- [Model, Prompt, Pipeline, Epoch cards and Release Evidence](evaluation/model-prompt-pipeline-epoch-cards-release-evidence-0.31.21.alpha.md) — `0.31.21.alpha`

### evolution

- [Model Evolution Control Plane — 0.31.12](evolution/model-evolution-control-plane-0.31.12.md) — `0.31.12`
- [NoemaForge 0.32.1 — model evolution and model selection](evolution/model-evolution-control-plane-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — model evolution and model selection](evolution/model-evolution-control-plane-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — model evolution and model selection](evolution/model-evolution-control-plane-0.32.1.md) — `0.32.1`

### first-start

- [NoemaForge 0.32.1 display-preservation P0 fix](first-start/display-preservation-p0-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — emergency GUI recovery](first-start/emergency-gui-recovery-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — emergency GUI recovery](first-start/emergency-gui-recovery-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — emergency GUI recovery](first-start/emergency-gui-recovery-0.32.1.md) — `0.32.1`
- [NoemaForge 0.32.1 — first-start watchdog and hang fix](first-start/firststart-watchdog-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — first-start watchdog and hang fix](first-start/firststart-watchdog-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — full composite real launch](first-start/full-composite-real-launch-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — full composite real launch](first-start/full-composite-real-launch-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — full composite real launch](first-start/full-composite-real-launch-0.32.1.md) — `0.32.1`
- [NoemaForge 0.32.1: live runtime and model-selection fixes](first-start/live-runtime-selection-fixes-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1: live runtime and model-selection fixes](first-start/live-runtime-selection-fixes-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1: live runtime and model-selection fixes](first-start/live-runtime-selection-fixes-0.32.1.md) — `0.32.1`
- [NoemaForge 0.32.1 — first-start model selection modes](first-start/model-selection-modes-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — first-start model selection modes](first-start/model-selection-modes-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — first-start model selection modes](first-start/model-selection-modes-0.32.1.md) — `0.32.1`
- [NoemaForge 0.32.1 — TTY status, GUI restore and interrupt recovery](first-start/tty-status-gui-recovery-interrupt-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — TTY status, GUI restore and interrupt recovery](first-start/tty-status-gui-recovery-interrupt-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — TTY status, GUI restore and interrupt recovery](first-start/tty-status-gui-recovery-interrupt-0.32.1.md) — `0.32.1`

### governance

- [Calibration, abstention and data-centric error loop](governance/calibration-abstention-data-centric-error-loop-0.31.21.alpha.md) — `0.31.21.alpha`
- [MCP and A2A as zero-trust extension boundaries](governance/mcp-a2a-zero-trust-extension-boundaries-0.31.21.alpha.md) — `0.31.21.alpha`

### gui

- [NoemaForge 0.32.1 — Admin Chat, locales, artifacts](gui/admin-chat-locales-and-artifacts-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — Admin Chat, locales, artifacts](gui/admin-chat-locales-and-artifacts-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — Admin Chat, locales, artifacts](gui/admin-chat-locales-and-artifacts-0.32.1.md) — `0.32.1`
- [Admin Console and Admin Routing — 0.31.12](gui/admin-console-and-admin-routing-0.31.12.md) — `0.31.12`
- [NoemaForge 0.32.1 — Admin routing](gui/admin-console-and-admin-routing-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — Admin routing](gui/admin-console-and-admin-routing-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — Admin routing](gui/admin-console-and-admin-routing-0.32.1.md) — `0.32.1`
- [NoemaForge 0.32.1 — Epoch visualization, depth controls and usecase help](gui/epoch-visualization-depth-and-usecases-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — Epoch visualization, depth controls and usecase help](gui/epoch-visualization-depth-and-usecases-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — Epoch visualization, depth controls and usecase help](gui/epoch-visualization-depth-and-usecases-0.32.1.md) — `0.32.1`
- [Persona Portraits and Dashboard — 0.31.10](gui/persona-portraits-and-dashboard-0.31.10.md) — `0.31.10`
- [Persona Portraits and Dashboard — 0.31.11](gui/persona-portraits-and-dashboard-0.31.11.md) — `0.31.11`
- [Persona Portraits and Dashboard — 0.31.12](gui/persona-portraits-and-dashboard-0.31.12.md) — `0.31.12`
- [NoemaForge 0.32.1 — persona portraits and Admin Chat](gui/persona-portraits-and-dashboard-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — persona portraits and Admin Chat](gui/persona-portraits-and-dashboard-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — persona portraits and Admin Chat](gui/persona-portraits-and-dashboard-0.32.1.md) — `0.32.1`
- [NoemaForge stateful Admin GUI shell](gui/stateful-admin-gui-shell-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge stateful Admin GUI shell](gui/stateful-admin-gui-shell-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge stateful Admin GUI shell](gui/stateful-admin-gui-shell-0.32.1.md) — `0.32.1`
- [NoemaForge 0.32.1 — Stateful GUI Shell](gui/stateful-gui-shell-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — Stateful GUI Shell](gui/stateful-gui-shell-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — Stateful GUI Shell](gui/stateful-gui-shell-0.32.1.md) — `0.32.1`

### knowledge

- [Production RAG, grounding and documentation index](knowledge/production-rag-grounding-and-docs-index-0.31.21.alpha.md) — `0.31.21.alpha`

### metrics

- [Evaluation metrics and observability research merge](metrics/eval-observability-metrics-02914.md) — `02914`
- [NoemaForge telemetry and metrics model](metrics/metrics-model-0.32.1.md) — `0.32.1`

### multimodal

- [Multimodal Vault Readiness — 0.31.10](multimodal/multimodal-vault-readiness-0.31.10.md) — `0.31.10`
- [Multimodal Vault Readiness — 0.31.11](multimodal/multimodal-vault-readiness-0.31.11.md) — `0.31.11`
- [Multimodal Vault Readiness — 0.31.12](multimodal/multimodal-vault-readiness-0.31.12.md) — `0.31.12`
- [NoemaForge 0.32.1 — multimodal vault readiness](multimodal/multimodal-vault-readiness-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — multimodal vault readiness](multimodal/multimodal-vault-readiness-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — multimodal vault readiness](multimodal/multimodal-vault-readiness-0.32.1.md) — `0.32.1`

### multios

- [NoemaForge MultiOS Runtime Host Roadmap — 0.32.1](multios/multios-runtime-host-roadmap-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge MultiOS Runtime Host Roadmap — 0.32.1](multios/multios-runtime-host-roadmap-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge MultiOS Runtime Host Roadmap — 0.32.1](multios/multios-runtime-host-roadmap-0.32.1.md) — `0.32.1`

### operations

- [Trace, EvaluationGate and Safe Rollout operations](operations/trace-observability-evaluation-gates-safe-rollout-0.31.21.alpha.md) — `0.31.21.alpha`
- [Trixie recovery operating rule — 0.29.14](operations/trixie-recovery-operating-rule-02914.md) — `02914`

### personas

- [NoemaForge 0.32.1 — Persona Portraits and Fallback Avatars](personas/persona-portrait-fallback-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — Persona Portraits and Fallback Avatars](personas/persona-portrait-fallback-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — Persona Portraits and Fallback Avatars](personas/persona-portrait-fallback-0.32.1.md) — `0.32.1`

### pipelines

- [NoemaForge 0.32.1 — Pipeline Dock and Editor Plan](pipelines/pipeline-dock-editor-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — Pipeline Dock and Editor Plan](pipelines/pipeline-dock-editor-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — Pipeline Dock and Editor Plan](pipelines/pipeline-dock-editor-0.32.1.md) — `0.32.1`
- [NoemaForge 0.31.01 — Pipeline member cells](pipelines/pipeline-member-cells.md)

### prelaunch

- [Prelaunch tools — 0.29.14](prelaunch/prelaunch-tools-02914.md) — `02914`
- [Roadmap / TODO crosswalk — 0.29.14](prelaunch/todo-roadmap-crosswalk-02914.md) — `02914`

### qa

- [NoemaForge 0.31.01 — Pipeline member cells](qa/code-dev-member-cell.md)
- [NoemaForge 0.32.1 code-header and signature audit](qa/code-header-and-signature-audit-0.32.1.md) — `0.32.1`

### recovery

- [NoemaForge 0.31.01 — full first-start UI validation](recovery/first-start-ui-validation.md)
- [GUI live reboot stabilization — 0.31.10](recovery/gui-live-reboot-stabilization-0.31.04.md) — `0.31.04`

### release

- [NoemaForge 0.32.1 code-header and signature audit](release/code-header-and-signature-audit-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 code-header and signature audit](release/code-header-and-signature-audit-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 manifest completeness](release/manifest-completeness-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 manifest completeness](release/manifest-completeness-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 manifest completeness](release/manifest-completeness-0.32.1.md) — `0.32.1`
- [NoemaForge public launch and marketing package](release/marketing-launch-package-legacy-public.md)

### runtime

- [Release Notes — NoemaForge 0.31.03](runtime/autostart-llm-policy.md)
- [Autostart runtime policy — 0.31.10](runtime/autostart-runtime-policy-0.31.04.md) — `0.31.04`

### safety

- [NoemaForge Sense / Privacy / Honesty / Critics / Pipeline-RFC Roadmap — 0.32.1](safety/sense-privacy-honesty-critics-rfc-roadmap-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge Sense / Privacy / Honesty / Critics / Pipeline-RFC Roadmap — 0.32.1](safety/sense-privacy-honesty-critics-rfc-roadmap-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge Sense / Privacy / Honesty / Critics / Pipeline-RFC Roadmap — 0.32.1](safety/sense-privacy-honesty-critics-rfc-roadmap-0.32.1.md) — `0.32.1`

### smarthome

- [NoemaForge local-first smart-home control backlog](smarthome/local-first-smart-home-control-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge local-first smart-home control backlog](smarthome/local-first-smart-home-control-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge local-first smart-home control backlog](smarthome/local-first-smart-home-control-0.32.1.md) — `0.32.1`

### tasks

- [NoemaForge 0.32.1 — Tasks and Inactivity Policy](tasks/inactivity-and-task-governance-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — Tasks and Inactivity Policy](tasks/inactivity-and-task-governance-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — Tasks and Inactivity Policy](tasks/inactivity-and-task-governance-0.32.1.md) — `0.32.1`
- [NoemaForge task governance and idle policy](tasks/task-governance-and-idle-policy-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge task governance and idle policy](tasks/task-governance-and-idle-policy-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge task governance and idle policy](tasks/task-governance-and-idle-policy-0.32.1.md) — `0.32.1`

### telemetry

- [NoemaForge telemetry and metrics model](telemetry/metrics-model-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge telemetry and metrics model](telemetry/metrics-model-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — Telemetry and Metrics](telemetry/runtime-product-metrics-0.31.13.alpha-patched1.md) — `0.31.13.alpha-patched1`
- [NoemaForge 0.32.1 — Telemetry and Metrics](telemetry/runtime-product-metrics-0.31.13.alpha.md) — `0.31.13.alpha`
- [NoemaForge 0.32.1 — Telemetry and Metrics](telemetry/runtime-product-metrics-0.32.1.md) — `0.32.1`
<!-- wiki-index:archive:end -->
