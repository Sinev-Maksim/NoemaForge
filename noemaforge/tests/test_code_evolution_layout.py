#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_code_evolution_layout.py
Zone: tests
Version: 0.33.0
Created: 2026-07-24
Modified: 2026-07-24
Purpose: Verify CodeEvolutionLoop resolves both repository-root and package-root layouts and actually executes bounded tests.
Inputs: Temporary minimal repository/package trees.
Outputs: unittest assertions only.
Side effects: Temporary proposal state and Python bytecode under the temporary directory.
Tests: direct unittest execution from the premerge quality workflow.
Notes: This guards the GUI regression where package-root input previously resolved a duplicated noemaforge/noemaforge path and ran zero tests.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from code_evolution_loop import CodeEvolutionLoop  # noqa: E402


class _Paths:
    def __init__(self, state: Path):
        self.code_evolution_state_dir = state


class CodeEvolutionLayoutTests(unittest.TestCase):
    def _make_package(self, base: Path) -> Path:
        package = base / "noemaforge"
        (package / "src").mkdir(parents=True)
        (package / "tests").mkdir(parents=True)
        (package / "docs" / "history").mkdir(parents=True)
        (package / "src" / "sample.py").write_text(
            "def answer():\n    return 42\n", encoding="utf-8"
        )
        (package / "tests" / "test_layout_smoke.py").write_text(
            "import unittest\n\n"
            "class LayoutSmoke(unittest.TestCase):\n"
            "    def test_runs(self):\n"
            "        self.assertEqual(42, 42)\n",
            encoding="utf-8",
        )
        (package / "docs" / "TODO.md").write_text(
            "- [ ] **task-900 (P0): Verify package layout**\n",
            encoding="utf-8",
        )
        (package / "docs" / "history" / "CHANGELOG.md").write_text(
            "# Changelog\n", encoding="utf-8"
        )
        return package

    def _assert_layout(self, supplied_root: Path, expected_package: Path, state: Path) -> None:
        loop = CodeEvolutionLoop(
            project_root=supplied_root,
            paths=_Paths(state),
            python_exe=sys.executable,
            pycache_prefix=state / "pycache",
            dry_run=True,
        )
        self.assertEqual(expected_package.resolve(), loop.package_root)
        self.assertEqual(expected_package / "docs" / "TODO.md", loop._todo_path)
        result = loop.run_tests(("test_layout_smoke.py",))
        self.assertTrue(result["ok"], result)
        self.assertEqual(1, result["test_passed"], result)

    def test_repository_root_layout_executes_tests(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw) / "repo"
            package = self._make_package(repo)
            self._assert_layout(repo, package, Path(raw) / "state-repo")

    def test_package_root_layout_executes_tests(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw) / "repo"
            package = self._make_package(repo)
            self._assert_layout(package, package, Path(raw) / "state-package")


if __name__ == "__main__":
    unittest.main()
