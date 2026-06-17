# NoemaForge 0.33.0 — Release Readiness

- **Version:** 0.33.0 (source of truth: `VERSION`)
- **Status:** pre-release hardening — **not yet tagged**. Awaiting PR merges, then
  human GO + target-host validation.
- **Line:** `release/0.33.0-dev` → `main` → tag `v0.33.0`.
- **Process of record:** [`RELEASING.md`](RELEASING.md). Target-host gate list:
  adapt [`RELEASE_FINALIZATION_0.32.2.md`](RELEASE_FINALIZATION_0.32.2.md) to 0.33.0.

This document tracks what is ready and what still gates a 0.33.0 release. It is a
checklist, not an authorization — per the hard rule, no production GitHub Release
is published without explicit human GO **and** target-host validation evidence.

## 1. Release content (PRs into `release/0.33.0-dev`)

Already merged: #97 (repo-security rulesets), #98 (CodeQL fixes), #99 (admin-state
glossary), #103 (0.33.3 roadmap), #104 (0.32.2 broad-pytest, on the 0.32.2 line).

Open and mergeable — recommended merge order (low-risk → keystone last):

1. **#110** — version promotion 0.32.2 → 0.33.0 (configs, `release.json`, CLI, audit).
2. **#111** — 0.33.0 CHANGELOG entry.
3. **#109** — TODO hygiene + records the validator-class follow-up.
4. **#108** — Class A root-doc test fix (42 `*_qa.py` read loops + vacuous guard).
5. **#107** — D2: `bin/noemaforge` integration tests via the Python entrypoint.
6. **#105** — broad-pytest collection isolation (`conftest.py`) — keystone; makes
   the suite run order-independent.

All six are independent except the shared `Claude_stats.md` append (resolve by
keeping all rows). After merge, `release/0.33.0-dev` → `main`.

## 2. Gate status (verified on the hardened tree, Windows / CPython 3.14)

- [x] **Version consistency** — `test_version_03200_qa` passes; every active
  release surface equals the SoT (0.33.0). `RUNTIME_VERSION` derives from `VERSION`.
- [x] **Docs hygiene** — `docs_hygiene_runtime.py` → `ok: true`.
- [x] **Wiki integrity** — `ci/wiki_check.py` → OK (142 pages, hub index fresh).
- [x] **Compile / JSON / bash** — `py_compile` clean on changed files; all configs
  parse; `bash -n` clean on edited scripts.
- [x] **Premerge quality gate** — version derived from SoT (no hardcoded literal),
  so it validates 0.33.0; the open release PRs report mergeable with no CI failures.
- [~] **Broad pytest** — NOT a CI gate. The order-dependent collection blocker is
  fixed (#105); the suite now runs to completion (~1950 pass). The remaining
  pre-existing failures are classified in
  `noemaforge/docs/uat/BROAD-PYTEST-0.33.0-FINDINGS.md` (lands on this line with #105)
  (root-doc drift fixed in #108; CLI tests fixed in #107). Not release-blocking.

## 3. Tag + evidence flow (at release, per `RELEASING.md`)

Evidence is **pre-release-only**: `MANIFEST.json` / `SHA256SUMS` are NOT tracked on
dev. They are generated and verified at the tag:

1. `python ci/regen_evidence.py` then
   `manifest_checksum_exclusion_runtime.py --summary --hash-source working-tree`
   → `ok=true, hash_mismatches=0`.
2. `noema release pack … --version 0.33.0 …` → `dist/release-manifest.json`.
3. `noema release verify …` → `OVERALL: VERIFIED`.
4. Tagging `v0.33.0` runs `publish-evidence.yml`, which regenerates + verifies the
   evidence and assembles the signed release bundle.

## 4. Human-gated — required before the GitHub Release (HARD RULE)

- [ ] All six release PRs merged → `release/0.33.0-dev` → `main`.
- [ ] **Target-host P0 validation** on the production target (Debian 13 Trixie,
  GNOME/GDM, RTX 3080 Ti): install, services, model selection, display safety,
  Admin GUI — per the 0.32.2 finalization gate list adapted to 0.33.0.
- [ ] **Explicit human GO.**
- [ ] Tag `v0.33.0`; let `publish-evidence.yml` produce the evidence; publish the
  GitHub Release attaching the archive, `MANIFEST.json` + `SHA256SUMS`, and the
  signed release manifest.

## 5. Known follow-ups (owner-gated, NOT release-blocking)

- **Validator class** (~26 `missing_ref`/`docs_tokens_missing`): shared src policy
  validators (`_docs_report`/`_resolve_refs`) check non-existent project-root docs
  instead of canonical `noemaforge/docs/**`. Diagnosis + recommended fix recorded
  in `noemaforge/docs/TODO.md`. Touches release-gating logic across ~26 files —
  needs owner sign-off + a full regression. Broad-pytest only (not a CI gate).
- **Trace-coverage subclass** (`surface_trace_missing:admin_gui_jobs`) — same family.
- **i18n RELEASE_NOTES** (10 languages under `noemaforge/docs/i18n/`) — need a
  0.33.0 entry; a localization task for the owner/translators.
