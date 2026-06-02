# Documentation Completeness Matrix — NoemaForge 0.32.2
Generated: 2026-06-01

## Summary
Overall status: 11 covered / 8 partial / 0 missing

## Required Theme Coverage Matrix

| Theme | Canonical Location | Status | Notes |
|---|---|---|---|
| TODO-driven autonomous improvement | noemaforge/docs/TODO.md + WIKI.md | covered | 20+ analysis cycles documented in TODO.md |
| Release gates and completion discipline | WIKI.md + docs/quality/ | covered | WIKI.md covers release gate process |
| Strict Markdown/documentation hygiene | WIKI.md + docs-hygiene-policy.json | covered | Policy enforced via hygiene tests |
| Single canonical changelog policy | noemaforge/docs/history/CHANGELOG.md | covered | One canonical file, hygiene tests enforce it |
| Deep research integration policy | WIKI.md | partial | Referenced but no dedicated wiki article |
| GitHub main repo publication workflow | WIKI.md | partial | Mentioned but not a full article |
| GitHub Wiki publication workflow | WIKI.md | partial | Covered briefly |
| Windows PowerShell lessons | context.md + CLAUDE.md | partial | Documented in operational context |
| MultiOS runtime direction | noemaforge/docs/wiki/multios-runtime-host-roadmap-0.32.1.md | covered | 81-line article |
| Trust-adaptive governance | noemaforge/docs/reference/PROJECT_CONTEXT.md | partial | Architecture describes it |
| Edge/TinyML/OTA direction | noemaforge/docs/wiki/edge-tinyml-ota-roadmap-0.31.13.alpha.md | covered | 194-line article |
| Local-first/privacy-first constraints | noemaforge/docs/reference/PROJECT_CONTEXT.md | covered | Core constraint in PROJECT_CONTEXT |
| Clean distribution allowlist | noemaforge/docs/wiki/WIKI.md | partial | Referenced, no dedicated article |
| Trash/quarantine policy | context.md + CLAUDE.md + WIKI.md | covered | Policy documented |
| Executable-bit preservation | context.md + CLAUDE.md | partial | Documented in operational files |
| Manifest/checksum regeneration | noemaforge/docs/wiki/WIKI.md | partial | Referenced |
| QA and performance test requirements | noemaforge/docs/quality/ + tests/ | covered | Quality reports exist, 183+ tests |
| Documentation completeness matrix | noemaforge/docs/quality/DOC_COMPLETENESS_0.32.2.md | covered | This file |
| Known blockers and next safe TODO items | noemaforge/docs/TODO.md | covered | TODO.md tracks all open items |

## Stub Wiki Articles Requiring Expansion

These articles have fewer than 30 lines and should be expanded in future releases:
- gui-recovery-tty-trixie.md (5 lines)
- strict-markdown-placement-0.31.21.alpha.md (11 lines) — key policy article
- Various legacy versioned stubs (0.31.x pattern)

## Action Taken This Release

- docs-hygiene-policy.json updated: allowed_root_markdown, approved prefixes, i18n parallel changelogs
- CLAUDE.md: removed forbidden text references, replaced with policy-file references
- .codex/, .cursor/ IDE dirs moved to trash
- docs_hygiene_runtime.py: added .codex, .cursor, pytest, PyYAML to SKIPPED_DIR_NAMES
- All 6 docs hygiene tests passing

## Remaining Gaps

- Deep research integration policy: no dedicated wiki article (PARTIAL)
- GitHub publication workflow: described in context.md but not a full wiki article (PARTIAL)
- Windows PowerShell lessons: in context.md, not a wiki article (PARTIAL)
- Trust-adaptive governance: architecture only, no operational prose (PARTIAL)
- Executable-bit preservation: in context.md, not wiki article (PARTIAL)
- Several stub wiki articles < 30 lines need expansion

## Release Gate Status

release-ready: false — partial docs coverage; all tests pass; blockers documented above
