# Stale Wiki Single Source Prose Canonicalize 0.32.1

This machine-generated report records a bounded cleanup batch for versioned wiki pages whose canonical topic was missing and whose prose source group contained exactly one page. Each applied row was copied byte-for-byte to the canonical topic, hash-checked, and then moved into project trash. The stale wiki cleanup TODO remains open because multi-source and canonical-existing prose review groups still require manual merge decisions.

```json
{
  "kind": "StaleWikiSingleSourceProseCanonicalize",
  "contract": "stale-wiki-single-source-prose-canonicalize-core",
  "source_prose_merge_plan": "stale-wiki-prose-merge-plan-core",
  "batch_limit": 3,
  "selected_groups_before_apply": 2,
  "canonicalized_sources": 2,
  "active_todo_must_remain_open": true
}
```

| canonical_topic | source | trash_target | words | sha256 | status |
| --- | --- | --- | ---: | --- | --- |
| `noemaforge/docs/wiki/runtime/autostart-runtime-policy.md` | `noemaforge/docs/wiki/runtime/autostart-runtime-policy-0.31.04.md` | `trash/stale-wiki-single-source-prose-20260522/noemaforge/docs/wiki/runtime/autostart-runtime-policy-0.31.04.md` | 151 | `aadfa6ff766a815c90398d52a57cd956cd851c1a21d752130090fc807c2d1c9f` | canonicalized-and-quarantined |
| `noemaforge/docs/wiki/strict-markdown-placement.md` | `noemaforge/docs/wiki/strict-markdown-placement-0.31.21.alpha.md` | `trash/stale-wiki-single-source-prose-20260522/noemaforge/docs/wiki/strict-markdown-placement-0.31.21.alpha.md` | 253 | `a8938d0699a80841a075a1c4912ed22b5ff78ea8ffc7b1184d5af6a8a2b591a9` | canonicalized-and-quarantined |
