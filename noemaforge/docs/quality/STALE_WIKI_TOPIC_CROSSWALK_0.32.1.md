# Stale Wiki Topic Crosswalk 0.32.1

This machine-generated crosswalk maps versioned wiki pages to canonical topic destinations before any archival move. It is intentionally conservative: every row starts as `needs-review`, the default action is `merge-unique-prose`, and the active cleanup TODO remains open until prose integration and project-trash quarantine are complete.

```json
{
  "kind": "StaleWikiTopicCrosswalk",
  "contract": "stale-wiki-topic-crosswalk-core",
  "source_inventory": "stale-wiki-version-audit-core",
  "stale_pages": 40,
  "canonical_topics": 28,
  "duplicate_topic_groups": 12,
  "completion_blocker": "topic_crosswalk_review_and_prose_merge_required"
}
```

| source | canonical_topic | action | status |
| --- | --- | --- | --- |
| `noemaforge/docs/wiki/architecture/consolidated-mvp-kernel-roadmap-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/architecture/consolidated-mvp-kernel-roadmap.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/architecture/typed-control-plane-sense-critics-rfc-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/architecture/typed-control-plane-sense-critics-rfc.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/edge/edge-tinyml-ota-roadmap-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/edge/edge-tinyml-ota-roadmap.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/evolution/model-evolution-control-plane-0.31.12.md` | `noemaforge/docs/wiki/evolution/model-evolution-control-plane.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/evolution/model-evolution-control-plane-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/evolution/model-evolution-control-plane.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/evolution/model-evolution-control-plane-0.31.13.alpha.md` | `noemaforge/docs/wiki/evolution/model-evolution-control-plane.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/first-start/emergency-gui-recovery-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/first-start/emergency-gui-recovery.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/first-start/firststart-watchdog-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/first-start/firststart-watchdog.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/first-start/full-composite-real-launch-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/first-start/full-composite-real-launch.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/first-start/full-composite-real-launch-0.31.13.alpha.md` | `noemaforge/docs/wiki/first-start/full-composite-real-launch.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/first-start/live-runtime-selection-fixes-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/first-start/live-runtime-selection-fixes.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/first-start/model-selection-modes-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/first-start/model-selection-modes.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/first-start/model-selection-modes-0.31.13.alpha.md` | `noemaforge/docs/wiki/first-start/model-selection-modes.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/first-start/tty-status-gui-recovery-interrupt-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/first-start/tty-status-gui-recovery-interrupt.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/gui/admin-chat-locales-and-artifacts-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/gui/admin-chat-locales-and-artifacts.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/gui/admin-console-and-admin-routing-0.31.12.md` | `noemaforge/docs/wiki/gui/admin-console-and-admin-routing.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/gui/admin-console-and-admin-routing-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/gui/admin-console-and-admin-routing.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/gui/epoch-visualization-depth-and-usecases-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/gui/epoch-visualization-depth-and-usecases.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/gui/persona-portraits-and-dashboard-0.31.10.md` | `noemaforge/docs/wiki/gui/persona-portraits-and-dashboard.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/gui/persona-portraits-and-dashboard-0.31.11.md` | `noemaforge/docs/wiki/gui/persona-portraits-and-dashboard.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/gui/persona-portraits-and-dashboard-0.31.12.md` | `noemaforge/docs/wiki/gui/persona-portraits-and-dashboard.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/gui/persona-portraits-and-dashboard-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/gui/persona-portraits-and-dashboard.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/gui/stateful-admin-gui-shell-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/gui/stateful-admin-gui-shell.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/gui/stateful-gui-shell-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/gui/stateful-gui-shell.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/multimodal/multimodal-vault-readiness-0.31.10.md` | `noemaforge/docs/wiki/multimodal/multimodal-vault-readiness.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/multimodal/multimodal-vault-readiness-0.31.11.md` | `noemaforge/docs/wiki/multimodal/multimodal-vault-readiness.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/multimodal/multimodal-vault-readiness-0.31.12.md` | `noemaforge/docs/wiki/multimodal/multimodal-vault-readiness.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/multimodal/multimodal-vault-readiness-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/multimodal/multimodal-vault-readiness.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/multimodal/multimodal-vault-readiness-0.31.13.alpha.md` | `noemaforge/docs/wiki/multimodal/multimodal-vault-readiness.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/multios/multios-runtime-host-roadmap-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/multios/multios-runtime-host-roadmap.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/personas/persona-portrait-fallback-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/personas/persona-portrait-fallback.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/pipelines/pipeline-dock-editor-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/pipelines/pipeline-dock-editor.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/release/code-header-and-signature-audit-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/release/code-header-and-signature-audit.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/release/manifest-completeness-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/release/manifest-completeness.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/safety/sense-privacy-honesty-critics-rfc-roadmap-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/safety/sense-privacy-honesty-critics-rfc-roadmap.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/smarthome/local-first-smart-home-control-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/smarthome/local-first-smart-home-control.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/tasks/inactivity-and-task-governance-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/tasks/inactivity-and-task-governance.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/tasks/task-governance-and-idle-policy-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/tasks/task-governance-and-idle-policy.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/telemetry/metrics-model-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/telemetry/metrics-model.md` | merge-unique-prose | needs-review |
| `noemaforge/docs/wiki/telemetry/runtime-product-metrics-0.31.13.alpha-patched1.md` | `noemaforge/docs/wiki/telemetry/runtime-product-metrics.md` | merge-unique-prose | needs-review |
