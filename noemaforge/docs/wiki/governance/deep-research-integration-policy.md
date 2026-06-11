# Deep Research Integration Policy

How external research material (LLM-generated reports, web-scraped content,
draft analysis dumps, unedited API responses) is allowed to enter the
canonical documentation tree. This page is the standalone home of the policy
that previously lived inside the consolidated wiki dump.

NoemaForge releases include wiki articles as part of the signed release
evidence. This means raw research reports must never be added directly as
active wiki files.

## Rules

**Raw reports must not become active files.** A research report that arrives
as a raw file is a staging artifact. It belongs in `trash/` or a dedicated
staging area excluded from the release archive. The hygiene gate flags any
file under research-dump paths as a violation precisely because those
locations are associated with raw research inputs.

**Research material must be converted to prose.** Before any research finding
can appear in the wiki, it must be rewritten as standalone prose with a clear
scope, a concrete finding or recommendation, and enough context that a reader
unfamiliar with the original research can understand it without following
external links. Copy-pasted LLM output does not qualify. The prose must be
written in the voice of the project, not the voice of a research assistant
summarizing search results.

**Link-only stubs are not acceptable wiki content.** A wiki article that
consists solely of a heading and a list of links provides no standalone value
and cannot be trusted as release evidence. Every wiki article must have at
least 150 words of original prose. Articles below that threshold are stubs
and must be expanded before the release gate closes. The documentation
completeness matrix (`noemaforge/docs/quality/DOC_COMPLETENESS_0.32.2.md`)
tracks stub articles that require expansion.

**Consolidated dumps are retired.** Merging many fragments into one giant
"consolidated wiki" file is the inverse failure mode of raw dumps: it hides
articles from navigation and lets per-article history rot. Every fragment
must live as its own page under a category folder; the hub (`WIKI.md`) is an
index, not a container.

## Integration workflow

When a research pack arrives, the operator must:

1. read the raw material and identify the findings that are genuinely new to
   the canonical documentation;
2. write a wiki article (or expand an existing one) with those findings in
   project prose, under the right category folder;
3. add the article to the hub index in `WIKI.md` (the wiki integrity check in
   the premerge gate fails on unreachable pages);
4. move the original raw file to `trash/`;
5. record the integration in `noemaforge/docs/history/CHANGELOG.md`.

The release gate may not be closed while raw research files remain in active
documentation paths.
