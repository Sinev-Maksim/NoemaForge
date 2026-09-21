# Night Watch Current Status

**As of:** 2026-09-21  
**Classification:** `UAT request findings resolution`  
**Development branch:** `night-watch`  
**Canonical exact NoemaForge base:** `a3c172f5d60113876f0c103010de411fc30b8c38`  
**Checkpoint state:** `unstable, saved for context`

## Executive status

The older statement “v3.8.5 freeze/replay is still unfinished” is superseded by later qualification evidence dated 2026-09-16.

The available evidence establishes that the **frozen/build-side v3.8.5 qualification completed successfully**, including immutable inner/outer ZIP checks, repeated pre-send/fault/deployment qualification, and real cumulative handoff replay.

This does **not** yet establish all external trust-boundary gates.

```text
LOCAL_FROZEN_RELEASE_QUALIFICATION=PASS
REAL_CUMULATIVE_HANDOFF_REPLAY=PASS
ROOT_CAUSE_EXTRAPOLATION=PASS

REAL_WINDOWS_TARGET_FINAL_FROZEN_RUN=NOT_CONFIRMED
REMOTE_EXACT_SHA_INDEPENDENT_REVIEW=NOT_CONFIRMED
CODERABBIT_FINAL_GATE=NOT_CONFIRMED
HUMAN_RELEASE_GO=NOT_GRANTED
RELEASE_PROMOTION=NOT_AUTHORIZED
```

## Frozen v3.8.5 identities

```text
OUTER_ZIP_SHA256=6adbcabac444c393cb40b7f4cb495b6a78d410c2adefe2ce81cbd74aad3dbd5d
INNER_ZIP_SHA256=16e11736e5241e310b56f84acdd3a71e1d95b9a27f3a29d9ee26f221b45e371c
CUMULATIVE_HANDOFF_SHA256=35070d06fbec7fd8a883ad440b880ebdbf4be731e69d356228e0579811096f79
```

## Qualification evidence

The final release-test matrix records:

- 3 consecutive full pre-send PASS;
- `SKIP_COUNT=0`;
- 5 fault-injection PASS cycles;
- 30 priority failure classes;
- 56 scenario checks;
- 96 provider-role permutations;
- 5 deployment-selftest PASS cycles;
- 34 deployment checks per final self-test;
- empty-current acceptance PASS;
- dirty-current acceptance PASS;
- final outer ZIP CRC PASS (7 entries);
- final inner ZIP CRC PASS (35 entries);
- real cumulative handoff replay PASS;
- repeat handoff merge byte-idempotent;
- handoff history advanced 11 -> 12 runs with 1069 objects.

Root-cause extrapolation records 3 stable cycles and 0 unresolved defects in the final cycle.

## Deployment semantics qualified by the evidence

The v3.8.5 installer/release line uses:

```text
immutable sealed inner release
-> sibling staging
-> full SHA verification
-> whole-directory current swap
-> post-swap SHA/closure/launcher verification
-> rollback + quarantine on failure
```

The prior file-by-file active-tree deployment is superseded.

The evidence also records:

- clean/missing/empty `current` as a first-class scenario;
- previous current restoration after post-swap failure;
- correct intentional empty-state restoration when no previous current existed;
- fixed installer log at `logs/NightWatch-last-installer.log`;
- persistent installer shell/visibility;
- failure reporting with stage/type/message/rollback information;
- bounded release qualification to prevent the validator itself from turning sequential subprocess stalls into an availability failure.

## Important evidence limitation

`NightWatch-Agent-Self-Heal_HOST_PRE_SEND_FINAL.json` is a **host-runtime-mode qualification report produced in the Linux build sandbox**. Its own environment note states that native AST parsing is performed on Windows before controller startup.

Therefore it is valid evidence for host-runtime policy/closure logic, but it is **not evidence that the exact final frozen v3.8.5 outer/inner bytes were actually executed on a real Windows PowerShell 5.1 host**.

Older real-Windows logs prove that the Windows pathway existed and exposed earlier defects, but they refer to older v3.5.x/v3.8.x iterations and cannot be substituted for an exact-final-v3.8.5 target run.

## Documentation drift found during recheck

The later `ENGINEERING_SELF_CHECK.md` copy still contains unchecked release-freeze items for:

- final extrapolation cycle;
- 3 consecutive pre-send passes;
- 5 consecutive fault passes;
- dirty-overlay/path/read-only/handoff replay;
- repeat handoff idempotence;
- immutable final ZIP validation.

Those unchecked boxes are stale relative to the later final release evidence listed above. Do not use them to downgrade the already-proven build qualification. The document must be regenerated/synchronized from evidence rather than manually trusted.

## Promotion boundary

v3.8.5 is **locally frozen/build-qualified**, but it remains outside final production promotion until the remaining external gates are evidenced against the exact frozen identities above.

No merge/tag/deploy follows from this document alone.
