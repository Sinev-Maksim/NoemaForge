# Hermes Integration Roadmap — 0.33.0 (architecture notes)

Hermes-inspired capabilities mapped onto NoemaForge's existing architecture (RolePack/WorkflowPack,
the single gateway + ToolProxy, quarantine, Pipeline_RFC/epoch, sessions/events, self-evolution,
the eval suite). Everything imported from external/marketplace sources stays **privacy-first and
quarantine-gated** — nothing reaches the active runtime without passing the import policy (§8).

This is the **0.33.0 design backlog**; none of it is in 0.32.2. Each section is an intent stub to
be expanded into a full design doc when the item is scheduled. Tracked in `TODO.md` → "0.33.0
Roadmap".

## 1. Hermes-style `SKILL.md` parser (quarantine-only import)

- **Intent:** parse external `SKILL.md` descriptors (frontmatter + instructions) into a typed
  internal record.
- **NoemaForge mapping:** a `skill_parser` that emits a `SkillProposal` (§2); output lands **only**
  in the quarantine store (`quarantine.py`), never directly registered as an executable role/workflow.
- **Safety:** no code execution at parse time; all fields untrusted; declared tool/permission
  requests are extracted for review, not granted; size/section caps.

## 2. `SkillProposal` schema (SSR / QA review status)

- **Intent:** a typed proposal record carrying a candidate skill through its review lifecycle.
- **NoemaForge mapping:** JSON-schema'd `SkillProposal` `{id, source, provenance, parsed_skill,
  requested_tools, requested_permissions, ssr_status, qa_status, decision}`. **SSR** = safety/security
  review; **QA** = quality/eval review. Mirrors the knowledge publication gates
  (auto_publish/review/quarantine) and the role-review state machine.
- **States:** `pending → ssr_review → qa_review → approved | rejected | quarantined`.

## 3. `session_search` — SQLite FTS5

- **Intent:** local full-text search across session data.
- **NoemaForge mapping:** FTS5 SQLite index over conversations (`session_store`), batons (handoff
  records), artifacts, and tool events (`event_log`). Read-only query API; **local-first** (no
  remote). Incremental indexing on append; **redaction-aware** (never index secrets); scoped per
  profile (§6).

## 4. Gateway-adapter architecture note (single gateway + allowlist/pairing)

- **Intent:** document the adapter boundary between NoemaForge runtimes and the single gateway
  process.
- **NoemaForge mapping:** one gateway process (the Go gateway over `/run/noemaforge/*.sock`) fronts
  provider/tool access; callers connect via an **allowlist + pairing** (capability tokens, like
  ToolProxy issue/verify). The adapter normalizes provider/tool calls to the gateway protocol.
- **Key points:** single egress + capability chokepoint; pairing handshake; ties into the deferred
  #3b socket migration.

## 5. Provider-runtime-resolver (design doc)

- **Intent:** resolve which provider runtime serves a request.
- **NoemaForge mapping:** a resolver over `llm_backends_manager` / `noemaforge_llm_client` that picks
  a runtime by policy (privacy level, model capability, health) with fallback; complements the
  existing model-selection/router. **Privacy-first default = local.** Routes through the gateway
  adapter (§4); deterministic + auditable.

## 6. Profile isolation contract (config / memory / sessions / gateway tokens)

- **Intent:** guarantee per-profile isolation of state.
- **NoemaForge mapping:** each profile gets isolated config, memory, sessions, and gateway tokens —
  **no cross-profile leakage**. Builds on `platform_paths` (per-profile data roots) + the profile
  concept (`model_profiles` / install profiles). `session_search` (§3) is profile-scoped; gateway
  capability tokens are per-profile; explicit "no shared secrets" invariant.

## 7. Skill-bundle ↔ RolePack / WorkflowPack

- **Intent:** map the external "skill bundle" concept onto NoemaForge's packaging.
- **NoemaForge mapping:** a skill-bundle (skills + assets + manifest) imports as a **RolePack**
  (roles/personas) and/or **WorkflowPack** (pipelines/workflows). The bundle manifest declares roles,
  workflows, required tools, and provenance/license. Quarantine-gated import (§8).

## 8. Marketplace import policy: inspect → quarantine → scan → Pipeline_RFC → epoch

- **Intent:** the fixed safe pipeline for importing third-party marketplace content.
- **NoemaForge mapping:** **inspect** (parse + provenance) → **quarantine** (isolate, no execution) →
  **scan** (safety/security + license) → **Pipeline_RFC** (proposed change + review) → **epoch**
  (apply via the self-evolution epoch switch). Each stage is an explicit gate; human/SSR approval is
  required before `epoch`. Maps onto existing quarantine + Pipeline_RFC + epoch surfaces with an
  auditable trail.

## 9. Hermes benchmark cases (eval suite)

- **Intent:** add Hermes-style benchmark scenarios to the eval suite.
- **NoemaForge mapping:** new scored cases in the role-tournament / eval suite for **memory recall**,
  **skill reuse**, **gateway command**, **cron delivery**, and **safe tool denial**. Each is a
  deterministic-fixture scenario with explicit pass criteria; "safe tool denial" verifies the
  allowlist/pairing (§4) refuses disallowed tools. Integrates with the existing scorecards.
