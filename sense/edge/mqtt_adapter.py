#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: sense/edge/mqtt_adapter.py
Zone: prelaunch/sense
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Normalize offline MQTT sensor payloads into the Sense Layer Edge metric schema.
Inputs: MQTT topic and JSON/dict payloads.
Outputs: JSON-compatible normalized metric dictionaries.
Side effects: None; this module does not open network connections.
Tests: noemaforge/tests/test_sense_layer_edge_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
from typing import Any, Dict

from .metrics_schema import normalize_metric


def normalize_mqtt_message(topic: str, payload: Dict[str, Any] | str | bytes, *, source_id: str, source_trust: str) -> Dict[str, Any]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    data = json.loads(payload) if isinstance(payload, str) else dict(payload)
    metric = normalize_metric(data, protocol="mqtt", source_id=source_id, source_trust=source_trust)
    metric["topic"] = topic
    return metric
