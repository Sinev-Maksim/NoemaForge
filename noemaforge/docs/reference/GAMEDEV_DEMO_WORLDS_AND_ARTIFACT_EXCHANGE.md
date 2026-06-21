<!--
=== NoemaForge File Header ===
File: noemaforge/docs/reference/GAMEDEV_DEMO_WORLDS_AND_ARTIFACT_EXCHANGE.md
Zone: docs/reference
Version: 0.33.0
Created: 2026-06-21
Modified: 2026-06-21
Purpose: Design reference for two next-minor roadmap goals — (A) GameDev-ready: the NoemaForge
  Simulation Framework (NSF) + community-built "Demo Worlds" (Arcology Governance Simulator as
  Demo World #1), and (B) artifact exchange (GitHub-first now, decentralized P2P next), with a
  current-vs-vision capability mapping.
Inputs: Owner design session 2026-06-21 (GameDev tech-demo concept + artifact-exchange direction).
Outputs: Roadmap formalization; the tracked checklist lives in noemaforge/docs/TODO.md.
Side effects: None (documentation only).
Tests: docs hygiene.
Notes: The demo world is a showcase domain for NoemaForge, not a game product. Provisional target
  minors: 0.34 (A), 0.35 (B). English-only.
=== End NoemaForge File Header ===
-->

# GameDev-Ready Demo Worlds + Artifact Exchange

Two next-minor roadmap goals. Tracked checklist: the "Version milestones" section of
[`../TODO.md`](../TODO.md). Provisional targets: **0.34** (Goal A) and **0.35** (Goal B).

These are deeply linked: the community-built demo world *runs on* artifact exchange. Goal B's
GitHub-first phase is therefore a prerequisite slice for Goal A's community workflow.

---

## Goal A — GameDev-ready: NoemaForge Simulation Framework (NSF) + Demo Worlds

**Positioning (important):** *"Open-source platform for building impossible games through
community contributions and AI-assisted development."* It is **not** a Warhammer-40K fan game,
**not** a city builder, and **not** an "LLM game." The demo world is a **vertical slice** that
exercises most of the NoemaForge architecture — a showcase domain, not the product.

### Demo World #1 — Arcology Governance Simulator

- **Player** = the founding digital consciousness of a megacity (machine-spirit / founder AI /
  city-core intelligence) that persists for millennia inside the governing infrastructure.
- **Core loop:** the player does **not** build directly. They shape the world through laws,
  taxes, subsidies, privileges, religious campaigns, propaganda, repression and corruption; the
  world (factions, POP groups) reacts on its own.
- **Systems:** planet parameters (climate, radiation, resources, remoteness, external threats);
  megacity tiers (Spire → Upper → Mid → Lower → Undercity → Deep Undercity), each with its own
  economy/population/factions/threats; **POP groups** (aggregated, not individual NPCs: workers,
  engineers, nobility, clergy, security, criminal orgs, mutant population); factions (influence,
  wealth, loyalty, military, goals); **indirect construction** (the player sets conditions —
  factions build); **megaprojects** (the only direct intervention; decades + huge cost);
  **bureaucracy chain** (AI Core → Administrators → Governors → Officials → Executors, each a
  point for delay/sabotage/corruption/distortion); **corruption + a kompromat ledger** (every
  illegal act recorded — Incident/Date/Actors/Evidence/ExposureProbability — may surface decades
  later); **Memory Integrity** (the machine-spirit loses data, gains false memories, blind
  zones); **Entropy** (all systems decay); **hidden threats** (cults, undergrounds, mutant
  communities, techno-heresy — only symptoms are visible); **inspections**; and **logistics**
  (transport/energy/water/food/comms — damage cascades into crises).

### Everything is an artifact

`Faction.yaml`, `Building.yaml`, `District.yaml`, `Event.yaml`, `Policy.yaml`, `Planet.yaml`,
`Lore.md`, `Research.yaml`, `Incident.yaml`, `Quest.yaml`. This is a direct continuation of the
existing NoemaForge artifact model (Intake → Draft → Review → Integration → Vault).

### Community workflow + emergent loop

```
User creates artifact -> Agents review -> Agents suggest improvements
  -> Integration -> Simulation -> Consequences
```

Emergent gameplay loop (artifacts feed the sim, the sim emits new artifacts):

```
Player action -> Policy artifact -> Simulation -> Incident artifact
  -> History artifact -> new Policies
```

### Simulation-domain agent roles

Architect, Economist, Lore Keeper, Balance Analyst, QA Reviewer, Integrator, Historian — new
*roles*, not a new pipeline (they slot into the existing agent-orchestration + review model, and
into the [`LOOP_AWARE_ROLE_RUNTIME_AND_EVOLVER.md`](LOOP_AWARE_ROLE_RUNTIME_AND_EVOLVER.md) role
registry).

### New architecture tier — NoemaForge Simulation Framework (NSF)

A new module alongside Knowledge / Agents / Artifacts / Workflows, owning time progression,
resource flow, faction behaviour, events, entropy, logistics and politics. **The engine is not
LLM-in-the-loop:** classical game AI (GOAP / Utility AI / Behaviour Trees) drives the critical
loop; LLMs are used only for text, chronicles, lore, reports and explanations. Suggested stack
(provisional): Rust simulation core, UE5 UI (Nanite/Lumen/Mass Entity), YAML+Markdown content,
SQLite (local) / PostgreSQL (server).

New NSF modules and their NoemaForge analogues:

| NSF module | Does | NoemaForge analogue |
|---|---|---|
| Simulation Engine | time/resources/factions/events | new tier |
| Entropy Engine | infrastructure decay, knowledge loss, corruption growth | same principle as BrainOS knowledge-degradation |
| Historian Agent | auto-chronicle per tick (`History: {year, summary, key_events}`) | agent role over the event log |
| Memory Integrity | data loss, false memories, blind zones | Vault corruption / context degradation |
| Automated Balance Sandbox | "run 100 years" before merge; check economy/logistics/balance | CI/CD for the world |
| World Regression Testing | scenario / balance / lore / economic tests per release | the AAT/UAT model applied to the world |

### NoemaForge-native leverage (strong, under-used by the source doc)

- **Epoch system** as simulation snapshots / years (`Epoch 00001` ≈ `Year 1200`).
- **Multi-LLM governance:** Architect→GPT, Economist→Claude, Historian→Gemini, then Admin
  arbitration — stronger than uniform agents.
- **Artifact lineage / provenance:** "why does this faction exist?" → created-by/reviewed-by/
  merged-in-epoch = *git for the world*.
- **Audit trail:** who introduced the corruption mechanic, who changed the economy.

### Alignment with NoemaForge (owner estimate)

~80–90% conceptual fit, ~40–50% already implemented. Artifact architecture ~95%, agent pipeline
~90%, artifact-as-the-unit-of-work ~100%, community workflow ~100%, knowledge vault ~95%.

### Scaling

One NoemaForge core, many demo worlds: #1 Arcology Governance, #2 Space Colony, #3 Political
Party, #4 Open Civilization. Position as **"NoemaForge Demo World #N"**, not one game.

---

## Goal B — Artifact exchange (GitHub-first → decentralized P2P)

The unit of exchange is the **artifact** (the same YAML/Markdown artifacts as Goal A, and as
articles/packs elsewhere). Goal B builds the contract for submitting, reviewing, validating and
distributing artifacts between contributors and worlds.

### Mapping: current / in-progress vs the vision

| Capability | NoemaForge today (or planned in TODO) | For artifact exchange |
|---|---|---|
| Artifact model | Intake → Draft → Review → Integration → Vault; versioning | the exchange payload |
| Agent review | review pipelines, QA/Reviewer/Integrator roles | the review gate |
| Provenance / lineage | artifact lineage, audit trail, epoch versioning | trust + "why does this exist?" |
| Quarantine import | marketplace import policy: inspect → quarantine → scan → Pipeline_RFC → epoch (TODO) | safe inbound |
| Export / proposal | §B tokenless **signed proposal bundle** (patch + provenance) + GitHub-API PR path (TODO) | safe outbound |
| Signed manifests | release-manifest schema + `noema release verify` | bundle integrity |

So **GitHub PR-based content creation already IS artifact-exchange v1**: a contributor creates
`Faction.yaml` → PR → agent review → balance-sandbox test → merge → world update. The gap is
formalizing it as a first-class contract and then removing the central GitHub dependency.

### Phase 1 — GitHub as the substrate (0.35 target)

- Formalize the artifact-exchange contract over GitHub: PR-based submission, mandatory agent
  review gates, the Automated Balance Sandbox as a merge gate ("run 100 years" / scenario +
  balance + lore + economic regression), signed-manifest provenance on every accepted artifact,
  and the inspect → quarantine → scan → Pipeline_RFC → epoch import/export policy.
- Reuse the existing §B path (GitHub-API PR when a token is present; **tokenless signed proposal
  bundle** when not) so a contributor without a GitHub account can still propose.

### Phase 2 — decentralized P2P (post-0.35 plan)

- Peer-to-peer artifact exchange with **no central GitHub**: the signed, portable artifact
  bundle (patch + provenance + signed manifest) is the unit; relay / DHT distribution; the
  tokenless proposal bundle becomes the wire format; capability-scoped trust between peers; and
  epoch-bound integration so every imported artifact lands in a verifiable epoch.
- Builds directly on the existing signed-manifest + tokenless-proposal + quarantine model — the
  decentralized exchange is the same contract with a different transport.

---

## Why one core, not separate projects

Both goals are showcases of the same NoemaForge core (Knowledge Vault · Artifact Registry · Agent
Orchestration · Review Pipelines · Multi-LLM Governance · Epoch System · Provenance · Workflow
Engine · — and now NSF + Artifact Exchange). The demo worlds prove the platform far better than a
single game would, and artifact exchange is the connective tissue that makes them community-built.
