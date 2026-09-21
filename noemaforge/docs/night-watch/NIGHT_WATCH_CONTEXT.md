# Night Watch Canonical Context

**Status:** canonical non-secret continuation context  
**Branch:** `night-watch`  
**Checkpoint marker:** `unstable, saved for context`

## Role of Night Watch

Night Watch is the controlled diagnostic/recovery/self-heal harness around a specific NoemaForge candidate. It is not the global NoemaForge controller, production authority, Event Store, scheduler, or release approver.

The core proof chain is:

```text
candidate
-> deterministic validation
-> evidence
-> local logically separate review
-> sealed exact identity
-> independent external review
-> external/CI gates
-> human release authority
```

## Canonical principles

- `SUCCESS_FIRST_MAX_EVIDENCE`: safe recovery/degradation and independent-check aggregation before ordinary termination.
- Product-plane and control-plane failures are typed separately.
- Reviewer verdicts are structured and bound to exact candidate/evidence identity.
- Tests are evidence, not self-heal repair targets.
- Mutations are bounded by declared scope and exact rollback.
- Sealed manifest closure defines release/runtime verdict scope.
- Windows PowerShell 5.1 and Win32 path behavior are first-class target semantics.
- Release qualification and per-start target-host preflight are deliberately separate.
- A local self-review is never independent acceptance.
- GitHub checkpoint persistence is mandatory for meaningful WIP.
- Canonical non-secret context lives in repository Markdown, not only chat.

## Current base and historical boundary

The canonical exact NoemaForge base used by the current rules is:

`a3c172f5d60113876f0c103010de411fc30b8c38`

That commit contains the independently re-coded read-only Night Watch adapter against the canonical `noemaforge.evolution-execution/v1` contract. Later self-heal tooling must adapt to the canonical NoemaForge contracts; it must not redefine them.

## Current release-line interpretation

The v3.8.5 evidence supersedes the older “freeze/replay pending” handoff statement at the build-qualification layer. See `NIGHT_WATCH_STATUS.md`.

External trust-boundary evidence remains separate and must not be inferred from local/build qualification.

## Source-of-truth order

When sources disagree:

1. exact repository contracts and exact candidate bytes;
2. machine-readable evidence bound to the exact candidate/release identity;
3. canonical repository Markdown;
4. handoff summaries;
5. chat/history.

A contradiction is recorded and resolved; it is never silently averaged.
