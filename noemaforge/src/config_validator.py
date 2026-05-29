#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/config_validator.py
Zone: release/validation
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: JSON/YAML parse-gate for the NoemaForge release repo.
  Walks a directory tree, attempts to parse every .json/.yaml/.yml file,
  and returns a structured report.  Designed for use in first-run-audit,
  CI and pre-commit hooks.
Inputs: A root directory path; optional set of directory names to skip.
Outputs: ValidationReport dataclass with per-file FileCheckResult list.
Side effects: Read-only; no writes; no subprocess calls.
Tests: python -m unittest noemaforge/tests/test_config_validator.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from noemaforge_version import RUNTIME_VERSION

# Directories that are always skipped regardless of caller settings.
_DEFAULT_SKIP_DIRS: Set[str] = {
    ".git",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "env",
}

# YAML is optional; degrade gracefully if PyYAML is absent.
try:
    import yaml as _yaml  # type: ignore[import-untyped]
    _YAML_AVAILABLE = True
except ImportError:
    _yaml = None  # type: ignore[assignment]
    _YAML_AVAILABLE = False


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class FileCheckResult:
    """Outcome of parsing a single configuration file."""

    path: str
    kind: str          # "json" | "yaml"
    ok: bool
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "kind": self.kind, "ok": self.ok, "error": self.error}


@dataclass
class ValidationReport:
    """Aggregate result from scanning a directory tree."""

    ok: bool
    files_checked: int
    json_checked: int
    yaml_checked: int
    errors: List[FileCheckResult] = field(default_factory=list)
    version: str = RUNTIME_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "files_checked": self.files_checked,
            "json_checked": self.json_checked,
            "yaml_checked": self.yaml_checked,
            "errors": [e.to_dict() for e in self.errors],
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class ConfigValidator:
    """Walk *root_dir* and parse every JSON/YAML file found.

    Parameters
    ----------
    root_dir:
        Directory to scan recursively.
    skip_dirs:
        Set of directory *names* (not paths) to skip.  The default skip list
        is always applied; this parameter extends it.
    """

    def __init__(
        self,
        root_dir: "str | Path",
        skip_dirs: Optional[Set[str]] = None,
    ) -> None:
        self._root = Path(root_dir)
        self._skip = _DEFAULT_SKIP_DIRS | (skip_dirs or set())

    # ------------------------------------------------------------------
    # Per-file validators
    # ------------------------------------------------------------------

    def validate_json_file(self, path: "str | Path") -> FileCheckResult:
        """Parse *path* as JSON and return the result."""
        p = Path(path)
        str_path = str(p)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            json.loads(text)
            return FileCheckResult(path=str_path, kind="json", ok=True)
        except Exception as exc:
            return FileCheckResult(path=str_path, kind="json", ok=False, error=str(exc))

    def validate_yaml_file(self, path: "str | Path") -> FileCheckResult:
        """Parse *path* as YAML and return the result.

        Returns a passing result with a warning in ``error`` if PyYAML is
        not installed (YAML validation is skipped rather than hard-failing).
        """
        p = Path(path)
        str_path = str(p)
        if not _YAML_AVAILABLE:
            return FileCheckResult(
                path=str_path, kind="yaml", ok=True,
                error="warn: PyYAML not installed; YAML validation skipped",
            )
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            _yaml.safe_load(text)
            return FileCheckResult(path=str_path, kind="yaml", ok=True)
        except Exception as exc:
            return FileCheckResult(path=str_path, kind="yaml", ok=False, error=str(exc))

    # ------------------------------------------------------------------
    # Directory scan
    # ------------------------------------------------------------------

    def scan(self) -> ValidationReport:
        """Recursively scan *root_dir* and validate every JSON/YAML file.

        Returns
        -------
        ValidationReport
            ``ok=True`` only when every file parsed without errors.
        """
        json_results: List[FileCheckResult] = []
        yaml_results: List[FileCheckResult] = []

        for file_path in self._iter_files():
            suffix = file_path.suffix.lower()
            if suffix == ".json":
                json_results.append(self.validate_json_file(file_path))
            elif suffix in {".yaml", ".yml"}:
                yaml_results.append(self.validate_yaml_file(file_path))

        all_results = json_results + yaml_results
        errors = [r for r in all_results if not r.ok]
        return ValidationReport(
            ok=len(errors) == 0,
            files_checked=len(all_results),
            json_checked=len(json_results),
            yaml_checked=len(yaml_results),
            errors=errors,
            version=RUNTIME_VERSION,
        )

    def _iter_files(self):
        """Yield all non-skipped files under *root_dir*."""
        try:
            for item in self._root.rglob("*"):
                # Skip any path whose parent chain includes a skip-listed dir.
                if any(part in self._skip for part in item.parts):
                    continue
                if item.is_file():
                    yield item
        except (OSError, PermissionError):
            pass
