#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/runtime/registry.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Load and normalize the JSON-compatible MultiOS runtime policy file.
Inputs: noemaforge/configs/noemaforge.runtime.yaml.
Outputs: RuntimeProfile lists and health reports.
Side effects: None.
Tests: noemaforge/tests/test_multios_runtime_contract.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .base import RuntimeHealth, RuntimeProfile


def load_runtime_policy(path: Path | str) -> Dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def iter_profiles(policy: Dict[str, Any]) -> Iterable[RuntimeProfile]:
    for profile in policy.get("profiles") if isinstance(policy.get("profiles"), list) else []:
        if isinstance(profile, dict):
            yield RuntimeProfile.from_dict(profile)


def profile_by_id(policy: Dict[str, Any], profile_id: str) -> Optional[RuntimeProfile]:
    for profile in iter_profiles(policy):
        if profile.id == profile_id:
            return profile
    return None


def build_health_report(
    profile: RuntimeProfile,
    *,
    ok: bool,
    status: str,
    mode: str,
    checks: List[Dict[str, Any]],
    endpoint: str = "",
) -> Dict[str, Any]:
    return RuntimeHealth(
        profile_id=profile.id,
        ok=ok,
        status=status,
        mode=mode,
        checks=checks,
        endpoint=endpoint,
    ).to_dict()
