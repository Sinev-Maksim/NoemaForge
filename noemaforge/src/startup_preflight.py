#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/startup_preflight.py
Zone: runtime/safety
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: Pre-start safety gates for NoemaForge heavy jobs: storage, display/GDM, and journald checks.
Inputs: System paths, service names, environment.
Outputs: CheckResult dataclass and PreflightSuite.run() dict report.
Side effects: Read-only; no writes; subprocess calls to df/systemctl/journalctl.
Tests: python3 -m unittest noemaforge/tests/test_startup_preflight.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from noemaforge_version import RUNTIME_VERSION
from platform_paths import DEFAULT_PATHS as _platform_paths, PLATFORM_LINUX


# ---------------------------------------------------------------------------
# Platform helper
# ---------------------------------------------------------------------------

def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _existing_probe_path(path: Path) -> Path:
    probe = Path(path)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return probe


def _default_first_start_storage_paths() -> List[str]:
    if _platform_paths.platform == PLATFORM_LINUX:
        return ["/", str(_platform_paths.share_dir).replace("\\", "/")]
    return [str(_existing_probe_path(_platform_paths.data_root))]


# ---------------------------------------------------------------------------
# CheckResult
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    """Result of a single preflight check."""

    name: str
    passed: bool
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "details": self.details}


# ---------------------------------------------------------------------------
# StorageCheck
# ---------------------------------------------------------------------------

class StorageCheck:
    """Verify that each given path has at least *min_free_gb* GB free."""

    def __init__(self, *, min_free_gb: float = 10.0, paths: Optional[List[str]] = None) -> None:
        self.min_free_gb = min_free_gb
        self.paths = paths or ["/"]

    def run(self) -> CheckResult:
        min_bytes = self.min_free_gb * 1024 ** 3
        low: List[str] = []
        errors: List[str] = []
        details_parts: List[str] = []
        for path in self.paths:
            try:
                usage = shutil.disk_usage(path)
                free_gb = usage.free / 1024 ** 3
                details_parts.append(f"{path}: {free_gb:.1f} GB free")
                if usage.free < min_bytes:
                    low.append(f"{path} ({free_gb:.1f} GB < {self.min_free_gb} GB required)")
            except OSError as exc:
                errors.append(f"{path}: error — {exc}")
        details = "; ".join(details_parts + errors)
        if errors or low:
            msg = "; ".join(errors + [f"low space: {low_item}" for low_item in low])
            return CheckResult(name="storage", passed=False, details=msg)
        return CheckResult(name="storage", passed=True, details=details or "ok")


# ---------------------------------------------------------------------------
# DisplayCheck
# ---------------------------------------------------------------------------

class DisplayCheck:
    """Verify that the display manager service (GDM/GDM3) is active via systemctl."""

    def __init__(self, *, manager: str = "gdm") -> None:
        self.manager = manager

    def run(self) -> CheckResult:
        if not _is_linux():
            return CheckResult(
                name="display",
                passed=True,
                details=f"not applicable (non-Linux); {self.manager} check skipped",
            )
        try:
            result = subprocess.run(
                ["systemctl", "is-active", f"{self.manager}.service"],
                capture_output=True, text=True, timeout=10,
            )
            active = result.stdout.strip()
            if result.returncode == 0 and active == "active":
                return CheckResult(
                    name="display",
                    passed=True,
                    details=f"{self.manager} is active",
                )
            return CheckResult(
                name="display",
                passed=False,
                details=f"{self.manager} is not active (status={active!r}, rc={result.returncode})",
            )
        except Exception as exc:
            return CheckResult(
                name="display",
                passed=False,
                details=f"{self.manager} check failed: {exc}",
            )


# ---------------------------------------------------------------------------
# JournaldCheck
# ---------------------------------------------------------------------------

class JournaldCheck:
    """Check journald error count via journalctl.

    A high error count suggests the system is under stress.  This check is
    non-fatal (warning only) when journalctl is unavailable.
    """

    def __init__(self, *, max_errors: int = 50, since: str = "1 hour ago") -> None:
        self.max_errors = max_errors
        self.since = since

    def run(self) -> CheckResult:
        if not _is_linux():
            return CheckResult(
                name="journald",
                passed=True,
                details="not applicable (non-Linux)",
            )
        try:
            result = subprocess.run(
                ["journalctl", "--since", self.since, "-p", "err", "--no-pager", "-q", "--output=cat"],
                capture_output=True, text=True, timeout=15,
            )
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            count = len(lines)
            if count <= self.max_errors:
                return CheckResult(
                    name="journald",
                    passed=True,
                    details=f"{count} error-level journal lines in the last hour (limit {self.max_errors})",
                )
            return CheckResult(
                name="journald",
                passed=False,
                details=f"{count} error-level journal lines > limit {self.max_errors}; review before starting heavy job",
            )
        except Exception as exc:
            # journald unavailable is a warning, not a hard failure.
            return CheckResult(
                name="journald",
                passed=True,
                details=f"warn: journald check skipped — {exc}",
            )


# ---------------------------------------------------------------------------
# PreflightSuite
# ---------------------------------------------------------------------------

@dataclass
class PreflightSuite:
    """Run a collection of preflight checks and aggregate into a report dict."""

    checks: List[Any] = field(default_factory=list)

    def run(self) -> Dict[str, Any]:
        results = [c.run() for c in self.checks]
        all_passed = all(r.passed for r in results)
        return {
            "ok": all_passed,
            "version": RUNTIME_VERSION,
            "checks": [r.to_dict() for r in results],
        }

    @classmethod
    def for_first_start(
        cls,
        *,
        min_storage_gb: float = 10.0,
        storage_paths: Optional[List[str]] = None,
        display_manager: str = "gdm",
        journald_max_errors: int = 50,
    ) -> "PreflightSuite":
        """Factory for the standard first-start preflight suite."""
        return cls(
            checks=[
                StorageCheck(
                    min_free_gb=min_storage_gb,
                    paths=storage_paths if storage_paths is not None else _default_first_start_storage_paths(),
                ),
                DisplayCheck(manager=display_manager),
                JournaldCheck(max_errors=journald_max_errors),
            ]
        )
