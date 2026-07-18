# Current-loop read-only adapter

Status: provisional observation bridge for `0.33.0`  
Classification: **UAT request findings resolution**

## Purpose

This adapter lets NoemaForge observe the current prod-ready code-evolution loop
through NF-native Evolution contracts before NF is allowed to control it.

The first version is intentionally read-only. It exposes only:

```text
probe
snapshot
artifacts
blockers
```

It does not expose or internally implement start, stop, pause, resume, cancel,
apply, commit, push, merge, service, or GitHub-write operations.

## Why state-root probing is required

The current v46 wrapper exports:

```text
NF_V46_STATE_DIR=~/.local/share/noemaforge-agent-runs/token-aware-0330-v46
```

The historical base runner independently defaults `STATE_ROOT` to:

```text
~/.local/share/noemaforge-agent-runs/token-aware-0330-v3
```

Both layouts can therefore exist on the same host. The adapter considers, in
order:

1. an explicit state root;
2. `STATE_ROOT`;
3. `NF_V46_STATE_DIR`;
4. the conventional v46 path;
5. the conventional v3 path.

Without an explicit path, candidates are scored by known indicators such as
`status.md`, coordinator lock metadata, scheduler state, issue work items,
logs, and ledger. Multiple live candidates are reported as ambiguity; they are
not silently merged.

## Imported state

Known read-only sources include:

- `status.md`, `ledger.md`, `coordinator-lock-v51.json`;
- current and legacy scheduler PR state;
- issue work-item and recovery records;
- parked review records;
- manual evidence pending markers;
- security, Evolution, and visual evidence;
- semantic-loop quarantine markers;
- state-root-local provider pause and write-block markers;
- bounded loop logs.

Provider markers outside the selected state root are not read by this adapter.
A future provider adapter may expose them through its own scoped capability.

## Canonical projection

A snapshot contains:

- one `EvolutionRun`;
- normalized issue and PR `EvolutionWorkItem` records;
- hash-addressed artifact references;
- stable blocker fingerprints;
- observed active agent and cycle;
- explicit unknown resource/token telemetry fields;
- warnings for malformed, ambiguous, incomplete, or legacy state.

A short Git SHA from `status.md` is never padded or treated as an exact HEAD.
It is represented as `null` with `status_head_is_not_full_sha`.

## Read boundary

Every file read must:

- resolve inside the selected state root;
- be a regular file;
- remain below the configured byte limit;
- fit within the bounded artifact count.

Symlinks escaping the state root are rejected. Malformed JSON becomes a warning
and does not create synthetic success evidence.

The adapter hashes artifacts but does not copy, rewrite, delete, lock, or touch
them. Repeated observations therefore produce the same artifact and blocker
identities, aside from the outer capture timestamp.

## Migration sequence

After contract, skill, and read-only adapter review:

1. expose the snapshot in Admin GUI and `self_development` as observation only;
2. dogfood state import against the current host loop;
3. add ToolProxy-gated control operations one at a time;
4. keep commit/push/merge owned by one authoritative controller;
5. replace loop internals with NF-native workers and resource leases in `0.33.1`.
