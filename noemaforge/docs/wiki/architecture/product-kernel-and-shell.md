# Product Kernel, Shell, and Contribution Units

## Consolidated product direction

NoemaForge is converging toward an agent operating environment, not a chatbot wrapper. The stable public MWP should be built around a narrow kernel rather than the full backlog.

## Stable kernel for prelaunch

Base install should keep exactly four active/default roles:

- Admin
- Surgeon
- Scary
- Evolver/Darwin

Optional roles should ship as inactive role packs.

## Current runtime constraint

Only one heavy worker NN should be considered active in the current practical baseline. Role switching must therefore behave like a sleep/wake transaction:

```text
flush state → persist deltas → record baton/context → switch role/model → resume
```

Admin and Scary are logically always present, but should be implemented as lightweight supervisory layers rather than permanently resident heavy models.

## Visual shell requirement

The visual shell is not cosmetic. It is the operational cockpit for:

- session launch;
- role switching;
- approvals and interrupts;
- artifact review;
- daemon/resource budgeting;
- status and recovery.

For public MWP this should become **NoemaShell Lite**: Linux-first, console-safe, and able to run as a lightweight desktop alternative or local app-mode shell.

## Contribution units

Community and internal extensions should be organized as stable units:

| Unit | Purpose |
|---|---|
| `RolePack` | Role prompts, tools, memory profile, evaluation expectations |
| `RoleFlow` | Formal role sequence / workflow graph |
| `KnowledgeGraphPack` | Domain knowledge and graph mappings |
| `EvalPack` | Tests, scorecards, task cases |
| `ModelDeltaPack` | Adapter/LoRA/safetensors patch with provenance |
| `ArtifactPack` | Templates, docs, diagrams, generated outputs |

## Git exchange rule

Git-based exchange should be quarantine-first:

```text
import → validate metadata → scan/sandbox → evaluate → Scary verdict → Admin approval → promote
```

Large binaries should not be normal Git blobs. Use Git LFS/Xet/bucket-backed storage where needed, while keeping metadata and review history in Git.
