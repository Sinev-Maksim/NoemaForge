#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: gateway/inference_service/health.py
Zone: prelaunch/gateway
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Provide health, readiness and metrics payloads for the gateway inference service skeleton.
Inputs: In-memory model state and counters.
Outputs: JSON-compatible endpoint payloads.
Side effects: None.
Tests: noemaforge/tests/test_gateway_inference_service_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def health() -> Dict[str, Any]:
    return {"ok": True, "service": "gateway-inference-service", "status": "healthy"}


def ready(model_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    loaded = bool(model_state and model_state.get("source") == "signed_manifest")
    return {"ok": loaded, "service": "gateway-inference-service", "model_loaded": loaded}


def metrics(counters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    values = counters or {}
    return {
        "gateway_inference_requests_total": int(values.get("requests_total", 0)),
        "gateway_inference_manifest_loads_total": int(values.get("manifest_loads_total", 0)),
        "gateway_inference_fallbacks_total": int(values.get("fallbacks_total", 0)),
    }
