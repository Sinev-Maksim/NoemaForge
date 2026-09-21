# Night Watch v3.8.5 Recheck — 2026-09-21

**Classification:** `UAT request findings resolution`  
**Checkpoint:** `unstable, saved for context`

## Result

The previously missing exact frozen artifact was found and recovered.

```text
EVIDENCE_LEVEL_RECHECK=COMPLETE
REPOSITORY_CONTEXT_RECHECK=COMPLETE
EXACT_FROZEN_BYTE_LEVEL_RERUN=PASS
TARGET_HOST_EXECUTION=PENDING_USER_RUN
```

## Exact identities

- outer frozen installer envelope:
  `6adbcabac444c393cb40b7f4cb495b6a78d410c2adefe2ce81cbd74aad3dbd5d`;
- inner sealed release:
  `16e11736e5241e310b56f84acdd3a71e1d95b9a27f3a29d9ee26f221b45e371c`;
- exact NoemaForge base:
  `a3c172f5d60113876f0c103010de411fc30b8c38`.

## Independent archive audit

PASS:

- outer ZIP CRC and exact 7-entry inventory;
- outer path safety, duplicate detection, casefold collision detection, symlink rejection;
- installer manifest hash/size parity;
- nested sealed-release SHA consensus;
- inner ZIP CRC and exact 35-entry inventory;
- inner `SHA256SUMS.json` complete closure;
- `PACKAGE_REQUIREMENTS.json` closure and SHA parity;
- JSON parse;
- Python compile;
- Windows script encoding contract;
- PowerShell smart-quote contract.

## Fresh release qualification rerun

The recovered exact frozen bytes were extracted and validated again.

Successful full release-mode pre-send executions observed: **5**.

Each successful run included PASS for:

- package closure / SHA manifest;
- dirty-overlay isolation;
- harness regression;
- deployment self-test;
- fault injection;
- routing contracts;
- success-first/max-evidence policy;
- cumulative handoff simulations;
- pre-send policy parity;
- `SKIP_COUNT=0`.

Host-runtime-mode validator rerun: PASS.

Direct deployment self-test rerun:

```text
cycle 1 = PASS 34/34
cycle 2 = PASS 34/34
cycle 3 = PASS 34/34
cycle 4 = PASS 34/34
cycle 5 = PASS 34/34
```

Direct startup-hardening, provider-role-degradation, harness regression and 21 routing tests: PASS.

## Negative-control observation

A direct routing test was once executed outside the sealed runner without bytecode suppression and created:

`payload/noemaforge/src/__pycache__/night_watch_routing_runtime.cpython-313.pyc`

The immediately following pre-send rejected that dirty extraction via:

`no_build_bytecode_artifacts=FAIL`

All other checks remained PASS, and the frozen ZIP hashes were unchanged.

A clean re-extraction with the tree made read-only returned PASS again. This is a successful negative control for self-pollution detection.

## Remaining proof

The remaining operator step is to run this exact frozen outer archive on the real Windows host and return the generated installer/preflight/run evidence.

The current package invokes `powershell.exe`; modern Windows normally supplies Windows PowerShell 5.1 under that command. If the desired runtime is explicitly `pwsh.exe` / PowerShell 7, that requires a new build identity rather than altering this frozen artifact.

After the target-host evidence is bound to the exact outer SHA, independent exact-SHA review / CodeRabbit and human release GO remain separate promotion gates.
