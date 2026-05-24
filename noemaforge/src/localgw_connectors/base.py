#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/localgw_connectors/base.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: src/localgw_connectors/base.py
# Purpose: Provide the module 'base'.
# Invoked by / imported from:
#   - src/localgateway.py
# Public API / entry functions:
#   - class ConnectorContext
# Inputs:
#   - Imports: __future__, dataclasses, typing
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""localgw_connectors.base (v0.15.0)

Shared types for LocalGateway connectors.
"""


from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ConnectorContext:
    epoch_dir: str
    policy: Dict[str, Any]
    actor: Dict[str, Any]
    trace_id: str
    lan_session_token: str
    device_uid: str = ""
    device_profile: Optional[Dict[str, Any]] = None
