# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.32.2 (release/0.32.2-hardening) | ✅ Active |
| < 0.32.2 | ❌ No |

## Reporting a vulnerability

**Please do not open a public GitHub issue for a security vulnerability.**

Report suspected vulnerabilities privately to the maintainers. Include:
- A description of the vulnerability and its impact.
- Steps to reproduce, or a minimal proof-of-concept.
- The version/commit where you observed it.

You will receive an acknowledgement within a reasonable timeframe. We will coordinate a fix and
coordinated disclosure before any public announcement.

## Security model

- The Admin control plane binds `127.0.0.1` by default (localhost-only). See
  `noemaforge/docs/security/local-only-admin.md`.
- All tool access is mediated by ToolProxy under deny-by-default capability tokens. See
  `noemaforge/docs/security/capability-tokens.md` and `noemaforge/docs/security/threat-model.md`.
- Releases include `SHA256SUMS` for artifact verification. The signed release-manifest contract
  (`noemaforge/schemas/release-manifest.schema.json`) defines the full verification path for 0.33.0.
- Untrusted external content (marketplace skills, models) must pass the import policy
  (inspect → quarantine → scan → Pipeline_RFC → epoch) before reaching the runtime.
