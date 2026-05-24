#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/runtime/connectors/remote_http.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Represent the optional remote HTTP runtime connector without live network I/O.
Inputs: Runtime profile and optional precomputed health payload.
Outputs: JSON-compatible runtime health report.
Side effects: None.
Tests: noemaforge/tests/test_multios_runtime_contract.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..base import RuntimeProfile
from ..registry import build_health_report


class RemoteHTTPRuntimeConnector:
    def __init__(self, profile: RuntimeProfile, *, endpoint: str = "") -> None:
        self.profile = profile
        self.endpoint = endpoint

    def health(self, *, observed: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if observed is not None:
            checks = observed.get("checks") if isinstance(observed.get("checks"), list) else []
            return build_health_report(
                self.profile,
                ok=observed.get("ok") is True,
                status=str(observed.get("status") or "observed"),
                mode="offline_observed",
                checks=checks,
                endpoint=str(observed.get("endpoint") or self.endpoint),
            )
        return build_health_report(
            self.profile,
            ok=False,
            status="disabled_by_default",
            mode="offline_contract",
            endpoint=self.endpoint,
            checks=[
                {"id": "network_io", "status": "skipped", "reason": "connector_is_optional_and_disabled_by_default"},
                {"id": "health_report_contract", "status": "required"},
            ],
        )
