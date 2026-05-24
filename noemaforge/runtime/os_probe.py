#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/runtime/os_probe.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Detect host OS identity without enabling platform-specific launchers.
Inputs: Optional injected platform facts or the local platform module.
Outputs: JSON-compatible host OS facts.
Side effects: None.
Tests: noemaforge/tests/test_multios_runtime_contract.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import platform
import shutil
from typing import Any, Dict, Optional


def _normalize_system(system: str) -> str:
    text = str(system or "").strip().lower()
    if text in {"linux", "gnu/linux"}:
        return "linux"
    if text in {"windows", "win32", "cygwin", "msys"}:
        return "windows"
    if text in {"darwin", "macos", "mac", "osx"}:
        return "macos"
    if text.startswith("linux"):
        return "linux"
    if text.startswith("win"):
        return "windows"
    return "unknown"


def detect_os(
    *,
    system: Optional[str] = None,
    release: Optional[str] = None,
    machine: Optional[str] = None,
) -> Dict[str, Any]:
    raw_system = system if system is not None else platform.system()
    raw_release = release if release is not None else platform.release()
    raw_machine = machine if machine is not None else platform.machine()
    normalized = _normalize_system(raw_system)
    return {
        "system": normalized,
        "raw_system": str(raw_system or ""),
        "release": str(raw_release or ""),
        "machine": str(raw_machine or ""),
        "host_role": "reference_runtime" if normalized == "linux" else "control_host",
        "is_reference_runtime": normalized == "linux",
        "control_only_by_default": normalized in {"windows", "macos"},
        "supported": normalized in {"linux", "windows", "macos"},
    }


def has_command(command: str, *, path_env: Optional[str] = None) -> bool:
    if not str(command or "").strip():
        return False
    if path_env is None:
        return shutil.which(command) is not None
    search_paths = [item for item in str(path_env).split(os.pathsep) if item]
    return shutil.which(command, path=os.pathsep.join(search_paths)) is not None
