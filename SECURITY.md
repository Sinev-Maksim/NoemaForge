# Security & Governance

NoemaForge is built safety-first: **local by default, deny-by-default tool access, and
operator-approved privilege.** This page is the security front door; the detailed, checkable
documents are linked below.

## Reporting a vulnerability

**Please do not open a public GitHub issue for a security vulnerability.** Report suspected
vulnerabilities privately to the maintainers, including impact, reproduction / a minimal PoC, and
the version/commit. You'll receive an acknowledgement, and we coordinate a fix + disclosure before
any public announcement.

| Version | Supported |
|---|---|
| 0.32.2 (`release/0.32.2-hardening`) / 0.33.0 (`release/0.33.0-dev`) | ✅ Active |
| < 0.32.2 | ❌ No |

## The model in one line

Privileged, GPU, and tool actions are **structurally gated** — they cannot happen without an
explicit, auditable operator step. The exact list is in **[“What cannot happen automatically”](noemaforge/docs/security/TRUST_BOUNDARIES.md#what-cannot-happen-automatically)**.

## Security & governance documents

| Document | What it covers |
|---|---|
| [Threat model](noemaforge/docs/security/threat-model.md) | Assets, trust zones, adversaries, defenses-by-design. |
| [**Trust boundaries**](noemaforge/docs/security/TRUST_BOUNDARIES.md) | The trust-zone diagram + the “what cannot happen automatically” table. |
| [Local-only admin](noemaforge/docs/security/local-only-admin.md) | Why the control plane binds `127.0.0.1` by default. |
| [Capability tokens](noemaforge/docs/security/capability-tokens.md) | The deny-by-default ToolProxy authorization model. |
| [Signed manifests](noemaforge/docs/security/signed-manifests.md) | Verifiable release provenance. |
| [Disclosure](noemaforge/docs/security/disclosure.md) | Coordinated disclosure process. |
| [ADR-0001](noemaforge/docs/adr/ADR-0001-control-plane-boundary.md) · [ADR-0002](noemaforge/docs/adr/ADR-0002-contract-epoch-compatibility.md) | The decisions behind the boundaries. |

## Checkable guarantees

- **Deny-by-default tool access** — `noemaforge/policies/*.rego`, CI-guarded by `noema policy test`
  (fails if any `default allow := false` is weakened).
- **Localhost-only control plane** — Admin API binds `127.0.0.1`; privileged steps are plan-only
  `sudo` commands (always `--keep-display`).
- **Immutable contract epochs** with approved switch + rollback.
- **Verifiable releases** — `SHA256SUMS` + the signed release-manifest contract
  (`noemaforge/schemas/release-manifest.schema.json`); verify with `noema release verify`.
- **Quarantine-gated import** — untrusted skills/models pass inspect → quarantine → scan →
  Pipeline_RFC → epoch before reaching the runtime.

See the README’s [Public verifiability](README.md#public-verifiability--dont-trust-verify) table to
map each claim to the file/command that proves it.
