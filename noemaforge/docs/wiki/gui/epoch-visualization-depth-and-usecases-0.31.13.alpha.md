# NoemaForge 0.32.1 — Epoch visualization, depth controls and usecase help

> **Status: historical snapshot (0.31.13.alpha era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

## Scope

This patch adds GUI-level operator visibility and control for model-selection epochs and bounded improvement loops.

## Added GUI surfaces

- Epoch / model-selection panel with current main model, staffing state, tested/failed/remaining model counts and latest model-selection plan.
- `Switch to new epoch` button creates an explicit epoch apply request and points the operator to the sudo first-start apply command.
- `Continue model selection` button creates a continuation plan with tested/failed/remaining counts and recommended command.
- `Re-inventory Vault` button calls the inventory scan surface and returns command output or a clear permission warning.
- Improvement depth controls: max steps, time budget in minutes, and until-stop marker.
- Usecase help cards for model selection, model evolution, Dev Team, depth control and continued model selection.

## Safety model

The GUI does not silently run privileged first-start apply. Epoch switching remains review/approve based. The apply button creates a local audited request artifact; actual heavy apply remains explicit.

## Dialog-state fixes

When Admin asks for a model-selection mode and the operator replies `normal`, `fast`, `full`, or `full_composite N`, the GUI treats the reply as the pending mode selection and creates model-selection artifacts instead of asking for the mode again.

## UX fixes

The message input is cleared immediately after send, while the sent message is preserved in the chat history.
