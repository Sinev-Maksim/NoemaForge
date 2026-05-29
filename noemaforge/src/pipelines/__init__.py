"""
=== NoemaForge File Header ===
File: noemaforge/src/pipelines/__init__.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Manage NoemaForge pipeline catalog, runs, gates, artifacts and state.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""


# === NoemaForge Autodoc File Header ===
# File: src/pipelines/__init__.py
# Purpose: Implement the deterministic pipeline '__init__'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Inputs:
#   - Imported Python calls only; no explicit CLI or environment inputs detected.
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""NoemaForge built-in deterministic pipelines.

Pipelines are *spine code*: they run without network, keep auditability,
and generate structured artifacts.

LLM-based narrative/creative steps should be optional add-ons executed
via roles (brain zone) and written as separate artifacts.
"""
