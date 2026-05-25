# NoemaForge 0.32.2 Orchestration Hardening

## Purpose

0.32.2 is a safety and reliability release. The goal is to prevent display blackout, duplicated long-running work, lost GUI state after refresh, unclear Admin routing, and version drift.

## Required runtime primitives

### Job registry

Each long-running operation must be represented as a durable job record before any work begins. Required fields:

- `job_id`
- `kind`
- `status`
- `lock_key`
- `request`
- `progress.current`
- `progress.total`
- `progress.label`
- `artifacts`
- `created_at`
- `updated_at`
- `finished_at`
- `version`

A second request with the same active `lock_key` must return the existing job instead of creating another one.

### Session store

The Admin GUI session must be restored after browser refresh. Required state:

- active persona
- selected mode
- message history
- active jobs
- latest route decision
- latest event index

### Event stream

The GUI must consume a backend event stream for job progress and route confirmations. A terminal fallback may exist, but it must not be the only way to observe progress.

### Admin routing

Admin routing must distinguish:

- smalltalk
- help
- mode selection
- model-selection plan
- model-selection continue
- model-evolution plan
- pipeline execution
- job status
- job stop request

A mode-selection reply must explicitly show the chosen mode and persist it.

## Display safety

`first-start` and model-selection must preserve the graphical session by default. Display shutdown or headless mode requires explicit operator flags and a recovery plan.

## Validation gates

Before release:

```bash
noemaforge version-audit --strict-all --expected 0.32.2
python3 -m py_compile $(find noemaforge/src -name '*.py')
find . -name '*.sh' -type f -exec bash -n {} \;
```

Target validation must include:

- Admin GUI refresh replay
- duplicate model-selection request replay
- mode switching confirmation
- re-inventory permission fallback
- first-start dry-run with display preserved
