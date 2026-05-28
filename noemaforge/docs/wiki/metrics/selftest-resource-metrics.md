# Self-test resource metrics

NoemaForge `0.30.22` adds per-case resource telemetry.

## JSON fields

Each `SelfTestReport.results[]` entry contains:

```json
{
  "case_id": "pipeline_validate",
  "status": "pass",
  "metrics": {
    "duration_sec": 0.42,
    "max_rss_kib": 8000,
    "cpu_user_sec": 0.1,
    "cpu_system_sec": 0.02,
    "disk_read_bytes": 0,
    "disk_write_bytes": 0,
    "ecc_delta_total": 0
  }
}
```

## Prometheus export

```bash
noemaforge selftest metrics --report selftest-report.json --format prometheus
```

Exports:

- `noemaforge_selftest_case_duration_seconds`;
- `noemaforge_selftest_case_max_rss_kib`;
- `noemaforge_selftest_case_disk_read_bytes`;
- `noemaforge_selftest_case_disk_write_bytes`;
- `noemaforge_selftest_case_ecc_delta_total` when available;
- `noemaforge_selftest_cases_total`;
- `noemaforge_selftest_cases_failed`.

## ECC policy

ECC is treated as a target-machine/live resource signal. It is sampled through `nvidia-smi` only when GPU probing is enabled.
