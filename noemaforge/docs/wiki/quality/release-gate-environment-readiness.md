# Release-gate environment readiness

NoemaForge release gates are only meaningful when the local validation environment can run the tools that the gates depend on. A missing Python interpreter, YAML parser, or usable shell should be reported as a blocker before release evidence is interpreted, not silently treated as a passing gate.

The `release-gate-environment-readiness-core` contract records that distinction. It checks for a Python runner for AST and pytest gates, a semantic YAML parser for YAML gates, and a usable bash shell for shell syntax gates. The report is local-only: it uses no network access, starts no hardware probes, and never installs packages. Its purpose is to tell an operator whether the current machine can complete the release gate or whether the gate must move to a prepared validation host.

The readiness preflight is deliberately separate from the gate results. If the preflight reports blockers, the correct result is “verification blocked by missing local tooling,” not “release ready.” This keeps the strict completion rule intact while still giving automation a deterministic next action.

Typical use:

```bash
node helpers/release_gate_environment_readiness.mjs --fail-on-blockers
```

Without `--fail-on-blockers`, the command prints the same JSON report with process success so it can be collected as evidence inside broader diagnostics.

