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

## Candidate recovery and review

The current cumulative handoff has been recovered and integrity-verified:

```text
HANDOFF_SHA256=ef5ca29f1a7fb92cfca46cad2706267791788f98e99aec0a87332ebd7e55af80
OBJECTS_NWPACK_SHA256=c7033cd6234b14197e4780673360e0a81237149b28404515f2613cb4ca95a46d
CONTENT_ADDRESSED_OBJECTS=1196
RUN_COUNT=12
ORIGINAL_CANDIDATE_PATCH_SHA256=38882b33058de4f2ce3b16bdcbe293b8bf6c8c541090882c2a4e3b54fd59a020
```

The exact original candidate patch is persisted under:

`docs/night-watch/candidates/CONTINUATION_CANDIDATE_38882b.patch`.

The original candidate's 21 focused routing tests pass, but adversarial review found fail-open/strictness defects. The original candidate verdict is therefore `REQUEST_CHANGES`, not acceptance.

Two extrapolation/review cycles found and corrected nine related defect classes, including:

- unknown-scope CodeRabbit downgrade;
- non-strict provider/persona inputs and raw error leakage;
- contradictory PASS route envelopes;
- forgeable contextual vote eligibility;
- missing self-validation of required Git-helper and independent-persona reviews;
- missing Markdown CodeRabbit-history context;
- open blocker/route code domains;
- scalar/mapping collection coercion in builders.

The corrected WIP is persisted directly in the `night-watch` source tree. The serialized route envelope now carries enough deterministic review context to revalidate its own semantics, while remaining evidence rather than authentication/authority.

Fresh focused/adversarial validation:

```text
ROUTING_UNIT_TESTS=PASS 35/35
PYTHON_SYNTAX_COMPILE=PASS
ROUTING_SCHEMA_JSON_PARSE=PASS
DRAFT_2020_12_PASS_ENVELOPE=PASS
BLOCKED_ROUTE_MATRIX=PASS
ADVERSARIAL_FORGED_PASS_PROBES=REJECTED_AS_EXPECTED
MALFORMED_PUBLIC_INPUTS=TYPED_FAILURES
```

Review evidence:

- `docs/night-watch/reviews/NIGHT_WATCH_INDEPENDENT_REVIEW_38882b.md`;
- `docs/night-watch/reviews/NIGHT_WATCH_CANDIDATE_REVIEW_38882b.json`;
- `docs/night-watch/candidates/NIGHT_WATCH_REVIEW_FIX_38882b_FINAL.manifest.json` plus its four ordered patch parts.

The full review-fix patch reconstructed from those parts has SHA-256:

`afad43c2f4e1a1e8bf4ecddc882cb93ba34db5e868a2dbe4420adc70a389c3cd`.

The external review changes to the routing regression test are canonical review/fix work outside the Night Watch self-heal attempt. They do not weaken the rule that `noemaforge/tests/**` is immutable **inside a self-heal repair run**.

This review/fix iteration does **not** satisfy the separate remote independent acceptance or CodeRabbit gates.

## Promotion boundary

```text
TARGET_HOST_GATE=PASS
ORIGINAL_CANDIDATE_38882b=REQUEST_CHANGES
CORRECTED_WIP_FOCUSED_VALIDATION=PASS_35_OF_35
CORRECTED_WIP_ADVERSARIAL_VALIDATION=PASS
CODE_CHECKPOINT_REMOTE_PERSISTENCE=PASS
FULL_REPOSITORY_REGRESSION=PENDING
REMOTE_EXACT_CANDIDATE_REVIEW=PENDING
CODERABBIT_FINAL_GATE=PENDING
HUMAN_RELEASE_GO=NOT_GRANTED
RELEASE_PROMOTION=NOT_AUTHORIZED
```

No merge/tag/deploy is authorized yet.
