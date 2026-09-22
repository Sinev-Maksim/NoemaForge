# Night Watch Current Status

**As of:** 2026-09-22  
**Classification:** `UAT request findings resolution`  
**Development branch:** `night-watch`  
**Canonical exact NoemaForge base:** `a3c172f5d60113876f0c103010de411fc30b8c38`  
**Checkpoint state:** `unstable, saved for context`

## Release / target-host status

```text
OUTER_ZIP_SHA256=6adbcabac444c393cb40b7f4cb495b6a78d410c2adefe2ce81cbd74aad3dbd5d
INNER_ZIP_SHA256=16e11736e5241e310b56f84acdd3a71e1d95b9a27f3a29d9ee26f221b45e371c

LOCAL_FROZEN_RELEASE_QUALIFICATION=PASS
BYTE_LEVEL_RECHECK=PASS
REAL_TARGET_HOST_INNER_RELEASE_RUN=PASS
TARGET_HOST_PREFLIGHT=PASS
TARGET_HOST_PRE_SEND=PASS
TARGET_HOST_SKIP_COUNT=0
```

The real Windows run used Windows PowerShell `5.1.26100.9444` on `Microsoft Windows NT 10.0.26100.0`.
Installer deployment PASS and reported the exact frozen inner sealed-release SHA above.
Native AST, package closure, Git, Python, UTF-8, evidence storage and target-host pre-send all PASS.

The target log set does not itself record the outer installer-envelope SHA, so the target-host evidence is self-bound to the exact inner executable payload rather than independently re-proving the outer envelope identity.

Full machine-readable record:
`NIGHT_WATCH_TARGET_HOST_UAT_2026-09-21.json`.

## Real self-heal result

```text
TERMINAL_REASON=IMPLEMENTATION_COMPLETE_INDEPENDENT_REVIEW_PENDING
IMPLEMENTATION=PASS
MAIN_UAT_COMPLETE=False
PRODUCT_REPAIR_ATTEMPTS_CHARGED=5
INFRASTRUCTURE_RECOVERY_ATTEMPTS=3
FINAL_CANDIDATE_PATCH_SHA256=38882b33058de4f2ce3b16bdcbe293b8bf6c8c541090882c2a4e3b54fd59a020
LOCAL_DETERMINISTIC_GATES=PASS
LOCAL_COCHECK_STATUS=PASS
REMOTE_INDEPENDENT_REVIEW_REQUIRED=True
CODERABBIT_REQUIRED=True
ACCEPTANCE=PENDING
ACCEPTANCE_REASON=DISTINCT_PROVIDER_UNAVAILABLE
NEXT_TYPED_GATE=WAIT_FOR_DISTINCT_INDEPENDENT_REVIEW_PROVIDER
```

Codex CLI was usable. Claude CLI failed its transport process, so no distinct local independent reviewer was available.

The live run also proved immutable-test enforcement: attempts to propose a change under `noemaforge/tests/**` were rejected by the control plane, retried, and did not bypass the test-read-only boundary.

## Uploaded history archive

The uploaded `history.zip` is internally hash-consistent: all 621 blob objects match their SHA-256 filenames.

It is not the current v3.8.5 handoff:

- `HISTORY.json generated_at=2026-08-15T15:42:02.393214+00:00`;
- 6 historical runs only;
- no 2026-09-21 v3.8.5 run;
- no final candidate SHA `38882b...a020`.

## Durability gap

Canonical target-host evidence/status is now in GitHub, but the final candidate patch bytes are not present in the uploaded files.

To satisfy the no-lost-work rule, recover the current `NoemaForge-NightWatch-handoff.zip` (or the current run directory containing `candidate-6.patch` / final report) and checkpoint the exact candidate to `night-watch` as `unstable, saved for context`.

## Promotion boundary

```text
TARGET_HOST_GATE=PASS
SELF_HEAL_IMPLEMENTATION=PASS
CODE_CHECKPOINT_REMOTE_PERSISTENCE=PENDING_ARTIFACT_RECOVERY
REMOTE_EXACT_CANDIDATE_REVIEW=PENDING
CODERABBIT_FINAL_GATE=PENDING
HUMAN_RELEASE_GO=NOT_GRANTED
RELEASE_PROMOTION=NOT_AUTHORIZED
```
