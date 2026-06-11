# NoemaForge 0.31.01 — full first-start UI validation

> **Status: historical snapshot (0.31.01 era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).


The live machine test should validate NoemaForge through the real first-start/UI path, not only through manual `noemaforge-llama@main.service` start/stop.

## GUI mode

Expected order:

```text
boot
→ display-manager/GDM/GNOME ready
→ NoemaForge conditional safe-start
→ dashboard available
→ first pipeline/UI smoke
→ optional LLM smoke after operator approval
```

## woGUI mode

Expected order:

```text
boot
→ multi-user.target
→ NoemaForge conditional safe-start instead of GUI
→ dashboard/CLI reachable from TTY or remote shell
→ optional LLM smoke after operator approval
```

## Safety invariant

Heavy LLM autostart is still forbidden. Conditional safe-start may prepare runtime services, but it must not blindly start the heavy model before GUI readiness in GUI mode.

## Operator test

Use `docs/USER_TEST_CASE_0.31.01.md` as the live checklist.
