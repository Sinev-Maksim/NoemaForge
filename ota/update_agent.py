#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: ota/update_agent.py
Zone: prelaunch/ota
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Provide offline OTA update planning helpers with rollback and health-gate enforcement.
Inputs: OTA update manifest dictionaries.
Outputs: JSON-compatible update plan dictionaries.
Side effects: None; this module never applies host/device updates.
Tests: noemaforge/tests/test_ota_update_layer_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from typing import Any, Dict


def health_gate_passed(manifest: Dict[str, Any]) -> bool:
    gate = manifest.get("health_gate") if isinstance(manifest.get("health_gate"), dict) else {}
    checks = gate.get("checks") if isinstance(gate.get("checks"), list) else []
    return gate.get("required") is True and gate.get("status") == "passed" and all(
        isinstance(item, dict) and item.get("status") == "passed" for item in checks
    )


def rollback_plan(manifest: Dict[str, Any]) -> Dict[str, Any]:
    previous = manifest.get("previous_bundle") if isinstance(manifest.get("previous_bundle"), dict) else {}
    rollback = manifest.get("rollback") if isinstance(manifest.get("rollback"), dict) else {}
    return {
        "ok": rollback.get("enabled") is True and bool(previous.get("id")),
        "action": rollback.get("failure_action") or "rollback_previous_bundle",
        "previous_bundle_id": previous.get("id", ""),
        "previous_version": previous.get("version", ""),
    }


def can_activate(manifest: Dict[str, Any]) -> bool:
    activation = manifest.get("activation") if isinstance(manifest.get("activation"), dict) else {}
    return activation.get("enabled") is True and activation.get("requires_health_gate") is True and health_gate_passed(manifest)


def plan_update(manifest: Dict[str, Any]) -> Dict[str, Any]:
    staged = manifest.get("staged_rollout") if isinstance(manifest.get("staged_rollout"), dict) else {}
    candidate = manifest.get("candidate_bundle") if isinstance(manifest.get("candidate_bundle"), dict) else {}
    return {
        "manifest_id": manifest.get("id", ""),
        "target": manifest.get("target", ""),
        "candidate_bundle_id": candidate.get("id", ""),
        "staged_rollout": staged.get("enabled") is True,
        "stages": staged.get("stages") if isinstance(staged.get("stages"), list) else [],
        "health_gate_passed": health_gate_passed(manifest),
        "activation_allowed": can_activate(manifest),
        "rollback": rollback_plan(manifest),
    }
