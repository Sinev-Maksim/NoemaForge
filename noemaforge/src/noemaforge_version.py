#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/noemaforge_version.py
Zone: release/runtime
Version: 0.33.0
Created: 2026-05-25
Modified: 2026-06-07
Purpose: Provide the single source-of-truth runtime version for NoemaForge Python modules.
Inputs: The canonical VERSION file at $NOEMAFORGE_ROOT/VERSION or a repository-relative VERSION file.
Outputs: RUNTIME_VERSION constant used by runtime modules and audit tooling.
Side effects: Emits a warning to stderr only when VERSION cannot be read.
Tests: Import smoke, version-audit --strict-all --expected 0.33.0, Python syntax validation.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Centralized version management for NoemaForge.

Runtime modules must import RUNTIME_VERSION from this module instead of hardcoding
version literals. The canonical value lives in VERSION; this module only provides a
safe import-time bridge for Python runtime code.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

EMBEDDED_DEFAULT_VERSION = "0.33.0"


def _candidate_version_files() -> list[Path]:
    """Return VERSION file candidates in priority order."""
    candidates: list[Path] = []
    env_root = os.environ.get("NOEMAFORGE_ROOT")
    if env_root:
        candidates.append(Path(env_root) / "VERSION")

    here = Path(__file__).resolve()
    # noemaforge/src/noemaforge_version.py -> repo/noemaforge/VERSION
    candidates.append(here.parents[1] / "VERSION")
    # noemaforge/src/noemaforge_version.py -> repo/VERSION in source checkouts
    candidates.append(here.parents[2] / "VERSION")
    return candidates


def _read_runtime_version() -> str:
    """Read the canonical NoemaForge version, falling back safely if needed."""
    errors: list[str] = []
    for path in _candidate_version_files():
        try:
            value = path.read_text(encoding="utf-8").strip()
        except Exception as exc:  # pragma: no cover - depends on host layout
            errors.append(f"{path}: {exc}")
            continue
        if value:
            return value
        errors.append(f"{path}: empty VERSION file")

    print(
        "[noemaforge_version][WARN] cannot read canonical VERSION; "
        f"using embedded default {EMBEDDED_DEFAULT_VERSION}. Details: " + "; ".join(errors),
        file=sys.stderr,
    )
    return EMBEDDED_DEFAULT_VERSION


RUNTIME_VERSION = _read_runtime_version()

__all__ = ["RUNTIME_VERSION"]
