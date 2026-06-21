#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/service_manager.py
Zone: runtime/platform
Version: tracks the VERSION source of truth (noemaforge_version.RUNTIME_VERSION)
Purpose: Cross-platform service-manager abstraction (0.33.1 system-independence
         foundation). Thin wrapper so callers do not call systemctl directly:
         - Linux + systemd: delegates to systemctl.
         - All other platforms (macOS, Windows, Linux without systemd): returns
           SERVICE_MANAGER_UNAVAILABLE / empty results without crashing so that
           dev-host tests and future platform ports do not break.
Inputs: sys.platform, subprocess (stdlib only).
Outputs: int return codes and text output from the underlying tool.
Side effects: May invoke systemctl as a subprocess on Linux.
Tests: noemaforge/tests/test_service_manager.py
Notes: Code comments are English-only. stdlib only — no new runtime deps.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import subprocess
import sys
from typing import List, Tuple

SERVICE_MANAGER_UNAVAILABLE = 127  # POSIX convention: command not found

_cached_available: bool | None = None


def available() -> bool:
    """Return True if systemctl is reachable on this host."""
    global _cached_available
    if _cached_available is not None:
        return _cached_available
    if sys.platform != "linux":
        _cached_available = False
        return False
    try:
        rc = subprocess.call(
            ["systemctl", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _cached_available = rc == 0
    except (OSError, FileNotFoundError):
        _cached_available = False
    return _cached_available


def call(*args: str) -> int:
    """Run ``systemctl <args>``; suppress output.

    Returns the exit code, or SERVICE_MANAGER_UNAVAILABLE (127) when
    systemctl is not available on this host.
    """
    if not available():
        return SERVICE_MANAGER_UNAVAILABLE
    try:
        return subprocess.call(
            ["systemctl", *args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return SERVICE_MANAGER_UNAVAILABLE


def check_output(args: List[str]) -> Tuple[int, str]:
    """Run ``systemctl <args>`` and capture combined stdout+stderr.

    Returns ``(exit_code, output_text)``.  When systemctl is unavailable,
    returns ``(SERVICE_MANAGER_UNAVAILABLE, "service_manager_not_available")``.
    """
    if not available():
        return SERVICE_MANAGER_UNAVAILABLE, "service_manager_not_available"
    try:
        out = subprocess.check_output(["systemctl"] + args, stderr=subprocess.STDOUT)
        return 0, out.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as exc:
        return int(exc.returncode), (exc.output or b"").decode("utf-8", errors="replace")
    except Exception as exc:
        return 1, repr(exc)
