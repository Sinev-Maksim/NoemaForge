# NoemaForge 0.32.2 Branch Reconciliation Audit

## Scope

This document records the branch reconciliation state before further 0.32.2 runtime work. It is intentionally conservative: the release branch must not keep accumulating changes until the ancestry, branch content and conflict policy are explicit.

## Branch inventory

| Branch | Relation to `main` | Relation to selected 0.32.2 base | Decision for 0.32.2 |
|---|---:|---:|---|
| `main` | baseline `be0e516d319b49a716eeaa0f4b1ab86ee31b9238` | ancestor | Keep as PR target only. Do not use as functional release base because it lacks the 0.32.x prelaunch payload. |
| `Verion-32.0` | identical to `main` | no unique changes | Ignore for merge. Keep only as historical typo branch unless deleted later. |
| `v0.32.0` | ahead of `main` by 1 commit | ancestor of later 0.32 branches | Superseded by `v0.32.1-prelaunch`; do not cherry-pick separately. |
| `v0.32.0-alpha` | ahead of `main` by 2 commits | ancestor of `v0.32.1-prelaunch` | Superseded by `v0.32.1-prelaunch`; do not cherry-pick separately. |
| `v0.32.1-prelaunch` | ahead of `main` by 3 commits | canonical 0.32.2 base | Use as the functional base for 0.32.2. |
| `release/0.32.2-hardening` | ahead of `main` by 17 commits | ahead of `v0.32.1-prelaunch` by 14 commits, behind by 0 | Continue as 0.32.2 hardening branch. |

## Important ancestry result

`release/0.32.2-hardening` is already based on `v0.32.1-prelaunch`; it is ahead by 14 commits and behind by 0. This means the latest prelaunch branch content is included by ancestry, not by a partial cherry-pick.

`v0.32.1-prelaunch` is ahead of `v0.32.0-alpha` by 1 commit and behind by 0. Therefore `v0.32.0-alpha` is included by ancestry.

`v0.32.1-prelaunch` is ahead of `v0.32.0` by 2 commits and behind by 0. Therefore `v0.32.0` is included by ancestry.

## Conflict policy

Conflict resolution priority for 0.32.2:

1. Preserve `v0.32.1-prelaunch` as the content base unless there is an explicit 0.32.2 safety reason to change it.
2. Prefer 0.32.2 central version management over hardcoded runtime version literals.
3. Prefer display-preserving runtime behavior over any helper or first-start path that may stop GDM/display-manager implicitly.
4. Prefer durable job/session/event state over direct blocking subprocess calls from GUI handlers.
5. Defer unrelated feature expansion even if a branch contains useful future work.

## Branch-change classification

### Included by ancestry

The following broad change groups are already included from earlier branches because the 0.32.2 branch descends from `v0.32.1-prelaunch`:

- 0.32.x documentation, wiki and roadmap import.
- large policy/config catalog additions.
- helper script family and GUI helper updates.
- gateway/inference service scaffolding.
- pipeline/dashboard/config expansions.
- manifest/checksum material from 0.32.1 prelaunch.

### Added in 0.32.2 hardening branch

| Category | Files | Status |
|---|---|---|
| Version centralization | `noemaforge/src/noemaforge_version.py`, root/package/docs `VERSION`, `noemaforge/tools/prep/noemaforge-version-audit.sh` | Added, not fully propagated to every runtime file yet. |
| Orchestration contracts | `noemaforge/src/orchestration_state.py`, `noemaforge/src/job_manager.py`, `noemaforge/src/session_store.py`, `noemaforge/src/event_log.py` | Added as primitives; not fully wired into Admin GUI yet. |
| Display-safe stop behavior | `helpers/noemaforge-stop`, `helpers/noemaforge-llm-stop`, `helpers/noemaforge-service-stop` | Updated; requires target dry-run validation. |
| Model-selection safety | `noemaforge/src/model_selection_runtime.py` | Updated to use centralized runtime version and generated `--keep-display` commands. |
| Release validation docs | `noemaforge/docs/architecture/ORCHESTRATION_HARDENING_0.32.2.md`, `noemaforge/docs/release/RELEASE_VALIDATION_CHECKLIST_0.32.2.md` | Added. |

## Known reconciliation risks

### R1. PR base mismatch makes the GitHub PR look huge

The draft PR targets `main`, while the functional release branch is based on `v0.32.1-prelaunch`. This is expected but makes review noisy: GitHub shows the whole 0.32.1 prelaunch import plus 0.32.2 hardening. For review, compare `v0.32.1-prelaunch...release/0.32.2-hardening`.

### R2. `LICENSE` removal came from the prelaunch branch

The compare from `main` shows `LICENSE` removed by the 0.32.1 branch history. This should be reviewed before final merge. Recommended default: restore or preserve the license file unless there is an explicit legal/product reason not to.

### R3. Historical install scripts and wiki files are noisy

Earlier branches contain many historical install scripts and versioned wiki files. `v0.32.1-prelaunch` already made a cleanup decision. Do not re-add older scripts unless they are moved under a clearly historical path.

### R4. Three-file branch ticket could not be mapped to exactly three files

The repository branch inventory does not expose only three divergent files. The practical branch graph is larger: `v0.32.1-prelaunch` supersedes `v0.32.0` and `v0.32.0-alpha`, while `Verion-32.0` is identical to `main`. If there are three specific external branched files, they must be uploaded or identified by path/branch.

## Current merge decision

Use `v0.32.1-prelaunch` as the canonical content baseline and continue applying 0.32.2 hardening commits on top of it. Do not cherry-pick from `v0.32.0`, `v0.32.0-alpha` or `Verion-32.0` because those branches are either already included or contain no unique content.

## Required before further runtime expansion

- [ ] Replace remaining Python hardcoded `RUNTIME_VERSION = ...` assignments with `from noemaforge_version import RUNTIME_VERSION`.
- [ ] Restore or explicitly justify missing `LICENSE`.
- [ ] Wire `SessionStore`, `JobManager` and `EventLog` into `admin_gui_server.py`.
- [ ] Add duplicate-safe API behavior for model selection continuation and Vault re-inventory.
- [ ] Add GUI-side session restore and input clearing.
- [ ] Run `noemaforge-version-audit.sh --strict-all --expected 0.32.2`.
- [ ] Run Python and shell syntax checks.

## Operator recommendation

Continue development in `release/0.32.2-hardening`, but review diffs against `v0.32.1-prelaunch`, not against `main`, until the final merge-to-main step.
