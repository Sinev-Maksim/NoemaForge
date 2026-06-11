# Target-host UAT reports — NoemaForge 0.32.2

This folder is the curated, human-readable record of the user acceptance testing
performed on the production target host (Debian 13 "Trixie", GNOME/GDM desktop,
NVIDIA RTX 3080 Ti 12 GiB) during the BrainOS → NoemaForge cutover and the
0.32.2 release validation.

The reports are reworked from the raw evidence captured live on the target.
Raw evidence is **not** stored in this repository; it lives in the freeze
directory `brainos-freeze-to-noemaforge-20260608-131852`:

- on the target host: `~/brainos-freeze-to-noemaforge-20260608-131852/`
- mirrored on the lab workstation: `E:\brainos-freeze-to-noemaforge-20260608-131852\`

Each report cites the raw files it was derived from, so any claim can be traced
back to the original logs, JSON snapshots and archives.

## UAT runs and verdicts

| # | Date (2026) | Run | Verdict | Report |
|---|---|---|---|---|
| 1 | 06-08 | BrainOS freeze + NoemaForge migration cutover | PASS | [UAT-2026-06-08-brainos-freeze-migration.md](UAT-2026-06-08-brainos-freeze-migration.md) |
| 2 | 06-10 | Fresh GitHub `main` clone, clean install + liveness | PASS (`LIVENESS_UAT_OK`) | [UAT-2026-06-10-gh-main-clean-install.md](UAT-2026-06-10-gh-main-clean-install.md) |
| 3 | 06-10 | First-start `--full_composite` (dry-run + real apply) | PASS (epoch `00005` applied) | [UAT-2026-06-10-first-start-full-composite.md](UAT-2026-06-10-first-start-full-composite.md) |
| 4 | 06-10 | Admin GUI (operator) after composite | PASS_WITH_MAJOR_UI_AND_ROUTING_DEFECTS | [UAT-2026-06-10-admin-gui-and-user-experience.md](UAT-2026-06-10-admin-gui-and-user-experience.md) |
| 5 | 06-10 | User-facing pipelines / personas | PASS_WITH_MAJOR_USER_UX_AND_ROUTING_DEFECTS | [UAT-2026-06-10-admin-gui-and-user-experience.md](UAT-2026-06-10-admin-gui-and-user-experience.md) |

Bottom line: **the 0.32.2 runtime core (install, services, model selection,
display safety) is solid on the target host; the Admin GUI / user experience
layer is functional but not production-ready for non-engineer operators.**

## Defect register

All defects and observations found during these runs are consolidated with
canonical IDs in [DEFECT-REGISTER-0.32.2.md](DEFECT-REGISTER-0.32.2.md):

- `D-xxx` — Admin GUI operator defects (from run 4)
- `U-xxx` — user-facing experience defects/requirements (from run 5)
- `S-xxx` — smoke/validation tooling findings
- `R-xxx` — runtime/service findings
- `O-xxx` — non-blocking observations

The register is the source of truth for status; the per-run reports keep the
full observed/expected/acceptance detail. Fix planning lives in
[`noemaforge/docs/TODO.md`](../../noemaforge/docs/TODO.md) and
[`docs/ROADMAP.md`](../ROADMAP.md).

## Conventions for future UAT runs

- One report per run: `UAT-<YYYY-MM-DD>-<slug>.md` with Scope → Environment →
  Steps & results → Findings → Verdict → Evidence sections.
- New defects get the next free ID in the register; reports reference IDs
  instead of duplicating defect text.
- Verdicts use: `PASS`, `PASS_WITH_<QUALIFIER>`, `FAIL`, plus the explicit
  liveness marker `LIVENESS_UAT_OK` where smoke strictness differs from
  operator-level liveness (see S-001).
