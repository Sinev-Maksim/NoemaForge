#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: gateway/inference_service/app.py
Zone: prelaunch/gateway
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Expose offline REST/MQTT endpoint metadata for gateway inference service validation.
Inputs: Request path/topic plus signed manifest-backed model state.
Outputs: JSON-compatible endpoint responses.
Side effects: None.
Tests: noemaforge/tests/test_gateway_inference_service_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .health import health, metrics, ready
from .model_loader import load_model


ENDPOINTS = [
    {"kind": "inference", "protocol": "rest", "method": "POST", "path": "/infer"},
    {"kind": "inference", "protocol": "mqtt", "topic": "noemaforge/gateway/infer"},
    {"kind": "health", "protocol": "rest", "method": "GET", "path": "/health"},
    {"kind": "ready", "protocol": "rest", "method": "GET", "path": "/ready"},
    {"kind": "metrics", "protocol": "rest", "method": "GET", "path": "/metrics"},
]


def load_state(manifest_path: Path | str) -> Dict[str, Any]:
    return {"model": load_model(manifest_path=manifest_path), "counters": {"manifest_loads_total": 1}}


def infer(payload: Dict[str, Any], *, model_state: Dict[str, Any]) -> Dict[str, Any]:
    if model_state.get("source") != "signed_manifest":
        return {"ok": False, "route": "fallback_whitebox", "reason": "model_not_manifest_loaded"}
    return {
        "ok": True,
        "route": "shadow_score",
        "model_ref": model_state["model_ref"],
        "output_contract": model_state["output_contract"],
        "input_observed": bool(payload),
    }


def handle_rest(path: str, payload: Optional[Dict[str, Any]] = None, *, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    model_state = (state or {}).get("model") or {}
    counters = (state or {}).get("counters") or {}
    if path == "/health":
        return health()
    if path == "/ready":
        return ready(model_state)
    if path == "/metrics":
        return metrics(counters)
    if path == "/infer":
        return infer(payload or {}, model_state=model_state)
    return {"ok": False, "error": "route_not_found"}


def handle_mqtt(topic: str, payload: Optional[Dict[str, Any]] = None, *, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if topic != "noemaforge/gateway/infer":
        return {"ok": False, "error": "topic_not_found"}
    return infer(payload or {}, model_state=((state or {}).get("model") or {}))
