#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/runtime/hardware_probe.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Provide dependency-free hardware classification for runtime selection.
Inputs: Optional injected machine, processor, memory and GPU facts.
Outputs: JSON-compatible hardware facts.
Side effects: None.
Tests: noemaforge/tests/test_multios_runtime_contract.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import platform
from typing import Any, Dict, Optional


def _normalize_arch(machine: str, processor: str) -> str:
    text = f"{machine} {processor}".strip().lower()
    if any(token in text for token in ["arm64", "aarch64"]):
        return "arm64"
    if any(token in text for token in ["x86_64", "amd64", "x64"]):
        return "x86_64"
    if "arm" in text:
        return "arm"
    return "unknown"


def _memory_class(memory_total_mb: Optional[int]) -> str:
    if memory_total_mb is None or memory_total_mb <= 0:
        return "unknown"
    if memory_total_mb < 8192:
        return "low"
    if memory_total_mb < 32768:
        return "standard"
    return "high"


def detect_hardware(
    *,
    machine: Optional[str] = None,
    processor: Optional[str] = None,
    memory_total_mb: Optional[int] = None,
    gpu: Optional[str] = None,
) -> Dict[str, Any]:
    raw_machine = machine if machine is not None else platform.machine()
    raw_processor = processor if processor is not None else platform.processor()
    arch = _normalize_arch(str(raw_machine or ""), str(raw_processor or ""))
    gpu_text = str(gpu or "").strip()
    return {
        "machine": str(raw_machine or ""),
        "processor": str(raw_processor or ""),
        "arch": arch,
        "apple_silicon": arch == "arm64" and "apple" in str(raw_processor or "").lower(),
        "memory_total_mb": memory_total_mb,
        "memory_class": _memory_class(memory_total_mb),
        "gpu": gpu_text,
        "gpu_detected": bool(gpu_text),
    }
