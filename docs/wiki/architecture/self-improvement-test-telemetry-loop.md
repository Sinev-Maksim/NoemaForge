# Self-improvement test and telemetry loop

NoemaForge self-improvement is a gated loop:

```text
observe → test → measure → compare baseline → propose patch → review → apply/reject → publish wiki patch
```

The loop is designed for switchable LLMs: one active LLM lease at a time, typed context packets for handoff and SQLite/event logs for state. The LLM may propose improvements, but the testbench and operator approval gate decide whether a change proceeds.

## Canonical artifacts

- `cases.jsonl` — per-case telemetry;
- `summary.json` — run summary;
- `report.md` — human-readable result;
- `baseline.json` — accepted prior performance state;
- `metrics_delta.json` — before/after comparison;
- `functional_delta.md` — what changed;
- `patch.diff` — wiki-visible delta;
- `wiki_patch_manifest.json` — provenance.
