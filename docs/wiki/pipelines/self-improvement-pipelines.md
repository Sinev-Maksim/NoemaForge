# Self-improvement pipelines

Packaged in `0.30.22`:

- `self_improvement_test_matrix`
- `telemetry_regression_audit`
- `wiki_incremental_patch_publish`
- `auto_optimization_change_request`
- `module_test_case_authoring`

Each pipeline follows the NoemaForge lifecycle: architecture clarification, development or content production, testing, integration review, optimization attempt and final review.

The recommended operator path:

```bash
noemaforge pipeline run self_improvement_test_matrix --request "measure candidate change"
noemaforge testbench run --suite quick --json
noemaforge testbench baseline compare --baseline baseline.json --candidate summary.json --fail-on-regression
noemaforge wiki-patch create --wiki-repo /path/to/wiki --title "..." --description "..."
```

## Live Suite Evidence Boundary

`live-testbench-suite-readiness-core` records `blocked_until_target_live_testbench_suite_evidence` and the minimum evidence needed before the live self-improvement suite can be treated as complete: target baseline, operator approval, live-suite catalog, the exact `noemaforge testbench run --suite live --include-live --json` transcript, telemetry artifacts, baseline comparison, wiki patch manifest and archive hash.

The local readiness runtime is intentionally non-executing. It validates policy, examples, registry links and documentation coverage while leaving live testbench execution, target resource capture, wiki patch creation and archive collection to the operator-controlled target workflow.
