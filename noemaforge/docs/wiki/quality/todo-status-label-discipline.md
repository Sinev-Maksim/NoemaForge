# TODO Status Label Discipline

Active TODO files use explicit status labels so a checked item is never mistaken for runtime completion without evidence. The current labels separate contract coverage, runtime completion, target-machine evidence, roadmap work, blocked work, and documentation cleanup.

Checked active TODO lines must use `done-contract` or `done-runtime`. Open active TODO lines must use an open or blocked status such as `target-open`, `docs-open`, `blocked`, or `roadmap`. Historical archives are preserved as historical records and are not rewritten just to normalize old checklist fragments.

The executable audit is `todo-status-label-audit-core` in `noemaforge/configs/todo-status-label-audit.json`. Its validator scans the active short TODO, current detailed gate file, and roadmap file for bare checked tasks and unlabeled open tasks. This keeps the status vocabulary machine-checkable without weakening the historical archive.
