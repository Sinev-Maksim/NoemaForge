# Strict Markdown placement

NoemaForge uses documentation as part of its release contract, so Markdown placement has to be deterministic. Active Markdown belongs in the package documentation tree, helper notes or prelaunch material. The package docs root stays small: `README.md` explains the map, `Manifest.md` states the policy, and `TODO.md` carries current work. Everything else belongs in named subfolders such as architecture, backlog, history, operations, policies, quality, reference, i18n or wiki.

This rule keeps release archives understandable. Operators should not have to decide which parallel changelog, release note or copied research fragment is authoritative. The canonical release history is `noemaforge/docs/history/CHANGELOG.md`, and roadmap state is kept in `noemaforge/docs/backlog/ROADMAP_AND_TODO.md` plus `noemaforge/docs/TODO.md`.

Legacy Markdown is handled by migration or quarantine. If a legacy file contains useful standalone wiki prose, it is moved into the canonical wiki hierarchy. If it is a duplicate, raw source fragment, generated verification note or obsolete release-note copy, its useful summary is folded into canonical docs and the original file is moved to project trash. Trash is not a release input.

The executable gate is `docs-hygiene-prelaunch`. Its runtime scans the active tree, skips generated caches and trash, rejects direct project-root Markdown, rejects extra direct files in `noemaforge/docs`, blocks forbidden documentation folders, and verifies that production-AI TODO commitments remain checked in the canonical TODO. The QA test covers bad root files, direct docs-root drift and forbidden folders; the performance test proves the scanner stays bounded on a synthetic Markdown-heavy tree.

