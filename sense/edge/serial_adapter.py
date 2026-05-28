#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: sense/edge/serial_adapter.py
Zone: prelaunch/sense
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Normalize offline serial controller lines into the Sense Layer Edge metric schema.
Inputs: Serial text lines in metric_id=value unit form.
Outputs: JSON-compatible normalized metric dictionaries.
Side effects: None; this module does not open serial devices.
Tests: noemaforge/tests/test_sense_layer_edge_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from typing import Any, Dict

from .metrics_schema import normalize_metric


def parse_serial_line(line: str) -> Dict[str, Any]:
    text = str(line or "").strip()
    if "=" not in text:
        raise ValueError("serial_metric_separator_missing")
    metric_id, rest = text.split("=", 1)
    parts = rest.strip().split()
    if not parts:
        raise ValueError("serial_metric_value_missing")
    value_text = parts[0]
    unit = parts[1] if len(parts) > 1 else "count"
    try:
        value: float | str = float(value_text)
    except ValueError:
        value = value_text
    return {"metric_id": metric_id.strip(), "value": value, "unit": unit}


def normalize_serial_line(line: str, *, source_id: str, source_trust: str) -> Dict[str, Any]:
    return normalize_metric(parse_serial_line(line), protocol="serial", source_id=source_id, source_trust=source_trust)
