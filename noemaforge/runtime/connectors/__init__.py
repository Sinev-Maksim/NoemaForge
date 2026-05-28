#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/runtime/connectors/__init__.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Expose optional runtime connector helpers.
Inputs: Connector modules.
Outputs: Importable connector classes.
Side effects: None.
Tests: noemaforge/tests/test_multios_runtime_contract.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from .remote_http import RemoteHTTPRuntimeConnector

__all__ = ["RemoteHTTPRuntimeConnector"]
