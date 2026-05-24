# NoemaForge Wiki Knowledge Base

This wiki is the GitHub-ready prose layer for the NoemaForge `0.32.0.alpha` prelaunch tree. It consolidates architecture, runtime policy, recovery context, evaluation requirements, publication workflows and backlog direction into standalone articles that can be read without opening raw research bundles.

## Entry points

- `architecture/memory-vector-architecture.md` — embeddings, vector DBs, memory layers, routing, and retrieval tradeoffs.
- `architecture/product-kernel-and-shell.md` — stable NoemaForge kernel, shell requirements, role packs, and contribution units.
- `evolve/evolve-lab-roadmap.md` — Admin/Surgeon/Scary/Evolver boundaries and promotion gates.
- `metrics/eval-observability-metrics.md` — quality, runtime, safety, UX, and team metrics.
- `operations/recovery-stability-trixie.md` — Debian Trixie recovery/stability context and operational scripts.
- `prelaunch/prelaunch-tooling.md` — cross-platform prelaunch tool strategy.
- `prelaunch/todo-roadmap-crosswalk.md` — merged TODO/roadmap/context crosswalk.

## Merge Rule

Raw research and discussion material is not kept as active wiki evidence. Useful ideas are converted into full prose pages, tied to canonical TODO or roadmap entries, and then obsolete source material is quarantined under project trash. Wiki upload inputs should therefore be these normalized pages, not source dumps, isolated link lists or temporary reports.


## 0.29.14 additions

This wiki now includes the second merge pass: public launch/marketing package, tool gap analysis, metrics and evaluation research, and an updated prelaunch tooling inventory.

New pages:

- [Public launch and marketing package](public/marketing-launch-package.md)
- [Tool gap matrix and feature import backlog](tools/tool-gap-matrix.md)
- [Evaluation metrics and observability](metrics/eval-observability-metrics-02914.md)
- [Prelaunch tools README](prelaunch/prelaunch-tools-02914.md)
- [Roadmap/TODO merge notes](prelaunch/todo-roadmap-crosswalk-02914.md)
- [Trixie recovery operating rule](operations/trixie-recovery-operating-rule-02914.md)


## 0.31.0 additions

- [Self-improvement test and telemetry loop](architecture/self-improvement-test-telemetry-loop.md)
- [Testbench and regression metrics](metrics/testbench-and-regression-metrics.md)
- [Self-improvement pipelines](pipelines/self-improvement-pipelines.md)
- [Wiki incremental patch pipeline](pipelines/wiki-incremental-patch-pipeline.md)

## 0.31.0 self-improvement telemetry

- [Self-improvement architecture: test cases + telemetry + regression gates](architecture/self-improvement-test-telemetry.md)
- [Self-test resource metrics](metrics/selftest-resource-metrics.md)
- [Wiki incremental patch pipeline](pipelines/wiki-incremental-patch-pipeline.md)


## 0.31.0 additions

- GUI recovery / TTY Trixie fallback: `docs/GUI_RECOVERY_TTY_TRIXIE_0.31.0.md`
- Code-dev QA sub-team: `docs/CODE_DEV_QA_SUBTEAM_0.31.0.md`
- User acceptance test case: `docs/USER_TEST_CASE_0.31.0.md`
- Wiki pipeline: `docs/wiki/pipelines/code-dev-qa-subteam.md`



## 0.31.10 live reboot stabilization

- [x] Fix BootDoctor report write regression.
- [x] Fix ToolProxy root preflight and SEL current-day segment permissions.
- [x] Add GUI/Secure Boot/NVIDIA diagnostic command.
- [x] Make GUI mode default to runtime-only and enforce no active LLM backend.
- [x] Fix version reporting from installed `/opt/noemaforge/VERSION`.
- [ ] Complete post-reboot legacy live-validation host validation and archive logs as wiki patch.

## 0.31.12 additions

- [Admin Console and Admin Routing](gui/admin-console-and-admin-routing-0.31.12.md)
- [Model Evolution Control Plane](evolution/model-evolution-control-plane-0.31.12.md)
- [Multimodal Vault Readiness 0.31.12](multimodal/multimodal-vault-readiness-0.31.12.md)
- [Persona Portraits and Dashboard 0.31.12](gui/persona-portraits-and-dashboard-0.31.12.md)

## Future / experimental backlog packs

- [Edge / TinyML / OTA roadmap (0.31.13.alpha-patched1)](edge/edge-tinyml-ota-roadmap-0.31.13.alpha-patched1.md) — candidate backlog pack for edge inference, signed manifests, rules and OTA.

## 0.31.13.alpha-patched1 additions

- Architecture: `docs/wiki/architecture/consolidated-mvp-kernel-roadmap-0.31.13.alpha-patched1.md` — protected MVP kernel, NoemaShell Lite, RoleFlow, git_exchange, HFBridge, Evolve boundaries.
- Edge: `docs/wiki/edge/edge-tinyml-ota-roadmap-0.31.13.alpha-patched1.md` — candidate Edge/TinyML/OTA backlog pack.


## Alpha preparation backlog added in 0.31.13.alpha-patched1

- MultiOS runtime host roadmap: `docs/wiki/multios/multios-runtime-host-roadmap-0.31.13.alpha-patched1.md`.
- Sense/Privacy/Honesty/Critics/Pipeline-RFC roadmap: `docs/wiki/safety/sense-privacy-honesty-critics-rfc-roadmap-0.31.13.alpha-patched1.md`.
- These research themes are integrated into wiki prose and project context; raw source reports are not active release evidence.

These are backlog/wiki additions only and do not add runtime hard dependencies.
- Architecture: `docs/wiki/architecture/typed-control-plane-sense-critics-rfc-0.31.13.alpha-patched1.md` — typed governance, Sense/Privacy, Honesty, critics and Pipeline_RFC roadmap.


## Alpha additions
- gui/stateful-gui-shell-0.31.13.alpha-patched1.md
- telemetry/runtime-product-metrics-0.31.13.alpha-patched1.md
- pipelines/pipeline-dock-editor-0.31.13.alpha-patched1.md
- smarthome/local-first-smart-home-control-0.31.13.alpha-patched1.md
- tasks/inactivity-and-task-governance-0.31.13.alpha-patched1.md
- personas/persona-portrait-fallback-0.31.13.alpha-patched1.md

