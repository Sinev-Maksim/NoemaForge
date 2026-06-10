# NoemaForge 0.32.1 — Telemetry and Metrics

> **Status: historical snapshot (0.32.1 era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

## Hardware telemetry
CPU/GPU temperature, power, memory, battery/charge, disk and thermal data are surfaced from local tools when available.

## Runtime telemetry
Shows active model, sockets, service state, CPU/GPU device policy and current runtime placement.

## Product metrics
For code/model-selection/evolution: before/after tests, scorecards, role coverage and rollback evidence. For creative media: metadata and review-required status rather than fake objective quality.

## Device policy
CPU/GPU switch is staged. It applies on the next persona/model switch or explicit backend restart; it does not migrate an active model.
