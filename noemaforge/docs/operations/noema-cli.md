# The `noema` CLI

`noema` is the unified operator command line for NoemaForge (0.33.0+). It dispatches to a small
set of focused, **stdlib-only, cross-platform** subcommands. Everything here is **display-safe**:
no subcommand starts GPU/model/display work. The privileged first-start (model selection) stays
operator-gated through the Admin dashboard, always with `--keep-display`.

Invoke it as `python noemaforge/src/noema_cli.py <command> …` (or via an installed `noema`):

```text
noema start     one-button start: readiness + ensure dirs + launch the Admin GUI
noema doctor    read-only readiness report
noema release   build (pack) / verify release manifests
noema upgrade   plan / apply / fetch / run an in-place upgrade (preserves user state)
noema --version
noema --help
```

---

## `noema start` — one-button bring-up

Readiness check (`doctor`) → ensure user-writable data dirs → launch the **localhost** Admin GUI →
open the dashboard. Attaches to an already-running GUI instead of double-spawning. Critical
readiness blocks launch unless `--force`.

```bash
noema start                       # readiness + launch + open browser (127.0.0.1:8765)
noema start --check-only          # show the plan + readiness; create nothing, launch nothing
noema start --no-browser --background
noema start --port 8799
```

Security: the Admin control plane is **loopback-only**. `noema start` refuses a non-loopback
`--host` unless you pass `--allow-nonlocal-host` (UNSAFE — exposes the control plane off
localhost). One-button OS wrappers: `tools/windows/start.ps1`, `tools/start.sh`.

---

## `noema doctor` — readiness report

Read-only diagnosis: Python runtime, platform paths, policies/schemas present, admin
control-plane reachability (optional probe), detected model backends, and the display-safety
reminder. Never starts services; never raises.

```bash
noema doctor                      # human report; exit 0 unless a critical check fails
noema doctor --json
```

---

## `noema release` — verifiable releases

Implements the release-manifest contract (`noemaforge/schemas/release-manifest.schema.json`).

```bash
# Build a manifest by hashing every artifact under a root:
noema release pack --root <dir> --version 0.33.0 --contract-epoch <epoch> [--out manifest.json]

# Verify structure + every artifact SHA-256 against disk (read-only; exit 0 only if VERIFIED):
noema release verify <manifest.json> --root <dir> [--require-signature] [--json]
```

`verify` rejects path traversal, duplicate paths, malformed/missing hashes, and missing files —
it is the release GO gate. See `release-verification.md`.

---

## `noema upgrade` — in-place upgrade (preserves user state)

Data-safety invariants by construction: **never deletes anything; never overwrites protected
user/machine state** (`context.md`, and anything under `data/ memory/ sessions/ secrets/ tokens/
vault/ state/ logs/`, plus `*.key/*.pem/*.env/*.token`). Only managed code/doc extensions are
replaced. **Dry-run by default.**

```bash
# Inspect what an upgrade from an extracted release would change:
noema upgrade plan  --current <install> --incoming <extracted-release>

# Apply (omit --apply for a dry-run):
noema upgrade apply --current <install> --incoming <extracted-release> --apply

# Download + extract a GitHub release (zip-slip/symlink/size guarded):
noema upgrade fetch --repo owner/name [--version TAG] --dest <dir>

# End-to-end: fetch -> verify the signed manifest -> plan -> apply (dry-run default):
noema upgrade run   --current <install> --repo owner/name [--version TAG] [--apply]
                    [--allow-unverified] [--preserve <glob>] [--dest <dir>] [--json]
```

`run` aborts **before** touching the install if the release manifest fails verification — or is
absent without `--allow-unverified`. Protect an extra path with `--preserve <glob>` (repeatable).

---

## Exit codes & JSON

Every command exits `0` on success and non-zero on failure (`doctor`/`start --check-only`: `1` on
critical readiness; `release verify`: `1` if not VERIFIED; `upgrade run`: `1` if verification
fails). Most commands accept `--json` for machine-readable output.

## Related

- `first-start.md`, `operator-runbook.md`, `release-verification.md`
- `../security/local-only-admin.md`, `../security/signed-manifests.md`
- `../architecture/control-plane.md`
