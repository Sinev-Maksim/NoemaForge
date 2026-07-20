# Administrator Skill: Provider Prompt Optimizer

Canonical skill ID:

```text
admin.provider_prompt_optimizer
```

Status: required for the rebuilt 0.33.0 purpose-and-risk-aware Skill Registry.

## Purpose

Compile one canonical work item into a prompt and context pack optimized for a
specific provider/model family without changing the work item's requirements,
risk, permissions, or release claims.

The skill is non-mutating. It does not call the model, write repository files,
approve tools, or widen scope.

## Access policy

Suggested metadata for the rebuilt registry:

```yaml
id: admin.provider_prompt_optimizer
purposes:
  - orchestration.routing
  - orchestration.prompt_compilation
  - assurance.efficiency
required_capabilities:
  - provider.inspect
  - model.capability_probe
  - prompt.compile
default_risk: low
mutation_capability: none
approval_required: false
owner_persona_purpose:
  - operator.admin
```

Access must be derived from purpose, capabilities, task scope, environment
policy, and autonomy ceiling. The implementation must not hardcode a persona
display name as an authorization exception.

## Input contract

- canonical work-item ID and exact base/head;
- provider, model, family, version, and capability probe;
- task class, risk, and desired outcome;
- allowed paths, tools, commands, and network policy;
- context, output, time, and provider-attempt budgets;
- acceptance criteria and deterministic tests;
- evidence/report schema;
- stop and quarantine conditions;
- author/reviewer family constraints;
- privacy and data-egress classification.

## Output contract

- prompt profile ID/version/hash;
- compiled system/task prompt;
- ordered context-pack manifest;
- tool and mutation policy;
- expected machine-readable result schema;
- retry, compression, and checkpoint policy;
- provider-limit handling;
- independent-review family exclusion;
- explanation of any omitted context;
- provenance linking output to the canonical work item.

The compiler must fail closed when provider capability, work-item scope, privacy
classification, or required evidence is missing.

## Initial prompt profiles

### Codex

- concise reproduction and exact file scope;
- exact expected behavior and test commands;
- forbid speculative refactoring;
- require changed-file and terminal-result report.

### Claude

- architecture, invariants, and root-cause proof first;
- explicit trade-off and conflict matrix;
- implementation only after bounded plan;
- preserve existing contracts and declared behavior.

### Kimi K3

- indexed large-context map;
- long-horizon milestones and checkpoints;
- evidence ledger;
- reuse hashes for unchanged files;
- compact terminal response with detailed artifact.

When membership is unavailable, the profile emits a blocked provider result; it
must not substitute another model while claiming K3.

### Kimi Code

- one isolated workspace and one bounded work item;
- exact allowed paths and commands;
- mandatory tests;
- stop on out-of-scope change;
- no GitHub credentials or control-repository mutation.

### Google Antigravity

- task graph;
- separate read/reason and edit phases;
- bounded subagents;
- explicit approvals;
- each subagent returns an artifact;
- overage disabled under the current budget policy.

### Hermes Agent

- explicit provider and free-tag probe;
- explicit containerized sandbox;
- allowlisted skills only;
- restricted memory and no GitHub credentials;
- bounded fallback chain;
- no self-approval, push, merge, or release marker.

### Local Ollama models

- small schema-constrained tasks;
- low-variance extraction, classification, compression, and deduplication;
- no release decision;
- report model, quantization, VRAM, latency, and schema validity.

### Unknown or free-router models

- stateless auxiliary tasks only;
- strict output schema;
- no mutation and no final independent review;
- mandatory verification by a known family.

## Optimization evidence

A prompt-profile revision requires measured evidence:

- task and test success;
- semantic and provider attempts;
- input/output/context use where available;
- wall time;
- changed lines and out-of-scope changes;
- false-success rate;
- review findings;
- provider-limit behavior.

A model may propose a new profile. Only the owner/Administrator may approve the
profile version used by the production pipeline.
