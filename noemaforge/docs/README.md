# NoemaForge documentation

This documentation tree was consolidated for NoemaForge `0.31.13.alpha`.

## Canonical layout

The root of `noemaforge/docs` intentionally contains only three Markdown files:

- `README.md` — this index.
- `Manifest.md` — package and documentation manifest.
- `TODO.md` — active TODO and follow-up list.

All other Markdown documentation is grouped into subfolders:

- `architecture/ARCHITECTURE.md`
- `backlog/ROADMAP_AND_TODO.md`
- `developer/DEVELOPER_NOTES.md`
- `history/CHANGELOG.md`
- `i18n/LOCALIZED_GUIDES.md`
- `operations/OPERATOR_GUIDE.md`
- `policies/POLICIES.md`
- `quality/VERIFICATION_AND_AUDIT.md`
- `reference/KNOWLEDGE_BASE.md`
- `wiki/WIKI.md`

## Consolidation rules applied

- Changelog and release-note material now has one canonical file: `history/CHANGELOG.md`.
- Legacy research/source fragments were folded into consolidated reference, quality, backlog, and wiki documents.
- Duplicate Markdown fragments were skipped during consolidation.
- Files explicitly marked as removed legacy material were not carried forward.
- The legacy public-docs path and the retired external project name were removed from package text.
