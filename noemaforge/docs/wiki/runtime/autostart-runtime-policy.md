# Autostart runtime policy — 0.31.10

The autostart policy protects boot stability by separating the lightweight runtime from heavy model execution. GUI mode starts only timer-driven runtime and ToolProxy surfaces by default; it does not start a main LLM backend. This keeps the desktop recoverable and prevents a failed model launch from turning into a display outage.

Headless `wogui` mode may allow a CPU bootstrap LLM for first-start assistance, but heavy LLM backends remain manual-only. The default `runtime_only` profile means the operator can inspect status, run preflight checks and choose a model profile before any large backend consumes memory or GPU resources.

`--preserve-existing-llm` is an explicit exception for operators who already know a backend is healthy and want to keep it alive across a controlled operation. It must not become the default path, and release evidence should continue to show that boot, setup and GUI recovery work without hidden heavy-model autostart.
