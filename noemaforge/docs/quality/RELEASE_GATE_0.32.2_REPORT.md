# Release Gate Report — NoemaForge 0.32.2
Generated: 2026-06-01

## Version
- **Previous released**: 0.32.1 (2026-05-21)
- **This release**: 0.32.2
- **Prerelease status**: alpha-hardening (admin GUI hardening sprint complete)

## Version Files Updated
All confirmed consistent at 0.32.2:
- `VERSION`
- `noemaforge/VERSION`
- `docs/VERSION`
- `noemaforge/src/noemaforge_version.py` (EMBEDDED_DEFAULT_VERSION)
- `noemaforge/configs/docs-hygiene-policy.json` (version field)
- `noemaforge/release/release-v0.32.2.yaml`
- `docs/release.json`

## Documentation Completeness Matrix Summary

See full matrix: `noemaforge/docs/quality/DOC_COMPLETENESS_0.32.2.md`

| Status | Count | Themes |
|--------|-------|--------|
| Covered | 10 | TODO-driven process, release gates, changelog policy, MultiOS, Edge/TinyML, local-first, trash policy, QA tests, completeness matrix, known blockers |
| Partial | 9 | Deep research integration, GitHub workflows, PowerShell lessons, trust-adaptive governance, executable-bit, manifest/checksum detail, Markdown hygiene article, clean distribution allowlist, GitHub Wiki workflow |
| Missing | 0 | — |

## Research/Discussion Integration
- Hardening sprint analysis cycles 15–20 fully integrated into `noemaforge/docs/TODO.md`
- Architecture docs updated: `ORCHESTRATION_HARDENING_0.32.2.md` added
- Wiki: `strict-markdown-placement-0.31.21.alpha.md` expanded from 11→43 lines
- Wiki: `WIKI.md` received new "Deep Research Integration Policy" section (~300 words)
- Doc completeness matrix created as new quality report

## Files Changed (this release gate run)

### Source changes
- `noemaforge/src/docs_hygiene_runtime.py` — added .codex, .cursor, pytest, PyYAML to SKIPPED_DIR_NAMES
- `noemaforge/src/admin_gui_server.py` — tasks 73–95 hardening fixes (34 commits)
- `noemaforge/src/session_store.py` — task-93 _append_event locking
- `noemaforge/src/orchestration_state.py` — normalize_job_progress, needs_privilege
- `noemaforge/src/lsp_facade.py`, `mcp_router.py`, `plugin_runner.py` — _safe_int dedup

### Config changes
- `noemaforge/configs/docs-hygiene-policy.json` — allowed_root_markdown, approved prefixes, i18n allowlist, version bump

### Documentation changes
- `CLAUDE.md` — removed forbidden legacy host-name references
- `context.md` — created operational handoff context
- `noemaforge/docs/wiki/strict-markdown-placement-0.31.21.alpha.md` — expanded from stub to 43-line article
- `noemaforge/docs/wiki/WIKI.md` — added Deep Research Integration Policy section
- `noemaforge/docs/quality/DOC_COMPLETENESS_0.32.2.md` — new completeness matrix
- `noemaforge/docs/quality/RELEASE_GATE_0.32.2_REPORT.md` — this file
- `.github/workflows/p0-status-ledger.yml` — neutralized forbidden host reference

### New test files (tasks 73–95)
- `noemaforge/tests/test_job_state_machine.py` (19 tests)
- `noemaforge/tests/test_jobs_list_lock_normalize.py` (15 tests)
- `noemaforge/tests/test_job_get_cancel_normalize.py` (16 tests)
- `noemaforge/tests/test_tasks_lock_normalize_events.py` (15 tests)
- `noemaforge/tests/test_conv_lock_tasks_list_lock.py` (11 tests)
- `noemaforge/tests/test_safe_int_dedup.py` (13 tests)
- `noemaforge/tests/test_read_json_corrupt_normalize_progress.py` (17 tests)

## Files Moved to TRASH ROOT (`C:\Users\sinev\!Projects\trash`)

- `.codex/` (IDE config directory — contained forbidden text)
- `.cursor/` (IDE config directory — contained forbidden text)
- `.cursorignore`
- `.coderabbit.yaml`
- `noemaforge/TODO.md` (duplicate of noemaforge/docs/TODO.md)
- `docs/history/CHANGELOG.md` (stale copy missing 0.32.2 entries)
- `noemaforge/tools/prep/executable_manifest.txt` (new — created this run, not trashed)

## Tests Added
7 new test files, 106 new tests (tasks 73–95 hardening sprint). Previous total: 183 tests.

## Verification Commands Run

| Command | Result |
|---------|--------|
| `py -3 -m py_compile` 808 src+test .py files | PASS |
| JSON parse 444 .json files | PASS |
| YAML parse 142 .yaml/.yml files | PASS |
| `py -3 -m unittest` 183 hardening tests (10 suites) | 183/183 PASS |
| `py -3 -m unittest` 6 docs hygiene tests | 6/6 PASS |
| `noemaforge-premerge-check.ps1` | 13/13 PASS |
| Post-archive verification (8 gates) | 8/8 PASS |

## Archive

| Field | Value |
|-------|-------|
| Name | `noemaforge_0.32.2_release_gate_rechecked.tar.gz` |
| Path | `C:\Users\sinev\!Projects\release-output\` |
| Size | 7.5 MB |
| SHA256 | `91f752079ed0667090022f4df25c49db3f85e896f9a9a6c5362e608b8fae285d` |
| SHA256 sidecar | `noemaforge_0.32.2_release_gate_rechecked.tar.gz.sha256` |
| Executable-bit strategy | `noemaforge/tools/prep/executable_manifest.txt` (921 entries for post-extract restore) |
| Zip | Not created (tar.gz is authoritative) |

## Post-Archive Verification Results

| Gate | Result |
|------|--------|
| Archive integrity (SHA256 match) | PASS |
| Version consistency (VERSION + EMBEDDED_DEFAULT_VERSION) | PASS |
| Markdown placement (no forbidden dirs) | PASS |
| Exactly one CHANGELOG*.md | PASS (1 file) |
| Forbidden dirs absent | PASS |
| Python AST parse (extracted src/) | PASS |
| Executable manifest present | PASS (921 entries) |
| Quality report present | PASS |

## Remaining Blockers

The following items are **target-host-required** or **blocked on branch merges** and cannot be completed from the Windows development machine:

1. **SHA256SUMS comprehensive regeneration** — requires Linux host after all task branches merge to release/0.32.2-hardening
2. **Shell script `bash -n` validation** — requires bash on Linux
3. **Manual smoke tests** — requires target host (GDM, live GPU, browser)
4. **Executable-bit post-extract restore** — requires Linux tar extraction
5. **PR merge** — claude/task-50-server-epoch → release/0.32.2-hardening (34 commits ahead; needs GitHub PR)
6. **PR #2 description** — manual web UI action
7. **JobManager.prune_terminal()** — blocked on tasks 10/11 merging
8. **GitHub Wiki push** — wiki.git remote push requires target machine with git credentials

## Windows-Accessible Gate Results

All Windows-accessible release gates PASS:
- Python parse ✓  
- JSON parse ✓  
- YAML parse ✓  
- Unit tests (183) ✓  
- Docs hygiene (6) ✓  
- Premerge check (13) ✓  
- Version consistency ✓  
- Archive build ✓  
- Post-archive verification (8 gates) ✓  

## Release Readiness

```yaml
release-ready: false
```

**Reason**: Target-host-required gates not yet executed:
- bash -n shell script validation
- Manual smoke tests (GUI, GPU, GDM)
- Executable-bit verification on Linux tar extraction
- All task branch PRs merged to release branch

**Windows-gate status**: `release-ready-pending-target-host`

When all task PRs merge and target-host gates pass, change to `release-ready: true`.
