# UAT 2026-06-10 — first-start full composite (dry-run + real apply)

Verdict: **PASS** — composite epoch `00005` applied without reboot
(`selection_mode=full_composite`, `composite_top_n=3`, runtime safety OK,
staffing `degraded_selected`). One runtime finding (R-001), two observations.

## Scope

Run the real composite model selection on the fresh-`main` install and gate
the Admin GUI UAT on its result. Sequence correction
(`00-sequence-correction.md`): the Admin GUI UAT started earlier the same day
was paused because the only existing first-start artifacts were from the
pre-fresh-main install (`selection_mode=normal`, `composite_top_n=-1`) — a
composite first-start had to be executed first.

## Environment

- Host: production target (Debian 13 "Trixie", GNOME/GDM, RTX 3080 Ti).
- Install: fresh GitHub `main` 0.32.2 (see
  [UAT-2026-06-10-gh-main-clean-install.md](UAT-2026-06-10-gh-main-clean-install.md)).
- Display safety: first-start invoked from a graphical session; the launcher
  rehomed it into `noemaforge-first-start.service` and kept GDM running by
  default (banner in `logs/06-first-start-full-composite-real.log`).

## Steps and results

### 1. Baseline and artifact quarantine — PASS

`before/01-baseline-before-composite.log` (full status),
`before/03-first-start-not-running.log` (no active run). Old pre-fresh-main
bootstrap artifacts inventoried (`before/02-…log`) and archived to
`artifacts/pre-fresh-main-bootstrap-artifacts.tar.gz` so the composite run
starts from a clean evidence state.

### 2. Composite dry-run — PASS

`logs/04-first-start-full-composite-dry-run.log` (16:36) plus full status
review `after/05-after-composite-dry-run-status.log`. No blockers; plan mode
confirmed before the real run.

### 3. Real composite run — PASS

`logs/06-first-start-full-composite-real.log` (16:39): started as
`noemaforge-first-start.service` (invocation `452f0091…`), display preserved,
abort path (`sudo noemaforge first-start abort`) advertised. Progress followed
via journal; post-run status `after/07-after-real-composite-status.log`.

### 4. Pre-step-8 gate checks — PASS after one reset

- First gate capture (17:19, `07b`/`07c`) and failed-unit details (`07d`,
  `07j`): **`noemaforge-llm-backends-manager.service` (plan-only drift-report
  oneshot) entered `failed` during the composite window** — registered as
  **R-001**; `reset-failed` applied after capturing details.
- Gate v3 (17:33, `07l-pre-step8-gate-v3.txt`): `failed_units_zero=YES`,
  `brainos_not_running=YES`, `noemaforge_runtime_present=YES`,
  `backend_health_ok=YES`, `gateway_health_ok=YES`, `firstboot_applied=YES`;
  `first_start_not_running=NO` only because the first-start unit was still
  active at capture time while finishing (completed by 17:34).

### 5. Normalized composite verdict — PASS

`after/07k-composite-normalized-verdict.txt`:

```text
firstboot_state=applied_no_reboot      firstboot_ok=YES
applied_epoch_id=00005                 selection_mode=full_composite
composite_top_n: status=3 plan=3 effective=3
decision_mode=full_composite           decision_ready_to_apply=YES
runtime_safety_ok=YES
candidate_map_bad_count=0  tournament_bad_count=0  modelstore_unsafe_count=0
staffing_state=degraded_selected
```

`degraded_selected` is a warning state, not a failure: mandatory core roles
are staffed, but some selected roles score below target thresholds (this is
also the Admin GUI glossary gap behind defect D-002/D-003).

### 6. Artifact archival — PASS

`after/08-composite-artifacts.log` inventory;
`artifacts/post-composite-bootstrap-artifacts.tar.gz`; evidence bundles
`first-start-composite-uat-evidence-20260610-173421.tar.gz` and
`…-final-20260610-174316.tar.gz` at the freeze-directory root.

## Findings

- **R-001 (Medium, runtime):** `noemaforge-llm-backends-manager.service`
  failed once during the composite window. It is a plan-only oneshot (apply is
  operator-gated) so impact was nil, but the failure needs a root cause and a
  regression test; `reset-failed` is not a fix. Evidence: `07d`, `07j`.
- **O-001 (Low, tooling):** the key-scan summary
  `after/07g-model-selection-summary.json` carries `null` for most fields
  (`ok`, `selection_mode`, `applied_epoch_id`, …) even though the canonical
  artifacts hold real values — the scan extracted from the wrong layer. The
  normalized verdict (`07k`) had to be assembled manually.
- **O-002 (Low, tooling):** evidence-collection quirks: the failed-unit
  detail script tried to query the literal `●` list-marker as a unit name
  (`07d`), and the final evidence run created a literal `{` directory
  (`unix-uat-final-20260610-184654/{`) — shell quoting bugs in the UAT
  helper scripts.

## Verdict

**PASS.** Real full-composite selection completed end-to-end on the target:
epoch `00005` applied without reboot, runtime safety clean, zero bad
candidates/tournament entries/unsafe ModelStore records, display never lost.
Follow-ups are R-001 plus tooling polish (O-001/O-002).

## Evidence

Freeze directory: `first-start-composite-uat-20260610-163249/`
(`00-sequence-correction.md`, `before/01–03`, `logs/04+06`, `after/05,07–08`,
`artifacts/*.tar.gz`) and root-level
`first-start-composite-uat-evidence-*.tar.gz`,
`unix-uat-final-20260610-184654/` (`MANIFEST.md`, `SHA256SUMS.txt`).
