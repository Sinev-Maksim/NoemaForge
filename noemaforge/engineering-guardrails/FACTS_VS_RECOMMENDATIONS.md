# Facts vs recommendations

## Recovered / agreed
The policy entries marked `agreed` or `agreed+clarified` come from the project conversation chain, live UAT evidence, and the established Night Watch workflow.

## Recommended additions from the self-audit
The following are generalized protections inferred from repeated failures:
- versioned external-process invocation contract;
- explicit byte-level UTF-8 requirement;
- non-ASCII transport canary;
- product-attempt charging only after candidate materialization;
- workaround comments require a removal condition;
- every UAT fix must add a prevention guard, not only a patch.

These recommendations do not override an explicit later project decision; they are intended to prevent recurrence of the same failure classes.
