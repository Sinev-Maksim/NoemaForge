# NoemaForge 0.32.2

**Local-first AI orchestration runtime for governed, privacy-preserving AI execution.**

[![Premerge quality gate](https://github.com/Sinev-Maksim/NoemaForge/actions/workflows/premerge-quality.yml/badge.svg)](https://github.com/Sinev-Maksim/NoemaForge/actions/workflows/premerge-quality.yml)
[![Autonomous dev pipeline](https://github.com/Sinev-Maksim/NoemaForge/actions/workflows/autonomous-pipeline.yml/badge.svg)](https://github.com/Sinev-Maksim/NoemaForge/actions/workflows/autonomous-pipeline.yml)
[![P0 status ledger](https://github.com/Sinev-Maksim/NoemaForge/actions/workflows/p0-status-ledger.yml/badge.svg)](https://github.com/Sinev-Maksim/NoemaForge/actions/workflows/p0-status-ledger.yml)

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

## Public verifiability — don't trust, verify

NoemaForge's guarantees are designed to be **checkable from the repository**, not taken on faith:

| Claim | Verify it via |
|---|---|
| **Signed, reproducible provenance** | `MANIFEST.json` + `SHA256SUMS` + `noemaforge/checksums/SHA256SUMS` (+ `.sha256` sidecars). Run `python noemaforge/src/manifest_checksum_exclusion_runtime.py --summary --hash-source git-index` → `ok=true`. |
| **Verifiable releases** | Release-manifest contract (`noemaforge/schemas/release-manifest.schema.json`); verify a release with **`noema release verify <manifest> --root <dir>`**. See [`docs/operations/release-verification.md`](noemaforge/docs/operations/release-verification.md) + [`RELEASING.md`](noemaforge/docs/release/RELEASING.md). |
| **Deny-by-default isolation** | Policies in `noemaforge/policies/*.rego`; the contract is CI-guarded — **`noema policy test`** fails if any `default allow := false` is weakened. |
| **No hidden autostart / privilege** | The Admin API binds `127.0.0.1`; privileged actions are plan-only `sudo` commands (always `--keep-display`). See [`docs/security/local-only-admin.md`](noemaforge/docs/security/local-only-admin.md). |
| **Selftest / acceptance evidence** | [`docs/quality/UAT_SCENARIOS_0.32.2.md`](noemaforge/docs/quality/UAT_SCENARIOS_0.32.2.md) + the per-PR Quality gate (py_compile · JSON/YAML · versions · evidence). |
| **Rollback-oriented governance** | Immutable **contract epochs** with a two-step, approved switch + retained prior epoch ([ADR-0002](noemaforge/docs/adr/ADR-0002-contract-epoch-compatibility.md)). |

### CI & governance pipeline (the `.github/workflows`)

Every change is gated by a small, legible pipeline — see [`docs/ci/PIPELINE.md`](noemaforge/docs/ci/PIPELINE.md):

- [`premerge-quality.yml`](.github/workflows/premerge-quality.yml) — read-only Quality gate: `py_compile`, JSON/YAML parse, version source-of-truth, git hygiene, and the **manifest/checksum evidence gate**.
- [`autonomous-pipeline.yml`](.github/workflows/autonomous-pipeline.yml) — per-push validation + an independent **Codex CLI review** (with a CodeRabbit fallback) on every `claude/*` branch.
- [`p0-status-ledger.yml`](.github/workflows/p0-status-ledger.yml) — append-only P0 readiness ledger.
- [`qa-version-bump.yml`](.github/workflows/qa-version-bump.yml) — gated version-bump automation.

> **Releases:** GitHub Releases are published at the human **GO** milestone (after target-host
> validation), each carrying its verifiable signed manifest — see [`RELEASING.md`](noemaforge/docs/release/RELEASING.md).
> The release-engineering artifacts already live in the repo so a release can be cut and
> independently verified the moment GO is given.

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
