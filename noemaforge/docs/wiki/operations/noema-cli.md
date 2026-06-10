# noema CLI (current)

`noema` is the operator-friendly front door added on the 0.33.0 line. It wraps
the most common lifecycle actions behind one short command, while the full
`noemaforge` CLI remains the complete control plane. This page is maintained;
command details live in `noemaforge/src/noema_cli.py` and the per-command
modules (`noema_start.py`, `noema_doctor.py`, `noema_release.py`,
`noema_upgrade.py`, `noema_policy.py`, `noema_catalog.py`).

## Subcommands

| Command | Purpose |
|---|---|
| `noema start` | One-button start of the local runtime with safe defaults (no heavy GPU work, display preserved) |
| `noema doctor` | Readiness/health matrix: services, sockets, policies, versions — what is wrong and what to run next |
| `noema release` | Release verification surface: manifests, checksums, provenance evidence |
| `noema upgrade` | Version upgrade from GitHub that never touches user/machine state (config, memory, sessions, tokens, data roots); dry-run diff and rollback first |
| `noema policy` | Inspect/validate the active policy surface (ToolProxy, runtime device policy, governance contracts) |
| `noema catalog` | Generated capability/pipeline/persona catalog |

Safety posture shared by all subcommands:

- nothing starts heavy LLM backends implicitly;
- privileged actions are printed as explicit commands or guarded plans, not
  executed silently;
- `noema upgrade` treats user data as immovable — an upgrade that would remove
  or overwrite operator state is a bug by definition.

## Relationship to `noemaforge`

`noema` is a thin dispatcher; everything it does maps onto `noemaforge`
control-plane commands and the same JSON artifacts. Operators who need the
full surface (first-start modes, smoke, selftest suites, pipeline stage
control, model-selection plans, boot-mode, recovery helpers) use `noemaforge`
directly — see the operations pages in the [wiki hub](../WIKI.md) and
`noemaforge/docs/operations/OPERATOR_GUIDE.md`.

## Typical session

```bash
noema doctor              # what state am I in, what should I fix
noema start               # bring the runtime up safely
noemaforge smoke          # liveness: gateway/backend health + model reply
noema catalog             # what can the system do right now
```

For model selection and epochs (heavy, explicit):

```bash
sudo noemaforge first-start --full_composite 3 --keep-display
```

## Maintenance note

When a `noema` subcommand changes, update this page and the operator guide in
the same PR — the wiki integrity gate keeps the page reachable, but accuracy
is on the author.
