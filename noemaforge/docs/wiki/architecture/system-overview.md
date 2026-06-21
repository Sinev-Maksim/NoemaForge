# System overview (current)

NoemaForge is a local-first AI operating environment: it runs language models,
personas, pipelines and an operator GUI entirely on the user's machine, with
privacy-preserving defaults and explicit, audited paths for anything heavy or
privileged. This page is the maintained entry point into the architecture; it
reflects the 0.33.x line. Historical design snapshots live in the archive
section of the [wiki hub](../WIKI.md).

## Runtime services

The installed system is a small set of systemd services around unix sockets —
no TCP listeners by default:

| Service | Role |
|---|---|
| `noemaforge-llama@<backend>` | llama-server model backend on `/run/noemaforge/llm/backends/<backend>.sock` |
| `noemaforge-llm-gateway` | LLM gateway on `/run/noemaforge/llm/gateway.sock`; single entry point for chat |
| `noemaforge-toolproxy` | Tool execution proxy: deny-by-default policy, capability tokens, bounded exec allowlist |
| `noemaforge-memsentinel` | Memory sentinel housekeeping |
| `noemaforge-modelscan` (timer) | Periodic model inventory scan |
| `noemaforge-llm-backends-manager` (timer) | Plan-only backend drift report; apply is operator-gated |

Core invariants:

- **One active heavy worker.** `max_active_llms=1`; role switches behave like
  durable sleep/wake transactions.
- **Display safety.** First-start and other heavy GPU work never stop the
  desktop session by default; stopping a display manager requires an explicit
  operator opt-in flag.
- **Plan-first privilege.** GUI buttons and timers produce plan/dry-run
  artifacts and audited apply requests; real privileged work is an explicit
  operator action.

## Model selection and epochs

First-start (`sudo noemaforge first-start --fast|--normal|--full|--full_composite N`)
runs a warmup-gated role tournament over the model Vault, writes candidate and
decision artifacts, and applies an **epoch** — an immutable, hash-stable record
of which models staff which roles. Staffing can be `degraded_selected`
(mandatory roles staffed, some below target thresholds) — a warning state, not
a failure. The 2026-06-10 target-host UAT applied epoch `00005` in
`full_composite` mode with a clean runtime-safety verdict.

## Roles and governance

Four default roles ship active: **Admin** (rights owner, final approver),
**Surgeon** (framing, baselines, promotion dossiers), **Scary** (safety gates
and veto), **Evolver/Darwin** (lab-only mutation executor). Optional roles
arrive as inactive RolePacks. Every self-development or pipeline mutation goes
through the typed governance chain
(`Concept_Frame → … → Pipeline_RFC → dry-run → eval evidence → rollback plan →
explicit approval`); nothing mutates production weights automatically.

## Operator surfaces

- **Admin GUI** — localhost dashboard (`noemaforge dashboard start`, default
  `http://127.0.0.1:8765/`); chat-first console with persona portraits,
  pipeline dock, telemetry cards, job panel, and (since 0.33.0) inline artifact
  cards, pipeline progress panel, glossary answers, repeat-launch guard,
  persona selector with in-chat switch, iteration-depth notice, and SVG pipeline
  diagrams. Full status and shipped feature list:
  [Admin GUI current state](../gui/admin-gui-current-state.md);
  pipeline dashboard details:
  [Pipeline dashboard (0.33.0)](../gui/pipeline-dashboard-0.33.0.md).
- **`noema` CLI** — the friendly front door (start / doctor / release /
  upgrade / policy / catalog): [noema CLI](../operations/noema-cli.md).
- **`noemaforge` CLI** — the full control plane (first-start, smoke, selftest,
  pipeline, model-selection, boot-mode, recovery helpers).

## Quality and evidence

Everything observable is artifact-driven: selftest reports, pipeline run
directories, epoch records, release manifests with SHA256 evidence, and the
artifact-driven acceptance suite —
[Acceptance testing (AAT)](../qa/acceptance-testing-aat.md) and
[Release engineering](../release/release-engineering.md) describe the gates.

## Where to go next

- [Desktop app shell decision](desktop-app-shell.md) — how the GUI becomes a
  windowed app without heavyweight dependencies.
- [Product kernel and shell](product-kernel-and-shell.md) — kernel/shell
  boundaries and contribution units (RolePack, RoleFlow, EvalPack…).
- [Memory & vector architecture](memory-vector-architecture.md) — memory
  layers and retrieval design.
- First-start deep dives: the `first-start/` category in the hub archive.
