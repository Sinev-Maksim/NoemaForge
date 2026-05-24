# Stale Wiki Exact Duplicate Plan 0.32.1

This machine-generated plan identifies versioned wiki pages whose normalized text is exactly identical within the same proposed canonical topic. It does not move files. Each duplicate still needs review, canonical copy confirmation, and an explicit project-trash move step before the stale wiki cleanup TODO can close.

```json
{
  "kind": "StaleWikiExactDuplicatePlan",
  "contract": "stale-wiki-exact-duplicate-plan-core",
  "source_crosswalk": "stale-wiki-topic-crosswalk-core",
  "exact_duplicate_groups": 0,
  "duplicate_sources": 0,
  "auto_move_allowed": false,
  "trash_move_requires_explicit_review": true
}
```

| canonical_topic | retained_source | duplicate_sources | status |
| --- | --- | --- | --- |
