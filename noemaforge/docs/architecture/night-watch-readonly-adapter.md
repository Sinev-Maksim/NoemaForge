# night_watch read-only Evolution adapter

Status: pre-UAT co-integration  
Classification: **UAT request findings resolution**

## Boundary

The adapter observes an existing local `night_watch` / current-loop state root and
projects a minimal document set into the canonical
`noemaforge.evolution-execution/v1` contracts.

It does not import the reference implementation, ship its runtime, execute text
found in state artifacts, or expose lifecycle and repository mutation commands.

Public operations are limited to:

- `probe`
- `snapshot`
- `artifacts`
- `blockers`

`mutating_operations` is always empty.

## Canonical projection

A snapshot contains:

- one strict `EvolutionRun`;
- zero or more strict `EvolutionWorkItem` documents;
- adapter-local artifact hashes and blocker observations;
- explicit `null` values for unavailable token, CPU, RAM and VRAM usage;
- a canonical validation report.

The `EvolutionRun` references work items only by their canonical IDs. Legacy
fields from older adapter drafts are not copied into canonical documents.
Legacy phases are mapped only to `planned`, `ready`, `blocked`, `completed`, or
`failed`.

## Read safety

Every selected artifact is:

1. resolved beneath the selected state root;
2. rejected if a symlink escapes that root;
3. required to be a regular file;
4. bounded by a per-file size limit;
5. included only until the artifact-count limit.

External state content is untrusted data. It is never interpreted as an
instruction and never reaches process, service, model, Git, GitHub, camera,
microphone, media, or GPU control.

## Determinism and zero-write evidence

`run_id` and `source_fingerprint` derive from sorted relative paths, sizes, and
SHA-256 content hashes. No current time is injected. When no valid source
timestamp exists, the value is reported as `unknown`.

The co-integration UAT:

- imports the same state twice;
- requires byte-identical snapshot JSON;
- validates all projected canonical documents;
- compares complete repository and observed-state manifests before and after;
- requires a clean Git status before and after;
- writes evidence only outside the repository and state root.

Run through:

```bash
bash noemaforge/tools/uat/run-night-watch-readonly-co-integration.sh \
  --repo-root /path/to/worktree \
  --expected-head <40-character-head> \
  --out /path/outside/repository
```
