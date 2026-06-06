# First-Start

First-start is the one-time, operator-driven model-selection/evaluation run that establishes the
initial contract epoch. It is distinct from a later **version upgrade** (`noema upgrade`, 0.33.0).

## Display safety (read first)

Every command that starts model selection or heavy GPU work **must** carry `--keep-display` (or the
equivalent), so the graphical desktop (GDM/GNOME) is preserved. Never run first-start without it.

## Modes

| Mode | Behavior |
|---|---|
| `fast` | First suitable measured candidate is accepted; no composite testing. |
| `normal` | Retain at least two suitable candidates when available; choose best; no composite testing. |
| `full` | Evaluate all available runnable models; choose best. |
| `full_composite N` | Evaluate all models, then plan role compositions from the top `N` candidates (`N=0` = no top-limit before the safety cap). |

## Flow

```bash
# 1. Review readiness (0.33.0: prints backend matrix, approved profiles, epoch, policy status)
noema doctor

# 2. Run first-start in the chosen mode (ALWAYS keep the display)
sudo noemaforge first-start --normal --keep-display --show-candidates

# 3. Review the candidate-selection plan, then apply the epoch switch (separate, approved step)
sudo noemaforge first-start --normal --keep-display
```

First-start produces an operator-reviewable **candidate-selection plan**, a **decision** record, and
a **rollback plan**; the epoch is **not** applied without the separate approve/apply step. The
selected mode is persisted and survives a dashboard refresh.

## Acceptance (UAT)

See `docs/quality/UAT_SCENARIOS_0.32.2.md` (UAT-1 idempotency; UAT-5 launcher). On the target host,
the P0 first-start/display gates are in `release/RELEASE_VALIDATION_CHECKLIST_0.32.2.md`.

## Related

- `../architecture/contract-epochs.md` — what first-start establishes.
- `operator-runbook.md` — day-2 operations.
