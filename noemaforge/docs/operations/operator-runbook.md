# Operator Runbook

Day-2 operations for a running NoemaForge instance. All control-plane actions are localhost-only and
plan-then-apply; privileged commands carry `--keep-display`.

## Start the control plane

- **Windows (dev host):** `powershell -ExecutionPolicy Bypass -File noemaforge\tools\windows\run_admin_gui.ps1`
  (opens `http://127.0.0.1:8765/`).
- **Target host:** start the Admin GUI / dashboard service; reach it at `http://127.0.0.1:8765/`.

## Health & readiness

```bash
curl http://127.0.0.1:8765/api/health        # control-plane health
noema doctor                                  # 0.33.0: backend matrix, profiles, epoch, policy status
noemaforge pipeline validate --json           # catalog consistency
noemaforge smoke --profile runtime_only       # gateway/toolproxy-only profile
```

For install/re-entry diagnostics, `runtime_only` means gateway and ToolProxy only.
Do not interpret the intentionally missing main backend socket as a failed install.
Use the backend-required smoke only after `bootstrap_cpu_llm` or a manual backend
start.

`noemaforge mvp-smoke --json` writes per-check artifacts under the reported
`state/checks/<check_id>/` directory. Each failed check should include the command,
exit code, stdout, stderr and report path in the top-level JSON.

## ToolProxy diagnostics

Use the supported diagnostic path before constructing native ToolProxy JSON by hand:

```bash
noemaforge toolproxy diag --json
noemaforge toolproxy smoke --tokens-dir /tmp/noemaforge-cap-tokens
noemaforge toolproxy smoke --live-llm --json
```

The smoke command issues a short-lived capability token, verifies it, and only
uses live `llm.chat` when `--live-llm` is explicitly supplied. Manual native
calls must use the canonical envelope: top-level `action`, top-level `token`,
top-level `args`, and `meta.role`, `meta.project_id`, `meta.run_id`,
`meta.stream_id`, plus an optional `meta.trace_id`. Top-level `actor` or
top-level `role` does not satisfy ToolProxy identity binding.

## Jobs

- View/cancel jobs from the dashboard Jobs panel or `GET /api/jobs` / `POST /api/jobs/{id}/cancel`.
- Duplicate operator actions return the **same job** (idempotency); a double-click never creates two.
- Stale terminal jobs are bounded by `JobManager.prune_terminal` (done/failed/cancelled older than
  the cutoff are removed; active jobs are never pruned).

## Model selection / epoch switch

1. Pick a mode in the GUI (or `noema first-start --<mode> --keep-display --show-candidates`).
2. Review the candidate-selection plan + rollback plan.
3. Apply the epoch switch as a separate, approved step. Keep the previous epoch for rollback.

## Vault re-inventory

Trigger from the GUI (or `/api/vault/reinventory`); a double-click yields **one** job, or a clear
privileged fallback command. Plan-only — the privileged step is operator-run.

## Recovery

- If the display does not return after a model-selection/GPU run:
  `sudo systemctl set-default graphical.target && sudo systemctl start gdm.service display-manager.service`.
- On a failed epoch switch, roll back to the previous epoch and keep artifacts for audit.
- Target-host failure forensics: see `release/RELEASE_VALIDATION_CHECKLIST_0.32.2.md` (P0 failure bundle).

## Related

- `first-start.md`, `release-verification.md`, `../architecture/control-plane.md`.
