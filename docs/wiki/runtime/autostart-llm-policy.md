# Release Notes — NoemaForge 0.31.03

This release converts the live-tested fixes into a policy release.

Boot policy:

```text
gui mode:
  NoemaForge UI/dashboard/runtime start allowed
  ToolProxy allowed
  CPU bootstrap LLM optional
  heavy LLM disabled -> manual

wogui mode:
  CPU bootstrap LLM allowed
  heavy LLM only explicit/manual
```

Key commands:

```bash
sudo noemaforge boot-mode status
sudo noemaforge autostart-safe --mode gui --dry-run --json
sudo noemaforge autostart-safe --mode gui --llm-profile runtime_only
sudo noemaforge autostart-safe --mode gui --llm-profile bootstrap_cpu_llm
sudo noemaforge safe-start --llm-profile runtime_only --wait
sudo noemaforge safe-start --llm-profile bootstrap_cpu_llm --wait
sudo noemaforge safe-start --llm-profile heavy_manual --restart --wait
```

`heavy_manual` remains an explicit operator action and is never selected by boot autostart.
