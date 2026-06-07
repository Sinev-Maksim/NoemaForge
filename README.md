# NoemaForge 0.32.2

**Local-first AI orchestration runtime for governed, privacy-preserving AI execution.**

NoemaForge runs on your machine. The control plane is localhost-only by default, tool access is
mediated by a deny-by-default proxy, and nothing privileged runs without operator approval.

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

---

## Quickstart

```bash
# 1. Assess readiness
noema doctor

# 2. First-start (normal mode — ALWAYS include --keep-display on the target host)
sudo noemaforge first-start --normal --keep-display --show-candidates

# 3. Start the Admin GUI (Windows dev host one-command launcher)
powershell -ExecutionPolicy Bypass -File noemaforge\tools\windows\run_admin_gui.ps1
# Opens http://127.0.0.1:8765/ in your browser.
```

Full setup paths: `noemaforge/docs/onboarding/` — quickstart VM → setup modes → production install.

---

## Architecture in brief

```
Operator (localhost)
    │
    ▼
Admin GUI / Control Plane (127.0.0.1:8765)
    │  plan-then-apply · idempotent jobs · event log
    │
    ▼
ToolProxy  ←──  capability token (scoped · epoch-bound · expiring)
    │
    ▼
Gateway process  ──►  providers / tools / execution plane
    │
    ▼
Contract Epoch  (immutable compatibility snapshot · rollback-able)
```

- **Architecture docs:** `noemaforge/docs/architecture/` — control-plane, toolproxy-capabilities, contract-epochs.
- **Security docs:** `noemaforge/docs/security/` — threat-model, local-only-admin, signed-manifests, capability-tokens.
- **Operations:** `noemaforge/docs/operations/` — first-start, operator-runbook, release-verification.
- **ADRs:** `noemaforge/docs/adr/` — ADR-0001 control-plane-boundary, ADR-0002 contract-epoch-compatibility.
- **Published contracts:** `noemaforge/schemas/` (capability-token, release-manifest), `noemaforge/policies/` (toolproxy, release).
- **API:** `noemaforge/docs/reference/control-plane.openapi.yaml` — the localhost Admin API.
- **UAT scenarios:** `noemaforge/docs/quality/UAT_SCENARIOS_0.32.2.md` — per-feature acceptance tests.

---

## 0.32.2 hardening scope

| Feature | Status |
|---|---|
| Cross-platform paths (`platform_paths` migration) | ✅ |
| Admin-GUI idempotency (model-selection + vault re-inventory) | ✅ |
| Sandbox/canary Windows import-safety + `rlimits_available` metadata | ✅ |
| Unix-only syscall guards (`geteuid` / `SIGKILL`) | ✅ |
| `JobManager.prune_terminal` + path-traversal guard | ✅ |
| One-command Windows Admin-GUI launcher | ✅ |
| Composite-pair diversity scorer for `full_composite` planning | ✅ |
| Premerge checksum-gate with self-explanatory failure messages | ✅ |
| UAT acceptance scenarios | ✅ |
| Architectural legibility layer (docs / schemas / ADRs / OpenAPI) | ✅ |

Release status: `release/0.32.2-hardening` — local static gates **GREEN**. Pending: target-host
(Debian Trixie / GNOME-GDM / RTX 3080 Ti) validation + human GO before merge to `main`.
See `noemaforge/docs/release/RELEASE_FINALIZATION_0.32.2.md`.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). File issues on GitHub; for security vulnerabilities
use the private disclosure process in [`SECURITY.md`](SECURITY.md).

## License

See [`noemaforge/docs/`](noemaforge/docs/) for license and compliance notes.
