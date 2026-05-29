# Strict Markdown placement — 0.32.1

Version scope: runtime `0.32.1`, docs overlay `0.32.1-docs-integrated`.
Updated: 2026-05-29T00:00:00Z

## Purpose

Stub wiki page for the 0.32.1 strict Markdown placement enforcement.
See `strict-markdown-placement-0.31.21.alpha.md` for the predecessor content.

This page is referenced by `configs/docs-hygiene-policy.json` as a required ref anchor.
The canonical enforcement contract is in `src/docs_hygiene_runtime.py`.

## Placement rules (0.32.1)

Active Markdown files are restricted to:
- `noemaforge/docs/` — canonical package documentation
- `helpers/` — helper scripts with inline documentation
- `prelaunch/` — prelaunch governance and tooling

Root-level `.md` files and `docs/` directory entries are legacy anchors preserved
from the NoemaForge workspace structure; they are not writeable by the runtime.

New Markdown documents must be placed inside `noemaforge/docs/` only.
See `docs-hygiene-prelaunch` eval-pack for enforcement details.
