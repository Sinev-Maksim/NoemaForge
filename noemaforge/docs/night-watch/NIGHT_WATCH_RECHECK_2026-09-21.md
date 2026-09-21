# Night Watch v3.8.5 Recheck — 2026-09-21

**Classification:** `UAT request findings resolution`  
**Checkpoint:** `unstable, saved for context`

## Scope

This recheck reconciles:

- the historical Night Watch context/handoff;
- the later v3.8.5 qualification artifacts dated 2026-09-16;
- the current canonical development rules;
- the GitHub repository state and exact base;
- the later engineering self-check document.

## Findings

### PASS — build/frozen release qualification

The machine-readable evidence is mutually consistent on the release identity and qualification outcome:

- outer frozen envelope SHA-256:
  `6adbcabac444c393cb40b7f4cb495b6a78d410c2adefe2ce81cbd74aad3dbd5d`;
- inner frozen release SHA-256:
  `16e11736e5241e310b56f84acdd3a71e1d95b9a27f3a29d9ee26f221b45e371c`;
- pre-send: 3 consecutive PASS, `SKIP_COUNT=0`;
- fault injection: 5 PASS, 30 priority classes, 56 scenarios, 96 provider-role permutations;
- deployment selftest: 5 PASS, final suite 34 checks;
- empty current: PASS;
- dirty current: PASS;
- outer/inner ZIP CRC: PASS;
- handoff replay: PASS, 11 -> 12 runs, 1069 objects, repeat merge idempotent;
- root-cause extrapolation: 3 stable cycles, 0 unresolved defects.

The earlier screenshot showing 32 deployment checks is not contradictory: the later frozen evidence contains a later 34-check suite after additional findings were added.

### PASS — architecture/rule parity

The available pre-send evidence reports PASS for the relevant invariants:

- sealed package closure and SHA integrity;
- Windows path/encoding/PowerShell source guards;
- product/control-plane separation;
- immutable tests;
- exact-base/worktree handling;
- bounded provider/helper execution;
- rollback after untrusted mutation;
- provider-role degradation and separation of duties;
- success-first/max-evidence aggregation;
- atomic deployment semantics;
- cumulative handoff integrity/idempotence;
- pre-send self-pollution guard;
- root-cause extrapolation policy;
- controller version marker v3.8.5.

### FIXED — documentation drift

The later `ENGINEERING_SELF_CHECK.md` still has stale unchecked release-freeze boxes even though later machine-readable evidence proves those build gates PASS.

Canonical status is now derived from exact machine evidence and recorded in `NIGHT_WATCH_STATUS.md` and `NIGHT_WATCH_EVIDENCE_INDEX.md`.

### PENDING — real exact-final Windows execution

The available `HOST_PRE_SEND_FINAL` artifact is host-runtime **mode** executed in the Linux build sandbox. It is not a real Windows PowerShell 5.1 execution record for the exact frozen v3.8.5 bytes.

Older Windows logs are useful regression history but cannot satisfy this exact-release target gate.

### PENDING — external review/promotion

No available evidence currently proves:

- remote independent exact-SHA review of the exact final v3.8.5 frozen candidate;
- final CodeRabbit gate where required;
- human release GO/tagged release.

## Source-level rerun limitation

A true full source/byte-level rerun of v3.8.5 cannot be performed from reports alone. The exact frozen v3.8.5 outer/inner ZIP bytes are not currently present in the GitHub repository or retrievable as raw package files from the available project/library sources.

Therefore:

```text
EVIDENCE_LEVEL_RECHECK=COMPLETE
REPOSITORY_CONTEXT_RECHECK=COMPLETE
EXACT_FROZEN_BYTE_LEVEL_RERUN=BLOCKED_BY_ARTIFACT_AVAILABILITY
```

This is an artifact-availability/control-plane limitation, not a PRODUCT failure and not evidence that the previous frozen qualification failed.

## Required next proof

Recover an artifact whose SHA-256 matches the frozen outer identity exactly. Then:

1. verify outer SHA;
2. clean-extract;
3. verify inner SHA;
4. rerun release qualification against those immutable bytes;
5. install/run the exact frozen release on real Windows PowerShell 5.1;
6. preserve installer/host/runtime evidence;
7. bind remote independent review to the exact release/candidate identity;
8. only then seek human promotion GO.
