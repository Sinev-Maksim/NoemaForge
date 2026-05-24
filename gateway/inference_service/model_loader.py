#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: gateway/inference_service/model_loader.py
Zone: prelaunch/gateway
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Load gateway inference model metadata only from a signed model manifest.
Inputs: SignedModelManifest JSON files.
Outputs: JSON-compatible model handle metadata.
Side effects: None.
Tests: noemaforge/tests/test_gateway_inference_service_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def _load_manifest(manifest_path: Path | str) -> Dict[str, Any]:
    path = Path(manifest_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("kind") != "SignedModelManifest":
        raise ValueError("signed_model_manifest_required")
    if not str(payload.get("sha256") or "").strip():
        raise ValueError("manifest_sha256_required")
    if not str(payload.get("signature") or "").strip():
        raise ValueError("manifest_signature_required")
    if not str(payload.get("artifact_uri") or "").strip():
        raise ValueError("manifest_artifact_uri_required")
    return payload


def load_model_from_manifest(manifest_path: Path | str) -> Dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    return {
        "source": "signed_manifest",
        "manifest_id": manifest["id"],
        "model_ref": manifest["model_ref"],
        "artifact_uri": manifest["artifact_uri"],
        "sha256": manifest["sha256"],
        "runtime": manifest["runtime"],
        "input_contract": manifest["input_contract"],
        "output_contract": manifest["output_contract"],
        "fallback": manifest["fallback"],
    }


def load_model(*, manifest_path: Optional[Path | str] = None, model_path: Optional[Path | str] = None) -> Dict[str, Any]:
    if model_path is not None:
        raise ValueError("direct_model_path_forbidden")
    if manifest_path is None:
        raise ValueError("manifest_path_required")
    return load_model_from_manifest(manifest_path)
