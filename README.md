# NoemaForge

**NoemaForge is a local-first AI operating layer: it runs AI models, tools, and pipelines on your
own machine under a localhost-only control plane, where every privileged or GPU action is an
operator-approved, auditable, reversible step — not something that happens to you.**

[![Premerge quality gate](https://github.com/Sinev-Maksim/NoemaForge/actions/workflows/premerge-quality.yml/badge.svg)](https://github.com/Sinev-Maksim/NoemaForge/actions/workflows/premerge-quality.yml)
[![Autonomous dev pipeline](https://github.com/Sinev-Maksim/NoemaForge/actions/workflows/autonomous-pipeline.yml/badge.svg)](https://github.com/Sinev-Maksim/NoemaForge/actions/workflows/autonomous-pipeline.yml)
[![P0 status ledger](https://github.com/Sinev-Maksim/NoemaForge/actions/workflows/p0-status-ledger.yml/badge.svg)](https://github.com/Sinev-Maksim/NoemaForge/actions/workflows/p0-status-ledger.yml)

---

## The system at a glance

```
Operator (localhost, human-in-the-loop)
    │   approves every privileged / GPU action
    ▼
Admin GUI / Control Plane  (127.0.0.1:8765)        ← plan-then-apply · idempotent jobs · event log
    │
    ▼
ToolProxy   ←──  capability token (scoped · epoch-bound · expiring)   ← deny-by-default
    │
    ▼
Gateway process  ──►  providers / tools / execution plane
    │
    ▼
Contract Epoch   (immutable compatibility snapshot · rollback-able)
```

You get a **map of the system**, not just a map of files: the operator drives a localhost control
plane that *plans* actions; ToolProxy is the single deny-by-default gate to tools; and what may run
is pinned to an immutable, rollback-able epoch. See the safety boundaries in
**[“What cannot happen automatically”](noemaforge/docs/security/TRUST_BOUNDARIES.md#what-cannot-happen-automatically)**.

## Try it in ~10 minutes

```bash
# 1. Check readiness (read-only; no changes)
noema doctor

# 2. One-button start: ensures local dirs, launches the localhost Admin GUI, opens the browser
noema start                 # → http://127.0.0.1:8765/
#    (Windows dev host:  powershell -ExecutionPolicy Bypass -File noemaforge\tools\windows\run_admin_gui.ps1)

# 3. In the dashboard: pick a model-selection mode and review the plan. The privileged first-start
#    is emitted as an explicit command for you to run (ALWAYS with --keep-display on the target host):
sudo noemaforge first-start --normal --keep-display --show-candidates
```

Full setup ladder: `noemaforge/docs/onboarding/` (quickstart VM → setup modes → production install).
The unified CLI is documented in [`docs/operations/noema-cli.md`](noemaforge/docs/operations/noema-cli.md):
`noema start · doctor · release · upgrade · policy · catalog`.

## The Admin dashboard

The control plane is a localhost web dashboard at `http://127.0.0.1:8765/`: model-selection plans,
job/event timeline, pipeline drafts behind an approval gate, and artifact download. It starts no
GPU/model work on its own — heavy actions are surfaced as operator-approved commands.

**Guided demo:** the canonical end-to-end walkthrough — install → GUI open → pipeline draft →
approval gate → artifact download → selftest trend → forensics bundle — is in
**[`docs/showcase/SCENARIO.md`](noemaforge/docs/showcase/SCENARIO.md)** (each step with its command +
the governance boundary; screenshot/gif slots reserved for a live capture).

## What is proven here

NoemaForge's claims are **checkable from this repository**, not taken on faith:

- **Acceptance evidence** — [`docs/quality/UAT_SCENARIOS_0.32.2.md`](noemaforge/docs/quality/UAT_SCENARIOS_0.32.2.md): per-feature acceptance tests with explicit pass criteria + a verification record.
- **Signed provenance** — `MANIFEST.json` + `SHA256SUMS` (+ `.sha256` sidecars), generated at
  pre-release; run `python ci/regen_evidence.py && python noemaforge/src/manifest_checksum_exclusion_runtime.py --summary --hash-source working-tree` → `ok=true`.
- **Verifiable releases** — `noema release verify <manifest> --root <dir>` against the
  [release-manifest schema](noemaforge/schemas/release-manifest.schema.json); see [`RELEASING.md`](noemaforge/docs/release/RELEASING.md).
- **Deny-by-default, guarded in CI** — `noema policy test` fails if any `default allow := false` policy is weakened.
- **Green, legible CI** — the badges above + [`docs/ci/PIPELINE.md`](noemaforge/docs/ci/PIPELINE.md).
- **Downloadable acceptance evidence** — the [`publish-evidence`](.github/workflows/publish-evidence.yml) workflow bundles the manifest/checksums + a verification report + the capability catalog + UAT scenarios into a one-click `acceptance-evidence` artifact (with a build-provenance attestation) on every release tag or manual run.

Full claim → proof mapping is the [Public verifiability](#public-verifiability--dont-trust-verify) table below.

---

## Why NoemaForge

| Property | How |
|---|---|
| **Privacy-first** | Runs locally; no data leaves the machine by default. Admin API binds `127.0.0.1` only. |
| **Governed execution** | All tool calls go through **ToolProxy** under a scoped, epoch-bound capability token. Deny-by-default. |
| **Operator-in-the-loop** | Privileged actions produce a reviewable plan + an explicit `sudo` command the operator approves. Nothing runs implicitly. |
| **Versioned compatibility** | Runtime compatibility is pinned to an immutable **contract epoch**. Changes require an approved epoch switch with rollback. |
| **Auditable** | Every action appends to the event log; sessions, jobs, and rollback metadata are persisted locally. |
| **Verifiable releases** | Releases ship with `SHA256SUMS` and a signed manifest; the premerge gate verifies evidence consistency on every PR. |

## Documentation map

- **Architecture:** `noemaforge/docs/architecture/` — control-plane, toolproxy-capabilities, contract-epochs.
- **Security & governance:** [`SECURITY.md`](SECURITY.md) front page → `noemaforge/docs/security/` (threat-model, **trust-boundaries**, local-only-admin, signed-manifests, capability-tokens).
- **Operations:** `noemaforge/docs/operations/` — first-start, operator-runbook, release-verification, noema-cli.
- **ADRs:** `noemaforge/docs/adr/` — control-plane-boundary, contract-epoch-compatibility.
- **Published contracts:** `noemaforge/schemas/` (capability-token, release-manifest), `noemaforge/policies/` (toolproxy, release).
- **API:** `noemaforge/docs/reference/control-plane.openapi.yaml`. **CI:** `noemaforge/docs/ci/PIPELINE.md`.

## Public verifiability — don't trust, verify

| Claim | Verify it via |
|---|---|
| **Signed, reproducible provenance** | `MANIFEST.json` + `SHA256SUMS` (+ `.sha256` sidecars), generated at pre-release. Run `python ci/regen_evidence.py && python noemaforge/src/manifest_checksum_exclusion_runtime.py --summary --hash-source working-tree` → `ok=true`. |
| **Verifiable releases** | `noema release verify <manifest> --root <dir>` against `noemaforge/schemas/release-manifest.schema.json`. See [`docs/operations/release-verification.md`](noemaforge/docs/operations/release-verification.md). |
| **Deny-by-default isolation** | `noemaforge/policies/*.rego`, CI-guarded by **`noema policy test`**. |
| **No hidden autostart / privilege** | Admin API binds `127.0.0.1`; privileged actions are plan-only `sudo` commands (always `--keep-display`). See [`docs/security/local-only-admin.md`](noemaforge/docs/security/local-only-admin.md). |
| **What cannot happen automatically** | [`docs/security/TRUST_BOUNDARIES.md`](noemaforge/docs/security/TRUST_BOUNDARIES.md). |
| **Selftest / acceptance evidence** | [`docs/quality/UAT_SCENARIOS_0.32.2.md`](noemaforge/docs/quality/UAT_SCENARIOS_0.32.2.md) + the per-PR Quality gate. |
| **Rollback-oriented governance** | Immutable contract epochs ([ADR-0002](noemaforge/docs/adr/ADR-0002-contract-epoch-compatibility.md)). |

### CI & governance pipeline

Every change is gated by a small, legible pipeline — see [`docs/ci/PIPELINE.md`](noemaforge/docs/ci/PIPELINE.md):

- [`premerge-quality.yml`](.github/workflows/premerge-quality.yml) — read-only Quality gate (`py_compile`, JSON/YAML, version SoT, git hygiene, manifest/checksum evidence).
- [`autonomous-pipeline.yml`](.github/workflows/autonomous-pipeline.yml) — per-push validation + an independent **Codex review** (CodeRabbit fallback).
- [`p0-status-ledger.yml`](.github/workflows/p0-status-ledger.yml) · [`qa-version-bump.yml`](.github/workflows/qa-version-bump.yml).

> **Releases** are published at the human **GO** milestone (after target-host validation), each
> carrying its verifiable signed manifest — see [`RELEASING.md`](noemaforge/docs/release/RELEASING.md).

---

## Status

`release/0.32.2-hardening` — local static gates **GREEN**; `release/0.33.0-dev` adds the unified
`noema` CLI (start/doctor/release/upgrade/policy/catalog). Pending for a tagged release: target-host
validation + human GO. See `noemaforge/docs/release/RELEASE_FINALIZATION_0.32.2.md`.

## Contributing & security

See [`CONTRIBUTING.md`](CONTRIBUTING.md). For vulnerabilities, use the private process in
[`SECURITY.md`](SECURITY.md) — **do not** open a public issue. License/compliance: [`noemaforge/docs/`](noemaforge/docs/).
