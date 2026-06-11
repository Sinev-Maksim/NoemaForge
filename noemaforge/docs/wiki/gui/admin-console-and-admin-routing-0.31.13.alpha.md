# NoemaForge 0.32.1 — Admin routing

> **Status: historical snapshot (0.31.13.alpha era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

This build fixes the `создай музыку для приветственного демо NoemaForge` route regression by using boundary-aware greeting detection and domain-priority scoring.

## Route priorities

Strong domain intents outrank greeting:

- model selection / epoch optimization
- code / Dev Team
- music, voice, image, video and masks
- model evolution

Greeting matches require token/exact greeting boundaries, so words such as `приветственного` no longer become the greeting route.

## Dev Team clarification

A code request without project/file context is held by Admin. Admin asks for:

- what to change;
- where the project/file is;
- whether to apply directly or show a patch first.

Only after project visibility is confirmed should Admin hand off to Dev Team.
