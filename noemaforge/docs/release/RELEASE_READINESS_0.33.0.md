# NoemaForge 0.33.0 — Release Readiness

- **Version:** 0.33.0 (source of truth: `VERSION`)
- **Status:** merged to `main` (PR #138); `VERSION` = 0.33.0 on `main`. **Not yet tagged.**
  Remaining gates: release-channel decision, target-host validation, explicit human GO,
  then tag `v0.33.0`.
- **Line:** `release/0.33.0-dev` → `main` (done, #138) → tag `v0.33.0` (pending GO).
- **Process of record:** [`RELEASING.md`](RELEASING.md). Target-host gate list:
  adapt [`RELEASE_FINALIZATION_0.32.2.md`](RELEASE_FINALIZATION_0.32.2.md) to 0.33.0.

This document tracks what is ready and what still gates a 0.33.0 release. It is a
checklist, not an authorization — per the hard rule, no production GitHub Release
is published without explicit human GO **and** target-host validation evidence.

## 1. Release content (merged to `main` via #138)

`release/0.33.0-dev` was merged to `main` (PR #138). On top of the 0.32.2 hardening
baseline, 0.33.0 delivers:

- **Admin GUI / operator UX fixpack** — pipeline confirm + run-progress UX, metrics and
  artifact chat cards, dashboard glossary (D003), pipeline diagram (D006), pipeline
  editor flows (D009/D010), epoch-panel readability, iteration controls, persona
  selector (U003), and a no-silent-noop guarantee.
- **Version centralization** — all active release surfaces promoted 0.32.2 → 0.33.0
  (configs, `release.json`, CLI fallback, audit); `RUNTIME_VERSION` derived from `VERSION`.
- **`noema` CLI surface** — `noema doctor` readiness, `noema start`, and the one-command
  UAT runner.
- **Security / scan hardening** — job-id path-traversal guard, DOM-XSS + subprocess
  Semgrep fixes, SHA-pinned workflows, and the pre-release-only evidence model.
- **Quality / CI** — order-independent broad-pytest collection (`conftest.py`), validator
  doc-ref resolution fixes, and the portable wiki hub-index ordering regression test.

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

- [x] Release content merged → `release/0.33.0-dev` → `main` (#138); `VERSION` 0.33.0 on `main`.
- [ ] **Release-channel decision** — root `release.json` is still `status/channel: pre-alpha`;
  confirm the 0.33.0 channel (keep `pre-alpha`, or promote to `alpha`/`beta`) before the Release.
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
