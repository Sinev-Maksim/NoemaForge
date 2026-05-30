#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_premerge_sha256sums_check.py
Zone: release/package
Created: 2026-05-30
Modified: 2026-05-30
Purpose: TDD tests for Check 9 (SHA256SUMS staleness) in noemaforge-premerge-check.ps1.
Inputs: noemaforge/tools/prep/noemaforge-premerge-check.ps1 source text; temp dirs.
Outputs: unittest assertions only.
Side effects: None (temp dirs only).
Tests: python3 -m unittest noemaforge/tests/test_premerge_sha256sums_check.py -v
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # noemaforge/
PROJECT_ROOT = ROOT.parent                          # repo root
PS1_PATH = ROOT / "tools" / "prep" / "noemaforge-premerge-check.ps1"


# ---------------------------------------------------------------------------
# Source-text assertions (fast, no subprocess)
# ---------------------------------------------------------------------------

class TestPs1SourceContainsCheck9(unittest.TestCase):
    """The PS1 script must contain the SHA256SUMS staleness check."""

    _src: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls._src = PS1_PATH.read_text(encoding="utf-8")

    def test_check9_comment_present(self) -> None:
        self.assertIn("SHA256SUMS", self._src)

    def test_check9_reads_sha256sums_file(self) -> None:
        self.assertIn("$sha256sumsPath", self._src)

    def test_check9_iterates_src_py_files(self) -> None:
        # Should scan noemaforge/src/*.py for missing entries.
        self.assertIn("noemaforge/src/", self._src)

    def test_check9_reports_missing_entries(self) -> None:
        # Should surface which files are missing from SHA256SUMS.
        self.assertIn("Missing from SHA256SUMS", self._src)

    def test_check9_ok_check_call_present(self) -> None:
        self.assertIn("Ok-Check", self._src)


# ---------------------------------------------------------------------------
# Functional tests via pwsh subprocess
# ---------------------------------------------------------------------------

def _pwsh_available() -> bool:
    """Return True if PowerShell 7+ (pwsh) is available on PATH."""
    try:
        r = subprocess.run(["pwsh", "-Command", "echo ok"], capture_output=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@unittest.skipUnless(_pwsh_available(), "pwsh not available")
class TestCheck9Functional(unittest.TestCase):
    """Functional tests that run the PS1 script against fixture trees."""

    def _run_ps1(self, root: Path) -> tuple[int, str]:
        """Run noemaforge-premerge-check.ps1 with *root* as -Root, return (exit_code, stdout)."""
        result = subprocess.run(
            ["pwsh", "-NonInteractive", "-File", str(PS1_PATH), "-Root", str(root)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode, result.stdout + result.stderr

    def _make_fixture(self, td: Path, py_files: list[str], sha_lines: list[str]) -> None:
        """Build a minimal fixture tree under *td* for the SHA256SUMS check."""
        # Required structure so earlier checks pass without noise.
        for vf in ["VERSION", "noemaforge/VERSION", "docs/VERSION"]:
            p = td / vf
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("0.32.2", encoding="utf-8")

        rj = td / "docs" / "release.json"
        rj.parent.mkdir(parents=True, exist_ok=True)
        rj.write_text(
            '{"version":"0.32.2","release":"0.32.2","release_name":"NoemaForge 0.32.2",'
            '"package":"noemaforge_0.32.2_x","status":"alpha","channel":"alpha",'
            '"summary":"","version_audit":"","generated_at":"","updated_at":""}',
            encoding="utf-8",
        )

        src = td / "noemaforge" / "src"
        src.mkdir(parents=True, exist_ok=True)
        for fname in py_files:
            (src / fname).write_text("# stub\n", encoding="utf-8")

        (td / "noemaforge" / "configs").mkdir(parents=True, exist_ok=True)

        sha = td / "SHA256SUMS"
        sha.write_text("\n".join(sha_lines) + "\n", encoding="utf-8")

    def test_all_py_files_in_sha256sums_passes(self) -> None:
        """Check 9 must PASS when every src/*.py appears in SHA256SUMS."""
        with tempfile.TemporaryDirectory(prefix="nf_sha_pass_") as td:
            td_path = Path(td)
            py_files = ["foo.py", "bar.py"]
            sha_lines = [
                "aabbccdd" * 8 + "  noemaforge/src/foo.py",
                "11223344" * 8 + "  noemaforge/src/bar.py",
            ]
            self._make_fixture(td_path, py_files, sha_lines)
            code, out = self._run_ps1(td_path)
            self.assertIn("SHA256SUMS covers all", out)
            # Check 9 passes; overall script may still fail on other checks
            # (git, py_compile, etc.) so we only verify the SHA256SUMS line.
            self.assertNotIn("Missing from SHA256SUMS", out)

    def test_missing_py_file_in_sha256sums_fails(self) -> None:
        """Check 9 must FAIL and name the missing file."""
        with tempfile.TemporaryDirectory(prefix="nf_sha_fail_") as td:
            td_path = Path(td)
            py_files = ["foo.py", "bar.py", "new_module.py"]
            # Only foo.py and bar.py are in SHA256SUMS — new_module.py is missing.
            sha_lines = [
                "aabbccdd" * 8 + "  noemaforge/src/foo.py",
                "11223344" * 8 + "  noemaforge/src/bar.py",
            ]
            self._make_fixture(td_path, py_files, sha_lines)
            _code, out = self._run_ps1(td_path)
            self.assertIn("Missing from SHA256SUMS", out)
            self.assertIn("new_module.py", out)

    def test_absent_sha256sums_fails(self) -> None:
        """Check 9 must FAIL when SHA256SUMS is missing entirely."""
        with tempfile.TemporaryDirectory(prefix="nf_sha_absent_") as td:
            td_path = Path(td)
            py_files = ["foo.py"]
            # Build fixture but then delete SHA256SUMS after creation.
            self._make_fixture(td_path, py_files, [])
            (td_path / "SHA256SUMS").unlink()
            _code, out = self._run_ps1(td_path)
            self.assertIn("SHA256SUMS", out)
            # The check line must be a FAIL (no PASS for SHA256SUMS).
            lines = [l for l in out.splitlines() if "SHA256SUMS" in l and "[PASS]" not in l]
            self.assertTrue(len(lines) > 0, "Expected a FAIL line mentioning SHA256SUMS")


if __name__ == "__main__":
    unittest.main()
