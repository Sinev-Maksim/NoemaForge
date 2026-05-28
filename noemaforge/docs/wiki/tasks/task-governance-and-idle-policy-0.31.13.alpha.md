# NoemaForge task governance and idle policy

Version: `0.32.1`

## Task governance

Admin can add, edit, prioritize, assign, block and complete tasks. Task changes are auditable and SR/SSR-reviewable.

## Inactivity timer

The inactivity timer is visible in the GUI. Alpha defaults to `manual_only`. Future modes can take one task at a time or one task per category when idle.

## Dev backlog empty policy

If Dev Team has no tasks, NoemaForge may create a bounded `seed_self_optimization` plan against the latest seed version. The plan is not auto-applied and must include before/after metrics where applicable.
