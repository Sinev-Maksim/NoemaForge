#!/usr/bin/env python3
"""
Purpose: Guard release/UAT helper scripts against direct Python module execution
and unsafe Markdown heredocs.
Tests: python3 -m unittest noemaforge.tests.test_release_helper_shell_safety
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent


class ReleaseHelperShellSafetyTests(unittest.TestCase):
    def _prep_scripts(self) -> list[Path]:
        return sorted((ROOT / "tools" / "prep").glob("*.sh"))

    def test_prep_helpers_do_not_execute_python_modules_directly(self) -> None:
        direct_exec = re.compile(r'^\s*(?:exec\s+)?(?:["\']?[\w./$-]+\.py["\']?)(?:\s|$)')
        offenders: list[str] = []
        for path in self._prep_scripts():
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if direct_exec.search(line):
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{lineno}:{stripped}")
        self.assertEqual([], offenders, "\n".join(offenders))

    def test_markdown_heredocs_use_quoted_delimiters(self) -> None:
        markdown_heredoc = re.compile(r'>\s*["\']?[^"\']+\.md["\']?\s*<<\s*([A-Za-z0-9_]+)\s*$')
        offenders: list[str] = []
        for path in self._prep_scripts():
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if not markdown_heredoc.search(line):
                    continue
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{lineno}:{line.strip()}")
        self.assertEqual([], offenders, "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
