#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/runtime/selector.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Select safe runtime profiles from OS and hardware facts.
Inputs: Runtime policy, OS probe facts and hardware probe facts.
Outputs: JSON-compatible candidate and selection records.
Side effects: None.
Tests: noemaforge/tests/test_multios_runtime_contract.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import RuntimeProfile
from .registry import iter_profiles


def _candidate_for(profile: RuntimeProfile, host_os: str) -> Dict[str, Any]:
    exact = profile.host_os == host_os
    remote = profile.host_os == "remote"
    eligible = exact or remote
    blocked_reasons: List[str] = []
    if not eligible:
        blocked_reasons.append("host_os_mismatch")
    if profile.host_os in {"windows", "macos"} and profile.allow_heavy_local_inference:
        blocked_reasons.append("heavy_local_inference_not_allowed_by_default")
    if profile.host_os == "remote" and profile.enabled:
        blocked_reasons.append("remote_runtime_must_be_explicit")
    return {
        "id": profile.id,
        "host_os": profile.host_os,
        "role": profile.role,
        "connector": profile.connector,
        "enabled": profile.enabled,
        "optional": profile.optional,
        "required_for_first_start": profile.required_for_first_start,
        "allow_heavy_local_inference": profile.allow_heavy_local_inference,
        "eligible": eligible and not blocked_reasons,
        "blocked_reasons": blocked_reasons,
    }


def detect_runtime_candidates(
    policy: Dict[str, Any],
    *,
    host_os_report: Dict[str, Any],
    hardware_report: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    host_os = str(host_os_report.get("system") or "unknown")
    candidates = [_candidate_for(profile, host_os) for profile in iter_profiles(policy)]
    for candidate in candidates:
        candidate["hardware_class"] = str((hardware_report or {}).get("memory_class") or "unknown")
    return candidates


def select_runtime_profile(
    policy: Dict[str, Any],
    *,
    host_os_report: Dict[str, Any],
    hardware_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    candidates = detect_runtime_candidates(policy, host_os_report=host_os_report, hardware_report=hardware_report)
    enabled_exact = [
        candidate for candidate in candidates
        if candidate["eligible"] and candidate["enabled"] and candidate["host_os"] == host_os_report.get("system")
    ]
    if enabled_exact:
        selected = enabled_exact[0]
        return {"ok": True, "selected_profile_id": selected["id"], "mode": "enabled_exact", "candidates": candidates}

    control_profiles = [
        candidate for candidate in candidates
        if candidate["host_os"] == host_os_report.get("system") and candidate["role"] == "control_host"
    ]
    if control_profiles:
        selected = control_profiles[0]
        return {"ok": True, "selected_profile_id": selected["id"], "mode": "control_only", "candidates": candidates}

    return {"ok": False, "selected_profile_id": "", "mode": "no_supported_profile", "candidates": candidates}
