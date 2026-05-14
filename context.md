# NoemaForge context transfer — 0.29.11 verified full, context/roadmap/TODO sync

This document is the authoritative handoff context for continuing NoemaForge work after the BigBro-BOS post-install recovery cycle.
It consolidates the package audit, the BigBro-BOS operational debugging, the accepted degraded first run,
and the deep-research conclusions that should shape the next Trixie launcher and public MWP direction.

## Machine and current operating facts

- Host: `BigBro-BOS`
- User: `cat`
- OS observed in debugging: Debian GNU/Linux 13 / Trixie
- Kernel observed in the final stable LLM phase: `6.12.85+deb13-amd64`
- GPU: NVIDIA GeForce RTX 3080 Ti, 12 GiB VRAM
- NVIDIA driver observed healthy: `550.163.01`
- Secure Boot: enabled
- Canonical share mount: `/mnt/noemaforge-share`
- Canonical Vault: `/mnt/noemaforge-share/noemaforge-lab/data/Vault`
- Runtime ModelStore: `/var/lib/modelstore`
- Main backend socket: `/run/noemaforge/llm/backends/main.sock`
- Gateway socket: `/run/noemaforge/llm/gateway.sock`
- ToolProxy socket: `/run/noemaforge/toolproxy.sock`

Primary runtime invariant:

```text
runtime_desired_count=1
Only one active noemaforge-llama@*.service is allowed by default.
GPU use must be explicit or policy-gated; it is not the always-on baseline.
```

## What is already working

### GPU / NVIDIA / LLM runtime

The following were confirmed working during the accepted degraded first-run cycle:

- NVIDIA DKMS built and loaded.
- `nvidia-smi` reported the RTX 3080 Ti and active driver stack.
- `noemaforge-llama@main.service` successfully ran `llama-server-cuda`.
- `noemaforge-llm-gateway.service` answered chat completion requests.
- `noemaforge-toolproxy.service` stayed active without fresh SEL permission failures.
- `main.sock`, `gateway.sock` and `toolproxy.sock` were present and listening.
- Backend health check returned `{"status":"ok"}`.
- Gateway answered a trivial prompt with `OK`.

### First run status

A non-zero, operationally meaningful first-run was achieved.

Observed accepted degraded outcome:

```text
total_roles = 58
selected    = 41
na_count    = 17
```

Core roles were staffed with `main`:

- `operator.admin/administrator`
- `system.guard/surgeon`
- `dev.work/solution_architect`
- `writing.story/writer`

These did not all meet the original strict target thresholds, but they did produce viable scorecards and should be treated as `degraded_selected`, not `unstaffed`.

### Canonical model entrypoint rule

ModelStore now must point only to:

- full single-file `.gguf` models, or
- the **head shard** of a split model: `00001-of-N`

Never point runtime symlinks to non-head shards such as `00003-of-00005` or `00005-of-00005`.

## What is still unresolved

### Console boot vs GUI

The system later drifted into console-first boot with `gdm.service` failing to establish a greeter session.
Important characteristics of that state:

- `graphical.target` could still be set as default.
- `gdm.service` existed and could be started.
- `gdm.service` reported repeated greeter/session deaths:
  - `Session never registered`
  - `Child process ... was already dead`
  - `maximum number of X display failures reached`
- `WaylandEnable=false` was already set in `/etc/gdm3/daemon.conf`.
- The failure looked like GDM greeter/session startup failure, not a missing unit file.

This is still unresolved in-package and should be treated as an open Trixie integration issue.

### ToolProxy capability tokens

ToolProxy is alive and answers raw JSON over the UNIX socket, but unauthenticated requests are denied.
The public-friendly capability-token issuance and UX are still unfinished.

### Full evaluation matrix

The accepted degraded first run proves the runtime works, but **full evaluation over the full canonical model list** is still pending.
This must be done on both:

- CPU baseline path
- GPU-accelerated path

### Launcher

The idempotent Trixie launcher is still a design requirement, not a finished implementation.

## Rules learned from the debugging cycle

1. Do not let heavy LLM backends autostart before the machine is stable enough to host them.
2. GPU should be used only for explicit or policy-selected tasks, not as an unconditional always-on default.
3. Firstboot must not consider shard tails as standalone models.
4. Firstboot must not apply/reboot on an all-zero staffing result.
5. If a core role has a viable best model but is below target quality, it should be assigned as `degraded_selected` with a warning, not forced to `N/A`.
6. `noemaforge stop` / `pause` / `reboot-safe` logic must be able to pause NoemaForge runtime so the operator can return to GUI and continue diagnostics.
7. Mount normalization must always converge to `/mnt/noemaforge-share`; desktop automount locations such as `/media/...` are not canonical.
8. Dataset assurance is mandatory: `/opt/noemaforge/datasets/role_eval_cases` must exist before firstboot scoring.
9. The launcher must gather forensics automatically when firstboot or a critical service fails.

## Deep-research documents bundled in this archive

The archive now includes both the earlier bundled research and additional synthesized research notes from the full discussion:

- `docs/research/deep-research-report-2.md` — architecture / public MWP shell direction.
- `docs/research/deep-research-report-3.md` — Evolve / Surgeon / Scary / adapter-first lab path.
- `docs/research/deep-research-report-4.md` — recovery/stability packaging recommendations.
- `docs/research/deep-research-report-5-wiki-llm-comparison.md` — NoemaForge vs Wiki LLM concept comparison.
- `docs/research/deep-research-report-6-hypergraph-and-knowledge-substrate.md` — hypergraph substrate vs wiki/document projection.
- `docs/research/deep-research-report-7-setup-redesign-launcher.md` — single-entry setup/launcher redesign.
- `docs/research/deep-research-report-8-bootstrap-quality-gate.md` — bootstrap quality gate and degraded staffing policy.
- `docs/research/noemaforge_debug_context.txt` — original BigBro-BOS debug context.
- `docs/research/noemaforge_debug_context_v2_2026-05-04.txt` — authoritative updated debug context after the accepted degraded first run.
- `docs/research/DEEP_RESEARCH_INDEX.md` — index of all bundled research notes.

## Immediate next steps

1. Preserve the accepted degraded first-run artifacts.
2. Pause heavy NoemaForge runtime services and regain a usable GUI session.
3. Complete CPU and GPU evaluation across the **full canonical candidate list**.
4. Encode `degraded_selected` and core-role acceptance directly into firstboot/launcher logic.
5. Implement the Trixie launcher with mount normalization, dataset assurance, backend health gate, shard filtering, and automatic forensics.
6. Only after that, re-enable optional manager/modelscan automation in a constrained policy mode.

## Practical operator stance right now

Treat the system as:

```text
NoemaForge runtime healthy enough for controlled manual use.
First run acceptable for P0 as degraded bootstrap.
GUI path not yet reliable enough to be assumed.
Launcher and evaluation automation still need to be built.
```


## 0.31.0 final pre-machine-test context

- Old recovery dispatcher state observed on BigBro-BOS: `gui-rescue` missing, help surface incomplete.
- Added direct Trixie GUI fallback and compatibility wrappers for `gui-rescue`/`gui-status`.
- Added `noemaforge qa code team|run|list|show` for code-dev QA sub-team.
- QA sub-team default: two reviewer models distinct from producer, sequential under single-active-LLM invariant, consensus/unique finding ledger, tester handoff context.
- User test case: `docs/USER_TEST_CASE.md`.


## 0.31.11 live reboot stabilization

- [x] Fix BootDoctor report write regression.
- [x] Fix ToolProxy root preflight and SEL current-day segment permissions.
- [x] Add GUI/Secure Boot/NVIDIA diagnostic command.
- [x] Make GUI mode default to runtime-only and enforce no active LLM backend.
- [x] Fix version reporting from installed `/opt/noemaforge/VERSION`.
- [ ] Complete post-reboot BigBro-BOS validation and archive logs as wiki patch.


## 0.31.11 prod-readiness pass

Current archive has been promoted from `0.31.10` to `0.31.11` after an active-file audit. The canonical rule for all next steps remains: keep version-bearing active files synchronized, but preserve historical changelogs/reports as history.

Completed in this pass:

- Active release metadata/runtime constants/config catalog versions now align on `0.31.11`.
- `noemaforge version-audit --expected 0.31.11` passes with zero active metadata/runtime problems.
- `noemaforge consistency-audit` passes its 25 packaged release checks.
- `./setup.sh --mode vm --dry-run --selftest` passes.
- firstboot GGUF discovery now routes candidates through `model_inventory_normalize.normalize_paths()` so non-head split shards are rejected before role scoring/runtime selection.
- Added regression coverage for firstboot non-head shard filtering.

Still not closed:

- Full monolithic pytest run hangs in this container around pipeline runtime tests after earlier suites; targeted modified/release-gate tests pass. Investigate CI/process isolation before treating the full suite as green.
- Live BigBro-BOS validation remains required for GUI/GDM/NVIDIA reboot behavior and real LLM/gateway/ToolProxy smoke.

## 0.31.12 release-candidate Admin GUI control-plane

The current package is promoted to `0.31.12` as the release-candidate before the intended public `0.31.13` release. The goal is to make the first public flow operational from Admin/GUI, not just documented.

Completed in this pass:

- Active version-bearing package/runtime/config metadata aligned to `0.31.12`.
- Added `noemaforge admin route|message|pipelines` for Admin request classification and concrete pipeline launch.
- Added `noemaforge gui console start` / Admin GUI server with localhost JSON API, keeping the no-implicit-LLM/media/camera invariant.
- Added Dev Team runtime: pipeline launch plus explicit `replace`, `write-file`, and `set-version` code-modification operations; direct writes require `--apply`.
- Added model-evolution runtime: baseline snapshot, mutation plan, scorecard, rollback gate and candidate profile artifacts.
- Added pipeline/team catalog entries for Admin console, model evolution, media generation, image analysis and camera masks.
- Updated wiki, TODO, architecture, changelog, release notes and verification handoff for `0.31.12`.

Public-release interpretation:

- `0.31.12` is the operational release candidate.
- `0.31.13` should be the public release after final polish, target-machine validation, final archive naming/checksum and optional first backend adapter “bow”.


### 0.31.12 final RC alignment note

- GUI direct Dev Team operations were added after the initial RC pass: `/api/dev-team/write-file`, `/api/dev-team/replace`, `/api/dev-team/set-version`, plus `/api/admin/modify-pipeline` for pipeline overlay changes.
- Targeted launch-critical pytest set now passes 15 tests covering Admin, GUI, Dev Team, model evolution, multimodal shard filtering and member-cell flows.

## 0.31.12 final RC package closure

Final `0.31.12` packaging is rebuilt as a complete release-candidate tree before the intended public `0.31.13` release.

Additional closure items:

- `0.31.12` preserves the `0.31.10/0.31.11` multimodal discovery and GGUF/firstboot hardening while adding Admin GUI, Dev Team and model-evolution control-plane surfaces.
- Multimodal Vault scan is now shard-aware: non-head split GGUF shards are excluded from runtime candidate lists and reported as `excluded_non_head_shards`.
- Admin typo greeting `Првиет!` is explicitly recognized and remains inside the Admin GUI flow.
- Verified GUI API flow includes health, greeting, routed music pipeline, model-evolution action and shutdown.
- Targeted launch-critical pytest is now `noemaforge/tests/test_admin_gui_evolution_03112.py` plus `noemaforge/tests/test_multimodal_shards_03112.py`, passing with plugin autoload disabled in this sandbox.

`0.31.13` should now be treated as a public release polish step: target-machine validation plus one visible “бантик” rather than another large architecture expansion.


## 0.31.12 final RC polish

The Admin GUI release candidate now includes the last pre-0.31.13 control-plane polish: typo greeting `Првиет!`, GUI-local ask/start/approve/shutdown flow, Admin pipeline overlay modification, Dev Team direct edit/version surfaces, and measured model-evolution artifacts. Active version-bearing files remain aligned to `0.31.12`; historical docs remain preserved as history.

## 0.31.12 final RC alignment before public 0.31.13

Final `0.31.12` is the release-candidate control-plane build for the intended public `0.31.13`.

Confirmed release posture:

- Admin recognizes `Првиет!` and keeps the operator in the local GUI/API flow.
- Admin code requests create a pipeline run and a Dev Team runtime action.
- Admin music/media requests create a pipeline run and explicit-only multimodal prepare plan.
- Admin model-evolution requests create a pipeline run plus measured evolution artifacts.
- Dev Team can directly patch code or bump project versions only with explicit `--apply`, producing diff/backup metadata.
- The dashboard launcher uses `/api/state` and an operator-writable cache instead of requiring writes into the packaged UI directory.
- `0.31.13` should use a polished Admin GUI guided scenario as the public “бантик”; live heavy media adapters should remain explicit/manual unless one is validated on the target machine.


## 0.31.13.alpha context update

0.31.13.alpha is a pre-alpha stabilization build prepared from the BigBro-BOS 0.31.12 validation feedback and first-start rerun findings.

Key context:

- `first-run` is an audit path; optimal model selection belongs to `first-start`/role tournament.
- 0.31.12 discovery/inventory found real candidates, but stock selection could rank models while backend calls still returned loading/empty responses.
- 0.31.13.alpha adds a warmup gate and zero-credit scoring for failed/empty/loading calls.
- Admin GUI must be chat-first, not raw JSON-first.
- Admin must clarify Dev Team requests before handoff when the project/file path is missing.
- Every created or planned output must be returned as an artifact card.
- Runtime model optimization from chat must be two-step: show candidates first, then apply epoch switch only after confirmation.
- User-facing localization now targets `en`, `ru`, `uk`, `es`, `de`, `pt`, `it`, `zh-CN`, `ja`, and `ko`.

## 0.31.13.alpha context update

This patched pre-alpha closes easy high-impact issues found immediately before BigBro-BOS validation:

- first-start dry-run is now truly non-applying;
- warmup requires READY instead of arbitrary non-empty text;
- failed/loading/empty/no-pass backend calls are excluded from selected candidates;
- normal-mode candidate counting now matches `valid_measured` results;
- composite planning refuses incomplete role pools and filters QA==Developer combinations;
- GUI locale dictionaries are exposed to the browser and applied to the chat-first UI;
- version-audit recognizes `0.31.13.alpha` as a full release string.

## 0.31.13.alpha context update

This patch closes archive-audit gaps before the next BigBro-BOS validation run:
- first-start dry-run is direct selection-only and does not systemd-rehome or soft-headless;
- localized user-information files exist for en, ru, uk, es, de, pt, it, zh-CN, ja, ko;
- YAML mirrors parse cleanly;
- `/api/model-selection/plan` follows the chat/artifact response contract;
- manifest/checksums are regenerated after final files are written.
## 0.31.13.alpha docs/backlog addition — Edge / TinyML / OTA

Tracking ID: `NFG-PROP-0.31.13-edge-ml-pack`.

The Edge/TinyML/OTA proposal is now recorded as a candidate backlog pack, not as a runtime requirement.
It is intentionally excluded from first-start, Admin GUI, Dev Team, model-selection, and localized HOW2START gates.

Future implementation direction:

- Edge signal ingestion through MQTT/serial with source trust labels.
- TinyML/MCU validation through golden vectors, size gates, arena reports, and fallback rules.
- Gateway inference service with manifest-only model loading and `/health`, `/ready`, `/metrics`.
- Rule guard layer before/after ML, with whitebox fallback and drift/anomaly flags.
- Signed model manifests with budget and rollout metadata.
- OTA layer with staged rollout, rollback, and health gates.
- CI model gates storing `release_evidence.json`.

MVP recommendation remains docker-compose + MQTT + gateway inference + manifest + rules + health metrics.


## 0.31.13.alpha consolidated architecture roadmap insert

Tracking ID: `NFG-ARCH-0.31.13-kernel-shell-exchange`.

The consolidated architecture report is recorded as future-version roadmap/Wiki material. It keeps NoemaForge focused on a narrow public MVP kernel:

- Admin, Surgeon, Scary, Evolver/Darwin as base roles;
- optional roles as inactive packs;
- one heavy worker NN today with durable sleep/wake batons;
- NoemaShell Lite as the product shell/operator cockpit;
- RoleFlow/orchestration_graph as the standard handoff graph;
- quarantine-first git_exchange for community contribution;
- HFBridge as metadata-first eval/capability discovery;
- Evolve mutations confined to lab with Scary -> Surgeon -> Admin promotion.

Runtime impact in this package: none. This is a documentation/backlog inclusion only.

Docs: `docs/wiki/architecture/consolidated-mvp-kernel-roadmap-0.31.13.alpha.md`.


## 0.31.13.alpha alpha-prep backlog ingestion

Added three uploaded architecture/source reports into docs/wiki/backlog:

- `docs/source_reports/deep-research-report-6-consolidated-architecture.md`: preserved consolidated MVP kernel / NoemaShell / git_exchange / HFBridge architecture source.
- `docs/source_reports/noemaforge-patch-31-13-multiOS.md`: preserved MultiOS runtime host proposal.
- `docs/source_reports/deep-research-report-7-sense-privacy-honesty-critics-rfc.md`: preserved Sense/Privacy/Honesty/Critics/Pipeline-RFC proposal.

Runtime policy: these are roadmap/wiki/backlog additions only. No new hard dependencies and no changes to first-start/model-selection/Admin GUI runtime behaviour.


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

## 0.31.13.alpha governance / quality / sensing research inclusion

Added source and wiki material from `deep-research-report 8` under NoemaForge naming:

- `docs/source_reports/deep-research-report-8-noemaforge-governance-quality-pack.md`
- `docs/wiki/safety/governance-quality-research-pack-0.31.13.alpha.md`
- `docs/GOVERNANCE_QUALITY_RESEARCH_PACK_0.31.13.alpha.md`

The pack remains backlog-only. It records P0/P1/P2 work for `Concept_Frame`, `Sense_Layer`, `Privacy_Filter`, `Drive_Adapter`, Honesty Protocol, `Slop_Score`, `Critic_Stack`, provenance, `Research_Packet` and `Pipeline_RFC`.


## NFG-ARCH-0.31.13-typed-governance-sense-critics-rfc

The latest research update is included as alpha-prep context. It reinforces NoemaForge's dependency order: Concept_Frame -> Sense/Privacy -> Honesty/Slop -> Critics/Provenance -> Internet_Scout -> Pipeline_RFC. Runtime impact in this build is intentionally none.

## NoemaForge 0.31.13.alpha live-fix context

Patched7 incorporates the BigBro-BOS runtime-selection findings: core systemd units are installed by setup, setup markers are created, legacy share migration is handled, NoemaForge runtime sockets are canonical, `gui_rescue` aliases are action aliases, and first-start keeps partial valid model scores instead of invalidating them after per-model budget exhaustion. Runtime infrastructure failures are reported separately from model quality failures.

## NoemaForge 0.31.13.alpha patched10 update
- Fixed runtime-safety false positive: free-form eval answers mentioning non-head GGUF shards are warning-only; structured runtime paths remain blocking.
- Added canonical path helper for legacy `/mnt/brainos-share` -> `/mnt/noemaforge-share`.
- Added full-composite real launch runbook for `sudo noemaforge first-start --full_composite 0`.

## 0.31.13.alpha live-context update

BigBro-BOS full-composite real launch exposed operator-control issues rather than pure model-selection issues: the local TTY did not provide useful status, GUI recovery was not guaranteed, and interrupt handling needed a first-class abort path. Patched9 adds console status, GUI restore on exit, direct Ctrl+C trapping, and `noemaforge first-start abort`. Installer bind-mount handling for `/mnt/noemaforge-share` is made non-blocking with nofail/automount semantics.


## NoemaForge 0.31.13.alpha alpha

This alpha promotes the stateful GUI shell: persistent Admin conversation history, persona portraits with deterministic fallback avatars, SR/SSR review inbox records, telemetry panels, task governance, inactivity timer, full pipeline dock, epoch/model-selection controls, CPU/GPU device policy staging, and local-first SmartHome backlog architecture.

Important runtime policy: CPU/GPU switching is staged. The selected device policy applies on the next persona/model switch or backend restart; it does not migrate an active model.

Privileged operations such as Vault re-inventory, model-selection continuation and epoch apply are plan/job-first from the GUI. They require explicit operator approval or a terminal sudo command.
