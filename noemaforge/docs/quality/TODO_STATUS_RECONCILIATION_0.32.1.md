# TODO status reconciliation 0.32.1

This audit records the normalized TODO structure for the 0.32.1 gate cycle. It is deliberately machine-readable enough for simple scanners while remaining useful to operators.

```json
{
  "apiVersion": "noemaforge.todo-status-reconciliation/v1",
  "kind": "TodoStatusReconciliation",
  "version": "0.32.1",
  "canonical_files": {
    "short_active_todo": "noemaforge/docs/TODO.md",
    "detailed_active_gates": "noemaforge/docs/backlog/CURRENT_0.32.1_TODO.md",
    "crosswalk": "noemaforge/docs/backlog/TODO_CROSSWALK.md",
    "historical_archive": "noemaforge/docs/backlog/HISTORICAL_TODO_ARCHIVE.md",
    "roadmap": "noemaforge/docs/backlog/ROADMAP_AND_TODO.md",
    "status_audit": "noemaforge/docs/quality/TODO_STATUS_RECONCILIATION_0.32.1.md"
  },
  "legacy_paths": [
    {
      "path": "noemaforge/TODO.md",
      "status": "migrated",
      "replacement": "noemaforge/docs/TODO.md",
      "reason": "package-root Markdown is not allowed by the strict placement policy"
    },
    {
      "path": "docs/TODO.md",
      "status": "migrated",
      "replacement": "noemaforge/docs/TODO.md",
      "reason": "root docs Markdown is not allowed by the strict placement policy"
    }
  ],
  "active_status_counts": {
    "target-open": 20,
    "blocked": 2,
    "docs-open": 2,
    "done-contract": 3,
    "roadmap": 2
  },
  "hard_p0_focus": [
    "boot_display_storage_safety",
    "admin_chat_routing",
    "stateful_gui_jobs",
    "runtime_service_safety"
  ],
  "forbidden_text_policy": {
    "legacy_host_literal_used": false,
    "retired_public_docs_path_used": false,
    "stale_status_token_used": false
  },
  "completion_rule": "checked tasks remain complete only when their contract, docs, QA, performance, hygiene and checksum gates pass"
}
```

## Human Summary

- The short active TODO is now `noemaforge/docs/TODO.md`.
- Detailed active 0.32.1 gates are now in `noemaforge/docs/backlog/CURRENT_0.32.1_TODO.md`.
- Historical TODO material is preserved in `noemaforge/docs/backlog/HISTORICAL_TODO_ARCHIVE.md`.
- The roadmap is no longer the dumping ground for historical TODO fragments.
- Root-level TODO mirrors were not recreated because that would violate strict Markdown placement.
