# Self-improvement architecture: test cases + telemetry + regression gates

NoemaForge self-improvement is measured before it is trusted.

## Runtime components

- `noemaforge/src/selftest_runtime.py` — test runner, telemetry collector, baseline comparator and wiki patch generator.
- `noemaforge/configs/selftest-case-catalog.json` — executable test case catalog.
- `noemaforge/configs/module-test-matrix.json` — per-module coverage matrix.
- `noemaforge/configs/selftest-telemetry-policy.json` — regression thresholds and rollback policy.
- `selftest_registry.sqlite` — durable log of runs, case results, samples, regressions and wiki patch manifests.

## Commands

```bash
noemaforge selftest catalog --json
noemaforge selftest run --suite core --json
noemaforge selftest run --suite module_compile --json
noemaforge selftest run --suite core --baseline accepted/selftest-report.json --fail-on-regression
noemaforge selftest metrics --report runs/current/selftest-report.json --format prometheus
noemaforge wiki-patch create --report runs/current/selftest-report.json --summary 'what changed' --task 'operator task'
```

## Safety invariants

- Default suites do not start heavy LLMs.
- Live system/GPU/LLM checks require explicit `--allow-live` or dedicated target-machine playbooks.
- GPU/ECC telemetry requires `--gpu` or `NOEMAFORGE_SELFTEST_ENABLE_GPU=1`.
- Regression gates do not auto-apply fixes; they produce evidence for admin approval.

## Canonical flow

```text
change proposal
→ module/test gap scan
→ selftest run
→ baseline compare
→ regression gate
→ wiki incremental patch
→ admin review
→ accept / rollback / create optimization task
```
