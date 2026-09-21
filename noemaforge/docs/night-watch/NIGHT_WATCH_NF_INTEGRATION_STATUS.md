# Night Watch -> NoemaForge Integration Status

**As of:** 2026-09-21  
**Classification:** `UAT request findings resolution`  
**Branch:** `night-watch`

```text
ARCHITECTURE_METHOD=DRAFTED
PUBLIC_AGENT_INSTRUCTIONS=DRAFTED
PRIVATE_OPERATOR_OVERLAY=LOCAL_ONLY
FIRST_SLICE_MODULE_NAMES=SELECTED
CODE_INTEGRATION=NOT_STARTED
MUTATION_AUTHORITY=DISABLED
```

## Prepared

- seamless migration method: shadow -> proposal -> bounded execution -> native;
- NF single-writer / Night Watch observer-advisor rule;
- canonical `noemaforge.evolution-execution/v1` mapping;
- SSK2 engineering instructions;
- public/private context separation;
- first-slice file/module layout;
- disagreement classes;
- external state/evidence layout;
- phase promotion gates.

## Next implementation slice

Implement only:

1. `night-watch-integration-policy.json` with `off|observe|shadow|proposal`;
2. `evolution_adapters/night_watch_integration.py`;
3. canonical `EvolutionWorkItem` input validation;
4. read-only adapter invocation;
5. canonical `EvolutionEvent` + `EvolutionAgentResult` output;
6. deterministic integration fingerprint;
7. zero-write/deterministic replay tests;
8. shadow disagreement reporting;
9. external UAT evidence runner.

No mutation, provider invocation, GitHub write, merge, release or deployment authority belongs in this slice.
