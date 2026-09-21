# Night Watch v3.8.5 Evidence Index

**Classification:** `UAT request findings resolution`  
**Evidence reconciliation date:** 2026-09-21

This index records the evidence identities available during the status recheck. It does not replace the original artifacts.

## Release identities

| Artifact identity | SHA-256 |
|---|---|
| frozen outer installer envelope | `6adbcabac444c393cb40b7f4cb495b6a78d410c2adefe2ce81cbd74aad3dbd5d` |
| frozen inner release ZIP | `16e11736e5241e310b56f84acdd3a71e1d95b9a27f3a29d9ee26f221b45e371c` |
| cumulative handoff after replay | `35070d06fbec7fd8a883ad440b880ebdbf4be731e69d356228e0579811096f79` |

## Evidence artifacts observed

- `NightWatch-Agent-Self-Heal_RELEASE_TEST_MATRIX.json`
  - overall PASS;
  - pre-send consecutive passes: 3;
  - skip count: 0;
  - fault passes: 5;
  - 30 priority classes / 56 scenario checks / 96 provider-role permutations;
  - deployment selftest passes: 5 / 34 checks;
  - empty and dirty current: PASS;
  - final outer/inner ZIP CRC: PASS;
  - real cumulative handoff replay: PASS.
- `NightWatch-Agent-Self-Heal_INSTALLER_VALIDATION.json`
  - atomic sibling-stage deployment model;
  - persistent installer shell/log;
  - empty/dirty current PASS;
  - deployment selftest 5 x 34 checks PASS.
- `NightWatch-Agent-Self-Heal_REAL_HANDOFF_REPLAY_v385.json`
  - runs 11 -> 12;
  - 1069 objects;
  - repeat merge idempotent;
  - PASS.
- `NightWatch-Agent-Self-Heal_EXTRAPOLATION_REPORT.json`
  - 3 stable cycles;
  - final unresolved defects: 0;
  - PASS.
- `NightWatch-Agent-Self-Heal_PRE_SEND_FINAL.json`
  - release-mode PASS;
  - skip count 0;
  - no failures;
  - sealed-closure, Windows compatibility/static gates, deployment, fault, routing, handoff and policy-parity checks PASS.
- `NightWatch-Agent-Self-Heal_HOST_PRE_SEND_FINAL.json`
  - host-runtime-mode PASS;
  - produced in Linux build sandbox, therefore not proof of a real exact-final Windows run.
- `NightWatch-Agent-Self-Heal_FAULT_SIMULATION_REPORT.json`
  - 5 passes;
  - 30 / 56 / 96 matrix;
  - PASS.

## Evidence interpretation rule

Machine-readable evidence bound to the frozen release identities supersedes older prose saying freeze/replay was pending.

However build/host-runtime-mode evidence MUST NOT be promoted into a claim of real target-host execution. A real Windows PowerShell 5.1 run must identify the exact final frozen bytes.
