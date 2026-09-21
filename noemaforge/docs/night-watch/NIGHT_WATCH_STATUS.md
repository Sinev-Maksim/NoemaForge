# Night Watch Current Status

**As of:** 2026-09-21  
**Classification:** `UAT request findings resolution`  
**Development branch:** `night-watch`  
**Canonical exact NoemaForge base:** `a3c172f5d60113876f0c103010de411fc30b8c38`  
**Checkpoint state:** `unstable, saved for context`

## Executive status

The exact frozen v3.8.5 outer installer archive has now been recovered and byte-verified.

```text
EXACT_FROZEN_ARTIFACT_RECOVERED=PASS
OUTER_ZIP_SHA256=6adbcabac444c393cb40b7f4cb495b6a78d410c2adefe2ce81cbd74aad3dbd5d
INNER_ZIP_SHA256=16e11736e5241e310b56f84acdd3a71e1d95b9a27f3a29d9ee26f221b45e371c

LOCAL_FROZEN_RELEASE_QUALIFICATION=PASS
BYTE_LEVEL_RECHECK=PASS
REAL_CUMULATIVE_HANDOFF_REPLAY=PASS
ROOT_CAUSE_EXTRAPOLATION=PASS

REAL_TARGET_HOST_FINAL_FROZEN_RUN=PENDING_USER_RUN
REMOTE_EXACT_SHA_INDEPENDENT_REVIEW=NOT_CONFIRMED
CODERABBIT_FINAL_GATE=NOT_CONFIRMED
HUMAN_RELEASE_GO=NOT_GRANTED
RELEASE_PROMOTION=NOT_AUTHORIZED
```

## Exact recovered artifact

Recovered library source:

`/ОС_ИИ/NightWatch-Agent-Self-Heal(20260916-194020).zip`

Durable recovered copy:

`/NightWatch-Recovered/NightWatch-Agent-Self-Heal.zip`

Size: `183265` bytes.

The recovered bytes match the previously recorded frozen outer identity exactly.

## Independent byte-level recheck

Independent archive audit on the recovered exact bytes is PASS:

- outer SHA-256 matches the frozen identity;
- outer ZIP CRC PASS, 7 entries;
- no duplicate/casefold/path-traversal/symlink hazards;
- installer-manifest sizes and SHA values all match;
- inner SHA agrees across the actual nested bytes, `SEALED_RELEASE_SHA256.txt`, and `INSTALLER_MANIFEST.json`;
- inner ZIP CRC PASS, 35 entries;
- inner `SHA256SUMS.json` closure PASS: 34 declared files plus the manifest itself;
- `PACKAGE_REQUIREMENTS.json` closure and SHA parity PASS;
- all JSON parses;
- all Python sources compile;
- PowerShell BOM/CRLF contract PASS;
- CMD ASCII/CRLF contract PASS;
- executable PowerShell smart-quote guard PASS.

## Fresh rerun evidence

The recovered exact bytes were clean-extracted and rerun through the release validator.

Successful release-mode full pre-send runs observed against the exact frozen bytes: **5**. Each successful run reported:

- `PRE_SEND_DRY_RUN=PASS`;
- `SKIP_COUNT=0`;
- `deployment_selftest=PASS`;
- `fault_injection_selftest=PASS`;
- `pre_send_policy_parity=PASS`.

Host-runtime-mode validation also reran PASS.

Direct deployment self-test additionally reran **5 / 5 PASS**, with **34 checks** and zero failures each time.

Direct startup-hardening, provider-role-degradation, harness-regression, and the 21 routing-contract tests also PASS.

### Self-pollution guard observation

One ad-hoc direct routing-test invocation was intentionally/notably run outside the sealed runner without `PYTHONDONTWRITEBYTECODE`; it produced one `__pycache__` artifact in that extracted working copy.

The next pre-send correctly failed only `no_build_bytecode_artifacts` while the immutable outer/inner ZIP identities remained unchanged. A fresh clean extraction returned PASS again.

This confirms the pollution guard is live; it is not a frozen-package defect.

## Deployment semantics

The qualified deployment model remains:

```text
immutable sealed inner release
-> sibling staging
-> full SHA verification
-> whole-directory current swap
-> post-swap SHA/closure/launcher verification
-> rollback + quarantine on failure
```

File-by-file mutation of active `current` remains superseded.

## Target-host gate

The only runtime gate now waiting on the operator is execution of **this exact outer SHA** on the real Windows host, preserving installer, host-preflight, and run logs.

The package's current launcher invokes `powershell.exe`. On a modern Windows installation that normally means Windows PowerShell 5.1 even though the operating system itself is current. PowerShell 5.1 was a compatibility floor, not a requirement that the OS be old.

If execution specifically under PowerShell 7 / `pwsh.exe` is desired, that is a source change and must be frozen as a new release identity rather than silently modifying the exact qualified v3.8.5 bytes.

## Promotion boundary

v3.8.5 is **exact-artifact recovered, byte-rechecked, and locally frozen/build-qualified**.

It is not yet a promoted production release until the remaining external gates are evidenced against the exact identity above.

No merge/tag/deploy follows from this document alone.
