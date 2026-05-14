# NoemaForge 0.31.13.alpha TODO

## Current alpha validation follow-up

- [ ] Validate stateful Admin GUI after installation: conversation restore, persona portrait, task queue, job panel, telemetry and pipeline dock.
- [ ] Verify `Continue model selection` uses job/idempotency state and does not duplicate active selection work after page refresh.
- [ ] Verify `Re-inventory Vault` returns a privileged job/fallback command instead of a silent failure.
- [ ] Verify Admin smalltalk uses the conversational path and does not launch `public_mwp`.
- [ ] Verify Model Selection and Model Evolution routing are visually and semantically distinct.
- [ ] Verify first-start summary output is grouped by run and uses PASS/WARN/FAIL markers.
- [ ] Verify CPU/GPU staged policy applies only on next persona/model switch or backend restart.
- [ ] Verify telemetry cards show hardware, runtime and product metrics without overstating creative-media quality.
- [ ] Verify task add/edit/prioritize/block/complete through Admin chat and API.
- [ ] Verify Dev backlog empty policy creates a bounded seed self-optimization plan, not an auto-apply change.

## Roadmap packs kept as non-hard dependencies

- [ ] Smart Home local-first control pack: plugs, switches, vacuums, cameras, sensors, local server, value your privacy.
- [ ] Edge/TinyML/OTA pack: MQTT/serial, TinyML validation, gateway inference, rules, manifest signing and OTA rollback.
- [ ] MultiOS host/control pack: Linux reference runtime with future Windows/macOS host-control paths.
- [ ] Pipeline editor pack: drag-and-drop edit, clone as new pipeline class, Scary/Architecture/Admin review.
- [ ] Git exchange pack: quarantine-first RolePack, RoleFlow, EvalPack and KnowledgeGraphPack import/export.

---


## NFG-ARCH-0.31.13-kernel-shell-exchange — future consolidated MVP kernel / shell / exchange roadmap

Status: candidate architecture backlog; documentation only; no hard dependency for `0.31.13.alpha`.

- [ ] Keep base install focused on four default roles: Admin, Surgeon, Scary, Evolver/Darwin.
- [ ] Ship optional roles as inactive RolePacks instead of active core roles.
- [ ] Implement `ActiveNNManager` with one-heavy-worker invariant and durable sleep/wake batons.
- [ ] Treat Admin and Scary as lightweight always-present supervisors, not heavy resident workers.
- [ ] Formalize `RoleFlow` / `orchestration_graph` schema for role switching, branching, guards, approvals, rollback edges, and baton payloads.
- [ ] Make NoemaShell Lite the primary operator shell: active worker, approvals, artifacts, resource budgets, safe mode, recovery.
- [ ] Add quarantine-first `git_exchange` for RolePack, RoleFlow, EvalPack, KnowledgeGraphPack, ArtifactPack, and lab-only ModelDeltaPack.
- [ ] Keep HFBridge metadata-first/read-mostly for MVP; never auto-import arbitrary weights or data into runtime.
- [ ] Preserve Evolve boundary: mutation only in lab; promotion only through Scary -> Surgeon -> Admin.
- [ ] Build public distributions from an allowlist and keep optional HF/community/history/quarantine material outside core seed.

Docs: `docs/wiki/architecture/consolidated-mvp-kernel-roadmap-0.31.13.alpha.md`.



## NFG-PROP-0.31.13-edge-ml-pack — future Edge/TinyML/OTA backlog

Status: candidate backlog pack; experimental only; no hard dependency for `0.31.13.alpha`.

- [ ] Add Sense_Layer.Edge for MQTT/serial/metrics ingestion.
- [ ] Add TinyML_Node package for MCU inference validation.
- [ ] Add Gateway_Inference_Service with model manifest loading.
- [ ] Add Edge_Rules_Engine with whitebox fallback.
- [ ] Add signed Model Manifest contract.
- [ ] Add OTA_Update_Layer with rollback and health gates.
- [ ] Add CI_Model_Gates: latency, memory, golden replay, signature.
- [ ] Keep KubeEdge as post-MVP orchestration target.
- [ ] Keep eKuiper as preferred local stream/rule engine.
- [ ] Keep Mender/RAUC as OTA reference implementations.

Docs: `docs/wiki/edge/edge-tinyml-ota-roadmap-0.31.13.alpha.md`.
## 0.31.13.alpha follow-up

- Run BigBro-BOS first-start candidate review on real Vault/ModelStore.
- Confirm dry-run does not rehome into systemd and does not change headless state.
- Confirm localized docs are sufficient for public HOW2START handoff.


## NFG-PROP-0.31.13-multiOS-runtime-pack
- [ ] Add runtime abstraction layer: OS probe, hardware probe, registry, selector and connectors.
- [ ] Preserve Linux as reference runtime and current systemd launch behaviour.
- [ ] Add optional Windows host/control launcher path.
- [ ] Add optional macOS host/control launcher path.
- [ ] Add remote HTTP runtime connector and runtime health report.
- [ ] Add `configs/noemaforge.runtime.yaml` once implementation starts.
- [ ] Add smoke tests for Linux, Windows and macOS host detection.
- [ ] Keep all MultiOS work optional until alpha runtime gates pass.

## NFG-PROP-0.31.13-sense-quality-governance-pack
- [ ] Add `Concept_Frame` schema for Admin/Architect control-plane decisions.
- [ ] Add policy gates for dangerous role actions.
- [ ] Add coarse Sense_Layer host telemetry with privacy-by-default redaction.
- [ ] Add bounded Drive_Adapter signals: pressure, fatigue, urgency, curiosity.
- [ ] Add Honesty Protocol: Unknown, Need-Research and traceable Error_Attribution.
- [ ] Add Slop_Score and Critic_Stack as advisory quality gates.
- [ ] Add provenance/watermark hooks and aggregated Detection_Verdict.
- [ ] Add Research_Packet for freshness-bounded cited internet scouting.
- [ ] Add Pipeline_RFC for any self-development/pipeline mutation.


## 0.31.13.alpha first-start watchdog patch

`0.31.13.alpha` includes `NFG-FIX-0.31.13-firststart-watchdog`, based on the BigBro-BOS hang diagnostic bundle. It adds per-model and total watchdogs, streaming tournament progress artifacts, backend cleanup, fresh firstboot status writes, and a default safety-name filter for unverified/uncensored/aggressive models.

Recommended bounded candidate review:

```bash
sudo noemaforge first-start --normal --dry-run --show-candidates --per-model-timeout 180 --total-timeout 1200
```

Progress while running:

```bash
sudo jq . /var/lib/noemaforge/bootstrap/role-tournament-progress.json
sudo tail -n 50 /var/lib/noemaforge/bootstrap/role-tournament-progress.jsonl
sudo jq . /var/lib/noemaforge/bootstrap/model-run-records.json
```


## 0.31.13.alpha follow-up

- [ ] Validate NoemaForge clean install on BigBro-BOS with `/mnt/noemaforge-share`.
- [ ] Confirm no failed-runtime model remains in `role-candidate-map.filtered.json`.
- [ ] Confirm previous installation backup/migration context is not active runtime.

## NFG-ARCH-0.31.13-noemaforge-governance-quality-pack
- [ ] Add `Concept_Frame` schema for Admin/Architect decisions.
- [ ] Add rule/policy gates for dangerous role actions.
- [ ] Add coarse `Sense_Layer` host telemetry with privacy-by-default redaction.
- [ ] Add `Privacy_Filter` before persistence/export.
- [ ] Add bounded `Drive_Adapter` signals: pressure, fatigue, urgency, curiosity.
- [ ] Add Honesty Protocol templates for unknown/error/need-research states.
- [ ] Add `Slop_Score` and `Critic_Stack` as advisory quality layers.
- [ ] Add provenance/watermark verifier hooks as optional P1 integrations.
- [ ] Add `Research_Packet` schema for freshness/source-bounded scouting.
- [ ] Add `Pipeline_RFC` as the only path for self-development/pipeline mutation.


## NFG-ARCH-0.31.13-typed-governance-sense-critics-rfc
- [ ] Add `Concept_Frame` schema for Admin/Architect task framing.
- [ ] Add `Sense_State` + `Privacy_Filter` contracts before persistence/export.
- [ ] Add bounded `Drive_State` adapter for pressure/fatigue/urgency/curiosity.
- [ ] Add Honesty Protocol templates: Unknown, Need-Research, Error_Attribution.
- [ ] Add `Slop_Score`, `Critic_Stack`, `Detection_Verdict` as layered advisory quality gates.
- [ ] Add `Research_Packet` for source-allowlisted/freshness-bounded Internet scouting.
- [ ] Require `Pipeline_RFC` + dry-run + eval + rollback + explicit approval for pipeline mutation.

## NoemaForge 0.31.13.alpha live-fix context

Patched7 incorporates the BigBro-BOS runtime-selection findings: core systemd units are installed by setup, setup markers are created, legacy share migration is handled, NoemaForge runtime sockets are canonical, `gui_rescue` aliases are action aliases, and first-start keeps partial valid model scores instead of invalidating them after per-model budget exhaustion. Runtime infrastructure failures are reported separately from model quality failures.

## NoemaForge 0.31.13.alpha patched10 update
- Fixed runtime-safety false positive: free-form eval answers mentioning non-head GGUF shards are warning-only; structured runtime paths remain blocking.
- Added canonical path helper for legacy `/mnt/brainos-share` -> `/mnt/noemaforge-share`.
- Added full-composite real launch runbook for `sudo noemaforge first-start --full_composite 0`.

## 0.31.13.alpha follow-up

- [x] Emit first-start status to TTY/console during long full-composite runs.
- [x] Restore Debian GUI target after first-start completion/error.
- [x] Add Ctrl+C/direct interrupt and `first-start abort` recovery path.
- [x] Make NoemaForge share bind mount nofail/automount to avoid emergency boot mode.
- [ ] Validate full-composite real run on BigBro-BOS after patched10 install.

## patched10 follow-up
- [ ] Validate full-composite real run with SSH available.
- [ ] Confirm `/run/nologin` is cleared after recovery on BigBro-BOS.
- [ ] Confirm share automount lines do not re-enter emergency mode after reboot.

## 0.31.13.alpha follow-up

- [ ] Convert GUI epoch apply request into privileged, polkit-mediated local action after safety review.
- [ ] Add live runtime observer cards for gateway/backend smoke affirmation.
- [ ] Add LLM-backed conversational Admin path for smalltalk while preserving deterministic control-plane routing.
- [ ] Extend bounded-improvement depth to real multi-step Dev Team loops with checkpoint/stop handling.


## NOEMAFORGE-ALPHA-GUI-STATEFUL-SHELL (0.31.13.alpha)
- [x] Add backend-owned conversation history for GUI refresh recovery.
- [x] Route backend messages to SR/SSR review inbox records.
- [x] Add persona portrait static route and deterministic per-person fallback avatar.
- [x] Add hardware/runtime/product telemetry dashboard surfaces.
- [x] Add CPU/GPU runtime device-policy staging; applies on next persona/model switch.
- [x] Add task queue surfaces with create/update/prioritize-ready Admin contracts.
- [x] Add inactivity timer surface and manual_only/idle policy contract.
- [x] Add full pipeline catalog/dock with media/video/mask classes visible.
- [x] Add left-click pipeline start/explain flow and right-click diagram/stats menu.
- [x] Add + New Pipeline draft-only architecture path.
- [x] Add continue model-selection job/idempotency planning and Vault re-inventory privileged fallback.
- [ ] Add full drag&drop pipeline editor implementation after alpha.
- [ ] Add polkit/root job-runner for approved privileged GUI jobs after alpha.
- [ ] Add streaming job progress SSE/WebSocket after alpha.

## NOEMAFORGE-PROP-0.31.13-smart-home-local-control-pack
- [ ] Add local-first SmartHome pack: smart plugs, switches, vacuums, cameras, sensors.
- [ ] Keep home telemetry on local NoemaForge server by default: value your privacy.
- [ ] Add local MQTT/Home Assistant/Zigbee/Z-Wave/Matter adapter surfaces.
- [ ] Add no-hidden-camera/no-hidden-microphone policy and visible privacy state.
- [ ] Add room graph, device registry, automation rules, emergency pause and SR/SSR review.
