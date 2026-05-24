# Evaluation, Observability, and Team Metrics

## Measurement contour

NoemaForge should measure four layers:

1. Model/task quality.
2. Runtime performance and cost.
3. Safety, trust, and reliability.
4. UX/business/team delivery value.

## Code and agent quality metrics

| Metric | Use |
|---|---|
| `pass@k` | Functional correctness for generated solutions |
| Unit test pass rate | Required CI correctness gate |
| Compilation success rate | Build viability |
| Static analysis issue rate | Security/maintainability regression detection |
| CodeBLEU-like metrics | Secondary similarity metric for translation/refactor tasks |

Absolute thresholds should be avoided where the task/domain changes. Prefer baseline-delta gates plus human calibration on critical scenarios.

## Runtime metrics

Track at minimum:

- latency distributions;
- token throughput;
- queue depth;
- GPU/CPU/RAM/VRAM usage;
- error rate;
- timeout rate;
- retry rate;
- cost per successful task;
- model load/unload time.

Use histograms rather than averages for latency.

## Safety and reliability metrics

Track:

- refusal/allow decision consistency;
- policy violation rate;
- tool denial rate;
- rollback success rate;
- provenance completeness;
- eval contamination risk;
- human override rate;
- hidden gate failure rate.

## UX and team metrics

Track:

- task success rate;
- time-to-first-useful-output;
- correction cycles per artifact;
- adoption/retention for shell features;
- DORA-style deployment frequency and change failure rate;
- flow metrics for issue-to-release cycle.

## Dashboard recommendation

Minimum dashboard groups:

- Release health.
- Role staffing quality.
- Model/runtime cost.
- Safety gates.
- Artifact throughput.
- User-visible recovery status.
