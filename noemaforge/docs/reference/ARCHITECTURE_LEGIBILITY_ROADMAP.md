# Architectural Legibility Roadmap

_Analysis + staging of the "architectural business card" research (2026-06). NoemaForge already
has the rare, strong content — ToolProxy, immutable contract epochs, audit-oriented execution,
localhost-only Admin GUI/API, first-start evaluation modes, signed manifests, hypergraph
retrieval, graph linting, wiki projection. The gap is **legibility**: packaging those ideas into a
publicly readable, verifiable surface (front door, docs IA, control-plane narrative, policy
envelope, release verification, operator UX, knowledge projection)._

## Staging principle

The 0.32.2 release code is **frozen** (see `release/RELEASE_FINALIZATION_0.32.2.md`). Therefore:

- **0.32.2 = documentation/legibility layer only** (docs, ADRs, JSON schemas, example YAML, policy
  files-as-data). These are read-only artifacts; they do not change runtime behavior, so they are
  safe to land in the release that makes the repo a strong "architectural business card".
- **0.33.0 = the code features** the research implies (new CLI commands, CI gates, a policy engine,
  generated catalogs). These would reopen frozen 0.32.2 code, so they are deferred.

## Target docs information architecture (0.32.2 doc layer)

```text
noemaforge/docs/
  architecture/  system-context · runtime-topology · control-plane · toolproxy-capabilities · contract-epochs
  security/      threat-model · signed-manifests · local-only-admin · capability-tokens · disclosure
  operations/    first-start · operator-runbook · release-verification
  adr/           ADR-0001 control-plane-boundary · ADR-0002 contract-epoch-compatibility
  reference/     control-plane.openapi.yaml · this roadmap
noemaforge/schemas/      capability-token.schema.json · release-manifest.schema.json
noemaforge/policies/     toolproxy.rego · release.rego        (policy-as-code, validated in 0.33.0)
noemaforge/examples/     flows/* · environments/*             (declarative examples)
```

## Research milestones → NoemaForge tasks (mapping)

| # | Research milestone | NoemaForge mapping | 0.32.2 (doc) | 0.33.0 (code) |
|---|---|---|---|---|
| 1 | Front-door + docs IA | README trust-model; `docs/architecture/*`, ADRs, one system diagram, quickstart | ✅ docs | — |
| 2 | Policy boundary on ToolProxy | `schemas/capability-token.schema.json`, `policies/toolproxy.rego`, capability-token doc | ✅ schema+policy files+doc | `noema policy test` + CI policy-gate |
| 3 | Declarative flows + promotion | `examples/flows/*`, `examples/environments/*`, flow-lifecycle + promotion docs | ✅ examples+docs | `noema flow validate/simulate/apply/rollback` |
| 4 | Signed release gate | `schemas/release-manifest.schema.json`, release-verification doc | ✅ schema+doc | `noema release pack/attest/sign/verify` + `release-gate.yml` |
| 5 | Operator UX + audit surface | local-only-admin + operator-modes + first-start docs, audit-timeline narrative | ✅ docs | `noema doctor` readiness matrix; rollback ledger UI/CLI |
| 6 | Knowledge projection | capability-catalog + epoch-matrix doc format | ✅ doc format | `noema knowledge project --out docs/generated/` + CI |

## New 0.33.0 items requested alongside the research

### A. `noema upgrade` — version upgrade from GitHub (not first-run install)

- **Intent:** upgrade an installed NoemaForge to a newer GitHub release in place, preserving
  user/machine state.
- **Primary path:** GitHub-native — fetch the new release (release assets / tag tree) via the
  GitHub API; apply only tracked package files.
- **Fail-safe path (no API / offline-ish):** open/download the release archive by URL, then
  **replace files by extension/path** rather than wiping the tree — an additive/replace upgrade.
- **Preservation contract (default):** never touch user/machine-changed state — e.g. `context.md`,
  local config, memory, sessions, gateway tokens, data roots (`platform_paths`), profile dirs.
  Maintain an explicit **preserve-list** + **managed-list**; only managed (packaged) files are
  replaced; a dry-run shows the diff before applying; rollback to the previous version retained.
- **Safety:** verify the new release's signed manifest (milestone 4) before applying; display-safe;
  no auto-restart of GPU/LLM surfaces.

### B. Version / file proposal back to GitHub (contribution path)

- **Intent:** let an operator propose a change (a file or a version bump) upstream from inside
  NoemaForge.
- **GitHub path:** open a PR via the GitHub API (fork + branch + commit + PR) when a token is present.
- **No-account ideal:** a tokenless fallback — produce a portable **proposal bundle** (patch +
  provenance + signed manifest) that can be submitted via a relay/email-to-PR bot or a
  "create PR" deep link, so a contributor without a GitHub account can still propose. Maps onto the
  marketplace import policy in reverse (export: inspect → quarantine → sign → propose).

### C. Collaborative-development readiness (analysis → tasks)

Drawn from the research's "legibility layer" — what makes the repo legible to an external
contributor (hiring reviewer, OSS maintainer, platform architect):

- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`/disclosure, issue/PR templates, a
  `docs/architecture/` index linked from README.
- `docs/adr/` (Architecture Decision Records) so design rationale is discoverable, starting with
  the control-plane boundary and contract-epoch compatibility.
- A `control-plane.openapi.yaml` so the Admin API is a published, reviewable contract.
- Deny-by-default ToolProxy policy + capability-token schema as the published extension/security
  boundary (so a reviewer sees tools can't be called without a scoped, epoch-bound token).
- A `noema doctor` readiness matrix + a generated capability/epoch catalog so the system is
  understandable without reading internal RFCs.
- CI gates surfaced as `pr-gate.yml` / `release-gate.yml` so quality/trust is visible, not implicit.

## Sequencing (limit-aware)

1. **Now (this PR):** this roadmap + the core `docs/architecture/*` pages (control-plane,
   toolproxy-capabilities, contract-epochs). Highest leverage, doc-only, safe.
   (`system-context` / `runtime-topology` remain planned — see the target IA above.)
2. **Next 0.32.2 doc PRs:** security docs (threat-model, signed-manifests, local-only-admin),
   operations docs (first-start, operator-runbook, release-verification), ADR-0001/0002, the
   capability-token + release-manifest JSON schemas, example flows/environments, README trust-model.
3. **0.33.0 (code):** the CLI/CI/policy-engine/knowledge-projection features (incl. `noema upgrade`
   and the proposal path) — tracked in `TODO.md` → "0.33.0 Roadmap".
