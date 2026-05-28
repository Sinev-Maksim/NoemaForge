# Testbench and regression metrics

## Per-case metrics

- `duration_ms`
- `returncode`
- `timeout_hit`
- `resource.utime_s`
- `resource.stime_s`
- `resource.maxrss_kib`
- `resource.inblock`
- `resource.oublock`
- `resource.nvcsw`
- `resource.nivcsw`

## System samples

- CPU count;
- load average;
- memory and swap availability;
- disk free/total;
- optional GPU utilization/VRAM/ECC from `nvidia-smi`.

## Regression gate

Default thresholds:

- any new failed case blocks;
- runtime regression >25% warns/blocks depending on command;
- memory regression >25% warns/blocks depending on command;
- live-suite absence warns in sandbox but blocks target-public validation.

## Live Suite Readiness

`live-testbench-suite-readiness-core` keeps the live NoemaForge testbench run open in `blocked_until_target_live_testbench_suite_evidence` until the target records a baseline, operator approval, the live-suite catalog, the exact `noemaforge testbench run --suite live --include-live --json` transcript, per-case telemetry artifacts, baseline comparison, wiki patch manifest and archive hash.

The local validator is an evidence-shape gate. It proves that the required artifacts and documentation trace exist, but it does not run the live suite, probe GPU or ECC state, create wiki patches or archive target logs.
