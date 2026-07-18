# Evolution Skill Registry

Status: initial purpose-and-risk-aware registry slice for `0.33.0`  
Classification: **UAT request findings resolution**

## Why this exists

NoemaForge personas share one skill base, but they must not receive the same
view or execution authority. A skill is not permission by itself. It is a
reusable description of how to produce an outcome, while ToolProxy capability,
task authority, environment policy, risk, and approval determine whether one
specific invocation is allowed.

The registry separates:

- **persona** — who is responsible for the outcome;
- **purpose** — why the persona exists and which outcomes are relevant;
- **skill** — how a task can be solved;
- **capability** — which operations may be requested;
- **tool/adapter** — what performs an approved operation;
- **risk** — the danger of this concrete invocation;
- **approval** — an additional gate, never a replacement for purpose or capability checks.

There is no Security super-role and no hardcoded list of persona exceptions.
A visual artist, perimeter analyst, architect, QA persona, or home assistant is
processed by the same deterministic policy.

## Registry layout

The existing `configs/skills.yaml` remains the base registry. NF-native skill
families may be added as deterministic fragments under:

```text
configs/skills.d/*.yaml
```

Fragments are loaded in lexical path order. Skill IDs must be globally unique.
A duplicate ID removes that skill from the usable registry and emits a
`duplicate_skill_id` error; execution fails closed while registry errors exist.

The initial fragment is `configs/skills.d/evolution.yaml`. It contains clean
NF-native specifications extracted from the behaviour of the current
prod-ready loop. External source files and extraction notes remain in the
Local Reference Lab and are not shipped.

## Access decision

A scoped invocation is allowed only when all of the following hold:

1. The skill has purpose, capability, and risk metadata.
2. The skill purpose is relevant to the persona purpose.
3. The skill purpose is relevant to the current task purpose.
4. The persona has every capability required by the skill and task.
5. The environment has not denied a required capability.
6. Effective invocation risk does not exceed the persona autonomy ceiling.
7. Effective invocation risk does not exceed the environment ceiling.
8. The skill does not forbid the effective risk class.
9. Any required approval is present.

Effective risk is the maximum of the skill default and task invocation risk:

```text
effective_risk = max(skill.default_class, task.risk_class)
```

Approval cannot override purpose mismatch, missing capabilities, environment
denial, or an autonomy ceiling.

## Security as an outcome property

Security is not a privileged skill bucket. Assurance work is represented by
ordinary purposes such as:

- `assurance.quality`;
- `assurance.diagnostics`;
- `assurance.perimeter`;
- `assurance.provenance`;
- `assurance.governance`;
- `home.perimeter`.

A persona receives an assurance skill because that outcome belongs to its
purpose and the invocation is within its capabilities and risk ceiling. The
persona name has no effect on the decision.

The same skill can therefore be visible and executable for one persona, denied
for another, allowed at `R1` but denied at `R3` for the same persona, or denied
by environment policy even when persona policy would otherwise permit it.

## Backward-compatible migration

Unscoped legacy callers keep the existing registry listing and execution
behaviour during the migration window. This avoids breaking current ToolProxy
and CLI surfaces in the contract/registry slice.

All new Evolution calls must supply `persona_context` and `task_context`.
Context-aware discovery fails closed for legacy skills that lack policy
metadata. A later ToolProxy binding slice will make scoped context mandatory
for persona-originated skill calls after existing skills have been classified.

Operator/system maintenance calls may remain explicitly unscoped only when the
ToolProxy policy identifies them as such; absence of context must never be
silently interpreted as an unrestricted persona.

## Initial Evolution skills

The seed fragment covers issue/PR inventory, bounded decomposition, blocker
fingerprinting, context packs, root-cause analysis, patch planning, isolated
mutation, deterministic validation, independent review, exact-head checking,
contradiction and release-claim reconciliation, manual-evidence and local
reference boundaries, repository skill extraction, retry budgeting, provider
limit pause/resume, and artifact handoff.

These are NF-native specifications, not shell wrappers. Current loop commands
remain behind the future adapter and are not embedded in skill definitions.

## Next integration slice

The read-only current-loop adapter will translate existing loop state into
Evolution contracts, attach skill IDs and access-decision evidence, import
artifacts idempotently by hash, and report blockers, attempts, provider limits,
and exact HEAD. Its first version will not start, pause, resume, cancel, or
perform Git/GitHub mutation.
