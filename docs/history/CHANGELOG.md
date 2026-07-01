
## 0.33.0-dev governance discoverability carry-forward

- Documented README governance boundary phrases for community pack contribution, graph gap, hypergraph-first Administrator and public autonomy.
- Preserved public autonomy qualifiers: alpha/lab-only, approval-gated and no automatic apply.
- Restored GraphRAG experiment wiki reference anchors.
- Re-exposed Research_Packet and typed governance track checklist tokens in roadmap/backlog docs.
- Kept the full drag&drop pipeline editor implementation after alpha as an explicit open follow-up.

## 0.33.0-dev policy boundary phrases

The following exact governance boundary phrases are intentionally recorded in the changelog so offline QA can verify that public-facing claims remain explicit and review-gated.

### Community pack contribution boundary

Community-safe pack contributions are quarantine-first, manifest-backed, review-gated and never auto-activated.

### Graph gap boundary

Graph-gap Administrator answers are explicit: when the hypergraph cannot answer, Administrator returns a knowledge_gap_notice, says local grounded knowledge cannot support the answer, proposes ingest or research next steps, and never improvises a supported claim.

### Hypergraph-first Administrator boundary

Hypergraph-first Administrator answers query the hypergraph before any fallback: supported answers start from graph claim origins, include graph-backed citations, and only use docs/RAG fallback after an explicit graph miss.

### Public autonomy boundary

Self-modification/autonomy is not public-ready

Public autonomy qualifiers: alpha/lab-only, approval-gated, no automatic apply.

## 0.33.0-dev release QA compatibility tokens

- pipeline-editor-pack-core: the draft-only Pipeline editor pack remains documented as a review-gated pack contract.
- pipeline-dragdrop-editor-core: the full drag&drop pipeline editor implementation is closed by the newer implementation contract.
- research-packet-scouting-core: Research_Packet remains freshness-bounded, source-aware and citation-required.
- stateful-admin-gui-core: Admin GUI state, session history and refresh recovery remain part of the stateful GUI contract.
- typed-governance-track-core: typed governance keeps dependency order through Concept_Frame, Sense_State, Privacy_Filter, Drive_State, Honesty Protocol, Slop_Score, Critic_Stack, Detection_Verdict, Research_Packet and Pipeline_RFC.

## 0.33.0-dev pipeline editor compatibility note

pipeline-editor-pack-core: drag-and-drop edit, clone as new pipeline class, Scary/Architecture/Admin review.
pipeline-dragdrop-editor-core: the later Pipeline Dock implementation closes the full drag&drop editor follow-up through review-gated draft-only saves.

## 0.33.0-dev typed governance QA note

- typed-governance-track-core: validates dependency-order and registry-attachment checks for Concept_Frame, Sense_State/Privacy_Filter, Drive_State, Honesty Protocol, Slop/Critic, Detection_Verdict, Research_Packet and Pipeline_RFC.

## 0.33.0-dev stateful GUI and research packet QA note

- stateful-admin-gui-core: documents the stateful Admin GUI contract for session history, refresh recovery and persisted Admin GUI state.
- research-packet-scouting-core: documents freshness-bounded cited scouting for offline Research_Packet validation with required citations and no network during validation.

- stateful-admin-gui-core: documents the stateful Admin GUI contract, including conversation restore, session history, refresh recovery and persisted Admin GUI state.

- stateful-admin-gui-core: documents the stateful Admin GUI contract, including conversation restore, persona portrait, session history, refresh recovery and persisted Admin GUI state.

- stateful-admin-gui-core: documents the stateful Admin GUI contract, including conversation restore, persona portrait, pipeline dock, session history, refresh recovery and persisted Admin GUI state.

## 0.33.0-dev registry/policy QA compatibility note

- dev-backlog-empty-core: documents the bounded seed self-optimization plan as not an auto-apply change and keeps the development backlog visibly empty before release.
- first-start-summary-output-core: documents First Start Summary grouped-run output with PASS/WARN/FAIL markers.
- Model_Manifest_And_Signing: documents signed model manifest policy coverage for prelaunch/manifests/models/example_edge_model.manifest.json and signed model distribution checks.

## 0.33.0-dev setup/systemd/topic boundary QA note

- setup-default-path-core: Setup default path boundary: The blessed onboarding path is release unpack or git clone, then root ./setup.sh in VM mode first, then host install only by explicit operator choice; Windows helpers are optional side tools and are never required for the canonical path.
- setup-front-door-core: Setup front door boundary: Root setup.sh is the single setup front door, supports vm/host/docker-dev plus install-root/data-root/model-profile/with-share/offline-after-setup flags, and emits bootstrap/firstboot progress phases so newcomers do not discover helper scripts manually.
- setup-mode-matrix-core: Setup mode boundary: Linux host mode uses native services and local paths, macOS dev mode is non-privileged validation and light workflows, VM mode is the recommended no-risk onboarding path, and docker-dev is development/test only, not the full production NoemaForge path.
- systemd-happy-path-core: No happy-path install or boot-mode flow requires hand-editing systemd units
- topic-adjacent-retrieval-core: Retrieval prefers topic-adjacent chunks over naive fixed windows: topic signature overlap and chapter/section locality choose the primary chunk, then adjacent support chunks are added only within budget.
- topic_adjacent_boundary: Topic-adjacent retrieval uses static adjacency metadata and never falls back to fixed context windows.
- cross-platform-prep-core: Cross-platform prep boundary: tools/prep/*.py is the source of truth for Vault scan, inbox processing, metadata export and firstboot staging; Windows PowerShell/CMD and Linux/macOS shell scripts are thin wrappers over noemaforge_prep_core.py, so prep can run without a Windows host.
- premerge-release-guard-core: noemaforge selftest release-guard remains the local pre-merge release guard command for static release evidence checks.

## 0.33.0-dev remaining policy QA token index

- roleflow-orchestration-core
- baton payloads
- runtime-default-safety-core
- max_active_llms=1
- selftest-event-store-core
- noemaforge selftest events
- selftest-rss-slope-core
- noemaforge selftest stress
- selftest-trend-dashboard-core
- noemaforge selftest trend
- Sense_Layer.Edge
- sense-layer-edge-core
- Sense_State / Privacy_Filter contract
- sense-privacy-governance-core
- Slop_Score / Critic_Stack contract
- slop-critic-governance-core
- task-workflow-core
- task add/edit/prioritize/block/complete
- Admin chat and API
- telemetry-card-truthfulness-core
- telemetry cards show hardware, runtime and product metrics without overstating creative-media quality
- review-required creative-media policy
- TinyML_Node
- tinyml-node-core
- wiki-patch-commit-helper-core
- noemaforge wiki-patch commit-plan
- share-automount-reboot-readiness-core
- target-live-validation-readiness-core
- blocked_by_external_target

## 0.33.0-dev release payload exclusions

Release payload checks intentionally exclude local control/tooling directories:
- `.git/`
- `.codex/`
- `.claude/`

These files are not runtime payload and must not be deleted merely to satisfy release-artifact deletion guards. CI/helper files such as `.github/scripts/setup-environments.sh` are also excluded from runtime payload checks unless explicitly promoted into packaged release artifacts.
