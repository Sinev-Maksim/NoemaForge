# NoemaForge wiki

This folder is the canonical wiki of the NoemaForge project: a set of
standalone articles about the system, organized by category folder and
indexed from a single hub.

- **Start here: [WIKI.md](WIKI.md)** — the hub with the maintained
  current-state articles and the full archive index.
- Pages whose filename carries a release marker (`-0.31.12`, `-0.32.1`, …)
  are **historical snapshots**: kept as release-evidence history, banner-marked,
  not maintained.
- Unversioned pages are **current** and must be kept accurate: when behavior
  changes, the same PR updates the affected article.

## Rules

1. One article per page under a category folder; consolidated dump files are
   retired. New research enters only via the
   [Deep Research Integration Policy](governance/deep-research-integration-policy.md).
2. Every page must be reachable from the hub — the wiki integrity check in
   the premerge gate (`ci/wiki_check.py`) fails the PR otherwise, and also
   fails on broken relative links.
3. On merge to `main`, the wiki is published automatically to the GitHub Wiki
   (`.github/workflows/wiki-sync.yml` → `ci/wiki_publish.py`); do not edit
   the GitHub Wiki by hand — it is generated.

This tree (`noemaforge/docs/wiki/`) is the only wiki source; the former
project-root mirror was removed when the package docs tree became canonical.
