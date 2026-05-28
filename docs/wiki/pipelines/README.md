# NoemaForge Pipelines

# NoemaForge 0.31.0 update

This repository snapshot is current for NoemaForge `0.31.0`: GUI recovery/help compatibility, code-dev QA sub-team, and user test-case handoff are included.


NoemaForge pipelines are process definitions launched by the administrator. A pipeline calls a role team, but the runtime invariant is **one active LLM by default**. Role-to-role handoff is done through markdown context packets:

```text
task_<task_id>_project_<project_id>_<stage>_context.md
```

This keeps the system compatible with the current legacy live-validation host stability rule: models are switched, not run together.

## Built-in starter pipelines

- `evolution` — architecture clarification → development → tests → integration → optimization → review.
- `book` — research → outline → drafting → review → fact check → export plan.
- `knowledge_graph` — source inventory → entity/relation mapping → provenance → graph patch.
- `release_prep` — inventory → merge analysis → smoke tests → docs/changelog → archive plan.

## CLI

```bash
noemaforge pipeline catalog
noemaforge pipeline run evolution --task-id task_001 --project noemaforge --request "Add pipeline orchestration scaffold" --dry-run
noemaforge pipeline list
noemaforge pipeline show <run_id>
noemaforge pipeline snapshot
```


## 0.31.0 self-improvement pipelines

- [Self-improvement pipelines](self-improvement-pipelines.md)
- [Wiki incremental patch pipeline](wiki-incremental-patch-pipeline.md)


## 0.31.0 additions

- GUI recovery / TTY Trixie fallback: `docs/GUI_RECOVERY_TTY_TRIXIE_0.31.0.md`
- Code-dev QA sub-team: `docs/CODE_DEV_QA_SUBTEAM_0.31.0.md`
- User acceptance test case: `docs/USER_TEST_CASE_0.31.0.md`
- Wiki pipeline: `docs/wiki/pipelines/code-dev-qa-subteam.md`


