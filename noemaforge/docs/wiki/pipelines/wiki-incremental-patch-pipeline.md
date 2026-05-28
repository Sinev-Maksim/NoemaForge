# Wiki incremental patch pipeline

Pipeline id: `wiki_incremental_patch_publish`

Purpose: publish measurable NoemaForge changes into the project wiki as incremental patches.

## Inputs

- `selftest-report.json`;
- optional previous baseline report;
- user summary or original optimization task;
- optional functional change note.

## Outputs

- `metrics_delta.md`;
- `functional_delta.md`;
- `selftest-report.json` copy;
- `manifest.json`;
- `.patch` file suitable for review and `git apply`.

## Graph Patch Provenance

`graph-patch-provenance-core` is the local contract for graph-aware wiki changes. When a wiki patch is derived from knowledge graph state, the patch must carry a `GraphPatch` record rather than loose prose: source and target graph refs, a SHA256 source graph digest, trace ID, actor role, review state, review decision and a rollback plan are required at the patch level.

Each operation in the graph patch also carries provenance. Node additions, edge updates, claim annotations, conflict resolutions and artifact attachments include source refs, artifact refs, a rationale, confidence and the role that produced the operation. The contract keeps graph patches reviewable and reproducible without turning wiki Markdown into the source of truth. The validator is offline-only and explicitly does not apply graph patches or mutate live graph storage; it proves that the patch is ready for human review and downstream wiki projection.

## Artifact Registry Table

`artifact-registry-table-core` is the shared evidence table for pipeline outputs, review records and graph patches. Every row has an artifact ID, table name, artifact type, relative path, SHA256 digest, trace ID, producer, review state, graph patch reference and creation timestamp. Review rows also identify the reviewer, while graph patch rows must point at a concrete graph patch reference instead of leaving the relationship implicit.

The table is intentionally a contract and example shape, not a storage migration. Validators can confirm that output artifacts, Admin/Scary/Surgeon review artifacts and graph patch bundles are hash-addressed and traceable before a wiki patch is accepted. Later SQLite or GUI storage can materialize the same columns, but the prelaunch gate stays deterministic and does not mutate artifact directories.

## Model Switch Policy

`model-switch-policy-core` keeps the workers used by pipeline and wiki patch review from choosing models through hidden defaults. A role request is resolved in a fixed order: preferred local models, explicitly approved remote models, role fallback models and finally `N/A` when no healthy approved candidate exists. Remote candidates are disabled by default and require an explicit approval flag in the decision input, so a failed local path cannot quietly become a remote call.

The policy is intentionally a validation and planning contract. It reads role policy and model inventory fixtures, reports the checked candidates and selected source, and never starts a local backend or calls a remote model service. That keeps wiki patch generation, graph patch review and firstboot model-selection planning reproducible in offline prelaunch validation.

## Pipeline Performance Metrics

`pipeline-performance-metrics-core` gives wiki patch review a bounded performance evidence shape. A metric artifact must identify each stage and record latency, memory, operation count, artifact bytes and status. The summary includes sample count, maximum latency, maximum memory, total operations, total artifact bytes and status counts, so reviewers can compare small pipeline changes without hunting through logs or accepting free-form claims.

The validator is deliberately artifact-only. It reads the policy and example metrics, checks that metric fields and units are present, rejects negative values or non-integer operation and artifact counts, and resolves the registry and documentation references. It does not inspect live processes, start workers or sample host resources; live profiling can produce artifacts later, but the prelaunch gate only accepts deterministic local evidence.

## Installed Pipeline CLI

`pipeline-cli-install-wiring-core` makes the pipeline CLI entrypoint an install-time contract instead of an assumption. The promoted installer must copy the packaged `noemaforge` tree into `/opt/noemaforge`, expose `/usr/local/bin/noemaforge` as a symlink to `/opt/noemaforge/bin/noemaforge`, and print the same link plan in dry-run mode before any live host mutation. Root `setup.sh` also keeps a syntax selftest for `noemaforge/bin/noemaforge`, so packaging cannot drift away from the command that will be installed.

The packaged CLI is part of the same gate. It must resolve its canonical self under `$ROOT/bin/noemaforge`, reject public wrapper paths as canonical self, and dispatch `noemaforge pipeline` to `src/pipeline_runtime.py`. The contract checks the installed pipeline command surface, including catalog, run, approve, advance, pause, resume, fail, artifact, worktree, template import/append, compaction, metrics, executor-step and validate commands. The validator is offline-only: it reads scripts and command text but never runs a live install.

## Safe Evolution Worktrees

`safe-worktree-evolution-core` keeps development/evolution worktree creation inside a reviewable local boundary. The `noemaforge pipeline worktree create` command now accepts only `evolution` pipeline runs, emits a plan by default, and requires explicit `--apply` before invoking local git. This preserves the operator's review point between planning a patch workspace and mutating the local repository state.

The worktree destination is confined to the run's `worktrees` directory even when a custom path is supplied, and branch names must stay under the `noemaforge/evolution/` namespace. Base refs are sanitized before being passed to git as an argv list, and apply-mode records both a worktree artifact and an event. The offline validator checks these source-level controls without creating a real git worktree.

## ToolProxy Stage Bindings

`pipeline-toolproxy-stage-binding-core` gives each pipeline stage a ToolProxy capability boundary at packet-generation time. The runtime writes a `toolproxy_stage_binding` object into every typed context-packet sidecar and a `toolproxy_stage_bindings.json` map into the run directory, so operators can review the exact action set before issuing or approving a capability token.

Bindings are local-first and deny network access by default. Read-only onboarding stages retain chat, retrieval and status-style actions; development and review stages may request mutating actions only with approval; testing and validation stages mark `exec.run` as sandbox-required. The `noemaforge pipeline toolproxy-policy <run_id> --stage <stage>` command prints the binding for an existing run without contacting a live ToolProxy socket.

## Stage Validators And Smoke

`pipeline-stage-validator-smoke-core` turns stage readiness into a repeatable local check. `noemaforge pipeline stage-validate <run_id> --stage <stage>` verifies the context packet, typed sidecar, sidecar checksum, output quality, contract-matching artifact and ToolProxy stage binding for a single stage. Without `--strict`, unfinished stages are reported as warnings; with `--strict`, placeholder output or missing contract artifacts block the command.

`noemaforge pipeline stage-smoke` creates a temporary offline run, proves that an unready stage cannot advance, writes a synthetic stage output and matching artifact, then proves the same validator marks the stage ready. This gives CI and prelaunch checks a deterministic smoke path without starting LLMs, contacting ToolProxy sockets or relying on target-machine services.

## CLI

```bash
noemaforge wiki-patch create \
  --report /path/to/selftest-report.json \
  --before /path/to/accepted-baseline.json \
  --summary 'short functional summary' \
  --task 'original user or auto-optimization request' \
  --out /tmp/wiki_patch
```

Safe default: generate patch only. Use `--apply --repo /path/to/wiki/repo` only after review.
