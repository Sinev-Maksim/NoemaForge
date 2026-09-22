# Night Watch v3.8.5 Qualification Checklist

**Reconciled:** 2026-09-22  
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

- [x] exact final frozen v3.8.5 inner sealed release executed on a real Windows PowerShell 5.1 target;
- [x] real-target evidence bound to exact frozen inner sealed-release SHA-256;
- [ ] remote independent exact-SHA review;
- [ ] CodeRabbit/final external quality gate where required;
- [ ] human release GO;
- [ ] production/tagged promotion.

The frozen package is now **build-qualified and real-target-host qualified**. It is not a promoted production release until the remaining independent review / external quality / human promotion gates are completed. The target-host logs bind the executable inner sealed-release identity; they do not independently restate the outer installer-envelope SHA.
