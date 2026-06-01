# Strict Markdown placement

NoemaForge uses documentation as part of its release contract, so Markdown placement has to be deterministic. Active Markdown belongs in the package documentation tree, helper notes or prelaunch material. The package docs root stays small: `README.md` explains the map, `Manifest.md` states the policy, and `TODO.md` carries current work. Everything else belongs in named subfolders such as architecture, backlog, history, operations, policies, quality, reference, i18n or wiki.

This rule keeps release archives understandable. Operators should not have to decide which parallel changelog, release note or copied research fragment is authoritative. The canonical release history is `noemaforge/docs/history/CHANGELOG.md`, and roadmap state is kept in `noemaforge/docs/backlog/ROADMAP_AND_TODO.md` plus `noemaforge/docs/TODO.md`.

## Why placement must be deterministic

When Markdown files are scattered across arbitrary project directories they become candidates for active release inputs even when they contain draft fragments, raw research dumps, or obsolete status notes. The hygiene gate exists because NoemaForge release archives are signed and checksummed: every file that passes the gate is implicitly treated as authoritative documentation. A misplaced file therefore makes the release evidence ambiguous.

Deterministic placement also means automated tooling — the docs-hygiene scanner, the manifest generator, and the checksum regenerator — can reliably enumerate all canonical documentation without false positives.

## Approved locations

Active Markdown files are permitted only in the following locations:

- `noemaforge/docs/` subfolders: `architecture/`, `backlog/`, `history/`, `i18n/`, `operations/`, `policies/`, `quality/`, `reference/`, `wiki/` and any further named subdirectories within those trees.
- `helpers/` — operational helper scripts and their inline documentation.
- `prelaunch/` — prelaunch tooling documentation and checklists.
- Project root exceptions: `CLAUDE.md`, `README.md`, and `context.md` are the only Markdown files permitted directly at the repository root.
- `noemaforge/docs/` root exceptions: only `README.md`, `Manifest.md`, and `TODO.md` may sit directly under `noemaforge/docs/`.

## Forbidden locations

The following locations must never contain active Markdown files:

- `noemaforge/docs/source_reports/` — raw research dumps and source fragments must not live as active docs.
- `research/` — any directory named research is treated as a staging area, not a release input.
- `todo/` — redundant TODO fragments outside the canonical `noemaforge/docs/TODO.md`.
- `patches/` — patch notes must be integrated into the canonical changelog, not stored separately.
- Any directory named `public/` under `noemaforge/docs/` or `docs/` — the `public` subdirectory spelling is retired and blocked (see `docs-hygiene-policy.json → forbidden_active_text` for the exact patterns).
- `wiki/public/` — the wiki public subfolder spelling is forbidden.

Markdown that appears in any of these locations will be flagged as a hygiene violation and must be remediated before release evidence can be trusted.

## How the hygiene gate enforces this

The enforcement chain has two components. `docs-hygiene-policy.json` is the machine-readable policy file. It declares `allowed_root_markdown` (the exact filenames permitted at the project root and at `noemaforge/docs/`), `approved_doc_prefixes` (the canonical subfolder names), and `forbidden_folder_names` (the blocked path segments). `docs_hygiene_runtime.py` is the scanner that reads the policy and walks the active file tree at runtime, skipping generated caches, trash directories, IDE metadata dirs (`.codex/`, `.cursor/`), and test framework directories (`.pytest_cache/`), then reporting violations. The QA test suite in `noemaforge/tests/test_docs_hygiene_runtime.py` and `test_docs_hygiene_performance.py` covers bad root files, direct docs-root drift, forbidden folders, and forbidden active-text fixtures. All 6 hygiene tests must pass before a release is gated.

## How violations are remediated

When a violation is found, the operator must decide whether the file contains useful standalone wiki prose. If it does, the prose is rewritten into a proper wiki article under the canonical wiki tree and the original file is moved to project trash (`trash/` at the repository root). If the file is a raw dump, duplicate, generated verification note, or obsolete release-note copy, its useful summary is folded into the canonical changelog or a wiki article and the original is moved to trash. Trash is not scanned by the hygiene gate and is not included in release archives.
