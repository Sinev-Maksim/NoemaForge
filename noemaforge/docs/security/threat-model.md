# Threat Model

A concise, operator-facing threat model for NoemaForge. It states what the system defends by
design, who the actors are, and where the trust boundaries sit. It is descriptive of the 0.32.2
hardening posture; enforcement mechanics live in the linked docs.

## Assets

- Operator's local machine, display session (GDM/GNOME), and data roots (config, memory, sessions,
  knowledge, artifacts) under `platform_paths`.
- Capability tokens and gateway tokens (per profile).
- Contract epochs and release artifacts (the compatibility + provenance record).

## Actors / trust zones

| Zone | Trust | Notes |
|---|---|---|
| Operator (localhost) | Trusted | Drives the control plane; approves applies. |
| Control plane (Admin GUI/API) | Trusted, **localhost-only** | Plans + audits; does not execute privileged work directly. |
| Execution plane (models, tools, pipelines) | **Untrusted output** | Runs under ToolProxy + the active epoch. |
| External/marketplace content (skills, models) | **Untrusted** | Enters only via inspect → quarantine → scan → Pipeline_RFC → epoch. |
| Network egress | Restricted | Fronted by the single gateway; deny-by-default for tools. |

## Defenses by design (0.32.2 posture)

1. **Localhost-only control plane** — the Admin GUI/API binds `127.0.0.1` by default; not a public
   service (see `local-only-admin.md`).
2. **Plan-then-apply** — privileged actions are reviewable plans; nothing privileged runs implicitly,
   and model-selection/GPU commands always carry `--keep-display` (display safety).
3. **ToolProxy deny-by-default** — tools are reachable only via a scoped, epoch-bound, expiring
   capability token through one audited proxy (see `capability-tokens.md`).
4. **Contract epochs** — what may run is pinned to an immutable epoch; changes require an approved
   epoch switch with rollback.
5. **Quarantine-gated import** — untrusted external content cannot reach the runtime without passing
   the import policy.
6. **Signed manifests** — release artifacts are hash-listed and verifiable (see `signed-manifests.md`).
7. **Audit trail** — actions append to the event log; jobs/sessions/rollback metadata are persisted.

## Out of scope / assumptions

- A compromised operator account or host root is out of scope (the operator is trusted).
- Cross-platform: POSIX rlimits/namespaces are unavailable on non-POSIX hosts; sandbox metadata
  declares `rlimits_available: false` there so host fallback is not mistaken for resource-limited
  execution.

## Coordinated disclosure

Report suspected vulnerabilities privately to the maintainers (see the repository `SECURITY.md`);
do not open public issues for undisclosed vulnerabilities.
