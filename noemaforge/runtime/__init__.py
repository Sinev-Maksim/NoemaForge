#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/runtime/__init__.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Expose the offline MultiOS runtime abstraction package.
Inputs: noemaforge/runtime modules.
Outputs: Importable runtime helpers.
Side effects: None.
Tests: noemaforge/tests/test_multios_runtime_contract.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from .hardware_probe import detect_hardware
from .os_probe import detect_os, has_command
from .selector import detect_runtime_candidates, select_runtime_profile

__all__ = [
    "detect_hardware",
    "detect_os",
    "detect_runtime_candidates",
    "has_command",
    "select_runtime_profile",
]
