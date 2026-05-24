#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/runtime/base.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Provide small JSON-friendly runtime profile and health containers.
Inputs: Runtime profile dictionaries and health checks.
Outputs: RuntimeProfile and RuntimeHealth dictionaries.
Side effects: None.
Tests: noemaforge/tests/test_multios_runtime_contract.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class RuntimeProfile:
    id: str
    host_os: str
    role: str
    connector: str
    enabled: bool
    optional: bool
    required_for_first_start: bool
    allow_heavy_local_inference: bool
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "RuntimeProfile":
        return cls(
            id=str(payload.get("id") or ""),
            host_os=str(payload.get("host_os") or ""),
            role=str(payload.get("role") or ""),
            connector=str(payload.get("connector") or ""),
            enabled=payload.get("enabled") is True,
            optional=payload.get("optional") is True,
            required_for_first_start=payload.get("required_for_first_start") is True,
            allow_heavy_local_inference=payload.get("allow_heavy_local_inference") is True,
            metadata={key: value for key, value in payload.items() if key not in {
                "id",
                "host_os",
                "role",
                "connector",
                "enabled",
                "optional",
                "required_for_first_start",
                "allow_heavy_local_inference",
            }},
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "id": self.id,
            "host_os": self.host_os,
            "role": self.role,
            "connector": self.connector,
            "enabled": self.enabled,
            "optional": self.optional,
            "required_for_first_start": self.required_for_first_start,
            "allow_heavy_local_inference": self.allow_heavy_local_inference,
        }
        payload.update(self.metadata)
        return payload


@dataclass(frozen=True)
class RuntimeHealth:
    profile_id: str
    ok: bool
    status: str
    mode: str
    checks: List[Dict[str, Any]] = field(default_factory=list)
    endpoint: str = ""
    observed_at: str = field(default_factory=now_utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "ok": self.ok,
            "status": self.status,
            "mode": self.mode,
            "endpoint": self.endpoint,
            "observed_at": self.observed_at,
            "checks": list(self.checks),
        }
