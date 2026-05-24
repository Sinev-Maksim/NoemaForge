# Stale Wiki Version Audit

The stale wiki version audit inventories versioned wiki pages before any archival move. The project has many useful wiki articles whose filenames contain older release numbers, and moving them without a topic crosswalk would risk losing prose that still explains current architecture, safety policy, or release discipline.

The active cleanup gate remains open. A safe migration must first map each versioned page to a canonical topic, merge unique prose into the current article when needed, then move only obsolete source pages into project trash after integration. A redirect or crosswalk must preserve where the information went.

The executable contract is `stale-wiki-version-audit-core` in `noemaforge/configs/stale-wiki-version-audit.json`. The local validator in `helpers/stale_wiki_version_audit.mjs` counts versioned wiki files, groups them by directory, and verifies that the active TODO remains open until the actual migration and quarantine work is complete.

The follow-on crosswalk contract is `stale-wiki-topic-crosswalk-core`. It generates `noemaforge/docs/quality/STALE_WIKI_TOPIC_CROSSWALK_0.32.1.md` with one row per inventoried versioned wiki page, a proposed canonical topic, an initial `merge-unique-prose` action, and `needs-review` status.

The exact-duplicate planning contract is `stale-wiki-exact-duplicate-plan-core`. It generates `noemaforge/docs/quality/STALE_WIKI_EXACT_DUPLICATE_PLAN_0.32.1.md` for byte-equivalent duplicate groups, but it does not move files because canonical-copy confirmation and explicit review are still required.

The canonical-copy consolidation contract is `stale-wiki-canonical-copy-plan-core`. It applies only to a bounded batch of exact duplicate groups: the retained review source is copied into the canonical topic when the canonical page is missing, the retained source remains active for human review, and only the byte-equivalent duplicate source is moved into project trash after the trash target is verified inside the project trash root. Eight batches moved all twenty-four duplicate sources and reduced the exact duplicate plan from 24 groups to 0 groups.

The prose merge planning contract is `stale-wiki-prose-merge-plan-core`. It covers the remaining non-identical pages by grouping source files under canonical topic paths, recording normalized hashes and word counts, and requiring `needs-prose-review` before any trash move. The current plan reports 39 prose-review groups and 51 source pages, including 15 missing canonical topic pages that must be created or merged before quarantine.

The single-source canonicalization contract is `stale-wiki-single-source-prose-canonicalize-core`. It is deliberately narrower than a general prose merge: it applies only when the canonical page is missing and there is exactly one source page. Four bounded batches copied eleven source pages into canonical wiki paths, verified canonical SHA-256 hashes, moved those source pages into project trash, and left the cleanup TODO open. The current prose merge plan now reports 28 prose-review groups and 40 source pages, including 4 missing canonical topic pages.
