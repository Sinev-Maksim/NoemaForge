# GUI live reboot stabilization — 0.31.10

0.31.10 promotes the legacy live-validation host live reboot fixes into package code.

Key lessons:

- Do not repeat `gui-rescue` when Secure Boot rejects NVIDIA modules; diagnose MOK/signing first.
- ToolProxy startup must not fail because SEL files are root-owned or append-only.
- GUI autostart must default to `runtime_only` and must not start or preserve stale LLM processes.
- Help flags must never trigger rescue actions.

