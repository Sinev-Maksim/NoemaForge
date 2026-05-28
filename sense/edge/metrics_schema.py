#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: sense/edge/metrics_schema.py
Zone: prelaunch/sense
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Normalize edge sensor and system metrics into one explicit trust schema.
Inputs: Adapter payload dictionaries.
Outputs: JSON-compatible normalized metric dictionaries.
Side effects: None.
Tests: noemaforge/tests/test_sense_layer_edge_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


REQUIRED_FIELDS = ["metric_id", "source_id", "source_trust", "timestamp", "value", "unit"]
TRUST_LEVELS = {"trusted", "simulated", "unverified"}
PROTOCOLS = {"mqtt", "serial", "system_metrics"}


def nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_metric(payload: Dict[str, Any], *, protocol: str, source_id: str, source_trust: str) -> Dict[str, Any]:
    if protocol not in PROTOCOLS:
        raise ValueError("protocol_not_allowed")
    if source_trust not in TRUST_LEVELS:
        raise ValueError("source_trust_not_allowed")
    metric = {
        "metric_id": str(payload.get("metric_id") or payload.get("metric") or "").strip(),
        "source_id": source_id,
        "source_trust": source_trust,
        "timestamp": str(payload.get("timestamp") or nowz()),
        "value": payload.get("value"),
        "unit": str(payload.get("unit") or "").strip(),
        "protocol": protocol,
    }
    missing = [field for field in REQUIRED_FIELDS if metric.get(field) in ("", None)]
    if missing:
        raise ValueError(f"metric_missing_fields:{','.join(missing)}")
    return metric
