# Legacy BrainOS shutdown-hook removal

Status: `0.33.0` UAT request findings resolution (issue #301).

A host upgraded from BrainOS to NoemaForge can retain an orphaned
`brainos-shutdown-stop.service` systemd unit: it is not owned by any package, predates
NoemaForge, and sources `/usr/local/lib/brainos-common.sh`. When a stray
`*.target.wants/brainos-shutdown-stop.service` symlink is also present, systemd runs the
hook at **boot** (not only at shutdown), where it times out after 45s and leaves a
boot-time failure log entry. The hook only ever managed old `brainos-*` units and
sockets — it does not stop any `noemaforge-*` service — so an enabled copy is pure dead
weight with an active cost.

## Fix

`noema_upgrade.py` — the NoemaForge in-place upgrade orchestrator — gains
`remove_legacy_brainos_shutdown_hook(systemd_dir=DEFAULT_SYSTEMD_DIR)`. It is invoked
automatically from `run_upgrade(..., apply=True)` (i.e. `noema upgrade run --apply`);
dry-run/plan-only calls never touch systemd state.

Safety gates, in order:

1. **Filename match.** Only a unit literally named `brainos-shutdown-stop.service` under
   the systemd unit directory is considered.
2. **Content signature.** The unit's content must contain `brainos-common.sh` or
   `brainos-stop`. A same-named file without that content is left completely untouched —
   matching never happens on filename alone.
3. **Symlinks only, not the unit.** Only enablement symlinks under `*.target.wants/`
   pointing at the confirmed-legacy unit are removed (globbed across every target —
   `multi-user.target.wants`, `shutdown.target.wants`, `graphical.target.wants`, etc.,
   since systemd can enable a unit under several targets at once). The unit file itself
   is never deleted; it is kept on disk as an optional forensic/migration artifact.

This keeps the module's core "upgrade never deletes/overwrites user or machine state"
invariant intact for everything it plans/applies against the install and data roots: the
legacy hook is a confirmed pre-NoemaForge installation defect, not state the invariant is
meant to protect, and the narrow gate above ensures the removal can never touch an
unrelated file.

The function is idempotent: with the unit absent, or already stripped of its enablement
symlinks, it returns a `removed_count: 0` result rather than raising.

## Tests

`noemaforge/tests/test_noema_upgrade.py::NoemaUpgradeLegacyBrainosCleanupTests` covers:
fresh install (no unit present, no-op), the BrainOS-upgrade scenario (symlinks under
multiple `*.target.wants/` dirs removed, unit file preserved), an unrelated
same-named/differently-authored unit (left untouched), a second call after cleanup
(idempotent no-op), a real NoemaForge unit's own enablement symlink surviving
untouched, and `run_upgrade` wiring (cleanup runs on `apply=True`, is skipped on
dry-run).
