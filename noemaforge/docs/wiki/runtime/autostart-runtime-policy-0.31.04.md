# Autostart runtime policy — 0.31.10

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
