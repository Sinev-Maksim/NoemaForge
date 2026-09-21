# Night Watch v3.8.5 Qualification Checklist

**Reconciled:** 2026-09-21  
**Rule:** machine-readable evidence bound to exact release identity overrides stale manual checkbox state.

## Frozen/build qualification

- [x] root-cause extrapolation cycles >= 3;
- [x] final extrapolation unresolved defects = 0;
- [x] full pre-send >= 3 consecutive PASS;
- [x] mandatory skip count = 0;
- [x] fault-injection >= 5 PASS;
- [x] 30 priority failure classes exercised;
- [x] 56 scenario checks exercised;
- [x] 96 provider-role permutations exercised;
- [x] deployment selftest >= 5 PASS;
- [x] final deployment selftest = 34 checks;
- [x] empty/missing current acceptance PASS;
- [x] dirty current / dirty overlay PASS;
- [x] Windows-like path/Git/encoding static and simulated gates PASS;
- [x] frozen outer ZIP CRC PASS;
- [x] frozen inner ZIP CRC PASS;
- [x] cumulative handoff replay PASS;
- [x] repeat handoff merge idempotent;
- [x] final frozen release identities recorded.

## External trust boundaries

- [ ] exact final frozen v3.8.5 executed on a real Windows PowerShell 5.1 target;
- [ ] resulting real-target evidence bound to exact frozen release identity;
- [ ] remote independent exact-SHA review;
- [ ] CodeRabbit/final external quality gate where required;
- [ ] human release GO;
- [ ] production/tagged promotion.

Until the unchecked external gates are completed, the release may be described as **frozen/build-qualified**, not as fully promoted production release.
