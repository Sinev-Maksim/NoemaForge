# NoemaForge 0.31.01 — Pipeline member cells

This release clarifies the development pipeline model.

A pipeline participant is no longer treated as a single hard-coded command. Each participant can be:

- **standalone**: one selected model/persona performs the role;
- **multi-model cell**: two or more producer-distinct models execute sequentially by default under the single active LLM invariant.

The default flow for every member cell is:

```text
member input context
→ sequential model proposal slots
→ proposal log
→ consensus artifacts
→ unique artifacts
→ outgoing artifact consistency gate
→ typed next participant handoff
```

The runtime does not start models by itself. It creates auditable prompts, logs and handoff artifacts compatible with the switchable-LLM lease layer.

## Commands

```bash
noemaforge member validate
noemaforge member team --member qa --producer qwen25-coder-14b --json
noemaforge member run --member developer --project /opt/noemaforge --producer qwen25-coder-14b --json
noemaforge member run --member code_analyser_visualiser --project /opt/noemaforge --json
noemaforge pipeline member run <pipeline_run_id> --stage development --member developer --project /opt/noemaforge --json
noemaforge pipeline member run <pipeline_run_id> --stage code_analyser_visualiser --member code_analyser_visualiser --project /opt/noemaforge --json
```

## Consistency gates

The outgoing artifact gate checks:

- proposal files exist;
- consensus and unique artifact files exist;
- markdown + JSON handoff sidecar exists;
- JSON checksum matches;
- developer produced `auto_tests_report.json`;
- QA/testers do not repeat the same unresolved misunderstanding loop indefinitely;
- code analyzer/visualizer produced Mermaid diagrams and bottleneck reports.

## Code analyzer/visualizer

The `code_analyser_visualiser` member produces:

- `architecture_overview.mmd`;
- `call_graph.mmd`;
- `bottleneck_report.json`;
- `helicopter_view.md`;
- `code_analysis.json` with class/function/call summaries;
- repeated call highlighting from static execution emulation.

The static call emulation is intentionally conservative: it does not pretend to be a profiler. It shows where a function/call appears more than once in a test/static path so QA can decide whether a real benchmark is needed.
