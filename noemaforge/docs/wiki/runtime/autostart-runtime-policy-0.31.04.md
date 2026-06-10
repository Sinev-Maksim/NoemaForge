# Autostart runtime policy — 0.31.10

> **Status: historical snapshot (0.31.04 era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

```text
gui mode:
  runtime/toolproxy allowed
  CPU bootstrap LLM optional
  heavy LLM manual-only
  default: runtime_only

wogui mode:
  CPU bootstrap LLM allowed
  heavy LLM manual-only
  default: bootstrap_cpu_llm
```

`runtime_only` enforces no active main backend by default. Use `--preserve-existing-llm` only for explicit operator exceptions.
