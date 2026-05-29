#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_config_validator.py
Zone: test
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: TDD tests for config_validator — JSON/YAML parse gate for the release repo.
Inputs: config_validator module (ConfigValidator, FileCheckResult, ValidationReport).
Outputs: test pass/fail.
Side effects: Creates and removes temporary directories with synthetic JSON/YAML files.
Tests: python -m unittest noemaforge/tests/test_config_validator.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from config_validator import (  # noqa: E402
    ConfigValidator,
    FileCheckResult,
    ValidationReport,
)


# ---------------------------------------------------------------------------
# FileCheckResult
# ---------------------------------------------------------------------------

class TestFileCheckResult(unittest.TestCase):
    """FileCheckResult is a lightweight result record for a single file."""

    def test_ok_result(self) -> None:
        r = FileCheckResult(path="/a/b.json", kind="json", ok=True, error="")
        self.assertTrue(r.ok)
        self.assertEqual(r.kind, "json")

    def test_error_result(self) -> None:
        r = FileCheckResult(path="/a/b.json", kind="json", ok=False, error="parse error")
        self.assertFalse(r.ok)
        self.assertIn("parse error", r.error)

    def test_to_dict(self) -> None:
        r = FileCheckResult(path="/a/b.json", kind="json", ok=True, error="")
        d = r.to_dict()
        self.assertIn("path", d)
        self.assertIn("kind", d)
        self.assertIn("ok", d)
        self.assertIn("error", d)

    def test_yaml_kind(self) -> None:
        r = FileCheckResult(path="/a/b.yaml", kind="yaml", ok=True, error="")
        self.assertEqual(r.kind, "yaml")


# ---------------------------------------------------------------------------
# ConfigValidator.validate_json_file
# ---------------------------------------------------------------------------

class TestValidateJsonFile(unittest.TestCase):
    """validate_json_file() parses a single JSON file."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.cv = ConfigValidator(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_valid_json_passes(self) -> None:
        p = self.td / "ok.json"
        p.write_text('{"key": "value", "n": 42}', encoding="utf-8")
        result = self.cv.validate_json_file(p)
        self.assertTrue(result.ok)

    def test_invalid_json_fails(self) -> None:
        p = self.td / "bad.json"
        p.write_text("{key: value}", encoding="utf-8")  # missing quotes
        result = self.cv.validate_json_file(p)
        self.assertFalse(result.ok)

    def test_error_message_contains_details(self) -> None:
        p = self.td / "bad.json"
        p.write_text("[1, 2,]", encoding="utf-8")  # trailing comma
        result = self.cv.validate_json_file(p)
        self.assertFalse(result.ok)
        self.assertGreater(len(result.error), 0)

    def test_empty_json_file_fails(self) -> None:
        p = self.td / "empty.json"
        p.write_text("", encoding="utf-8")
        result = self.cv.validate_json_file(p)
        self.assertFalse(result.ok)

    def test_nested_json_passes(self) -> None:
        p = self.td / "nested.json"
        p.write_text('{"a": [1, 2, {"b": true}]}', encoding="utf-8")
        result = self.cv.validate_json_file(p)
        self.assertTrue(result.ok)

    def test_result_kind_is_json(self) -> None:
        p = self.td / "x.json"
        p.write_text("null", encoding="utf-8")
        result = self.cv.validate_json_file(p)
        self.assertEqual(result.kind, "json")

    def test_result_path_matches(self) -> None:
        p = self.td / "x.json"
        p.write_text("{}", encoding="utf-8")
        result = self.cv.validate_json_file(p)
        self.assertIn("x.json", result.path)


# ---------------------------------------------------------------------------
# ConfigValidator.validate_yaml_file
# ---------------------------------------------------------------------------

class TestValidateYamlFile(unittest.TestCase):
    """validate_yaml_file() parses a single YAML file."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.cv = ConfigValidator(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_valid_yaml_passes(self) -> None:
        p = self.td / "ok.yaml"
        p.write_text("key: value\nn: 42\n", encoding="utf-8")
        result = self.cv.validate_yaml_file(p)
        self.assertTrue(result.ok)

    def test_invalid_yaml_fails(self) -> None:
        p = self.td / "bad.yaml"
        # Intentionally malformed: tab-in-indentation after a mapping
        p.write_text("key:\n\tbad_indent: value\n", encoding="utf-8")
        result = self.cv.validate_yaml_file(p)
        self.assertFalse(result.ok)

    def test_empty_yaml_passes(self) -> None:
        """Empty YAML is valid (evaluates to None in PyYAML)."""
        p = self.td / "empty.yaml"
        p.write_text("", encoding="utf-8")
        result = self.cv.validate_yaml_file(p)
        self.assertTrue(result.ok)

    def test_yml_extension_passes(self) -> None:
        p = self.td / "ok.yml"
        p.write_text("enabled: true\n", encoding="utf-8")
        result = self.cv.validate_yaml_file(p)
        self.assertTrue(result.ok)

    def test_result_kind_is_yaml(self) -> None:
        p = self.td / "x.yaml"
        p.write_text("key: value\n", encoding="utf-8")
        result = self.cv.validate_yaml_file(p)
        self.assertEqual(result.kind, "yaml")

    def test_error_message_non_empty_on_failure(self) -> None:
        p = self.td / "bad.yaml"
        p.write_text("key:\n\tbad_indent: value\n", encoding="utf-8")
        result = self.cv.validate_yaml_file(p)
        if not result.ok:
            self.assertGreater(len(result.error), 0)


# ---------------------------------------------------------------------------
# ConfigValidator.scan()
# ---------------------------------------------------------------------------

class TestConfigValidatorScan(unittest.TestCase):
    """scan() walks a directory tree and checks all JSON/YAML files."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.cv = ConfigValidator(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def _write(self, rel: str, content: str) -> Path:
        p = self.td / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_all_valid_returns_ok(self) -> None:
        self._write("a.json", '{"a": 1}')
        self._write("b.yaml", "key: val\n")
        report = self.cv.scan()
        self.assertTrue(report.ok)

    def test_one_invalid_json_returns_not_ok(self) -> None:
        self._write("ok.json", '{"a": 1}')
        self._write("bad.json", "{not json}")
        report = self.cv.scan()
        self.assertFalse(report.ok)

    def test_errors_list_populated(self) -> None:
        self._write("bad.json", "{not json}")
        report = self.cv.scan()
        self.assertGreater(len(report.errors), 0)

    def test_files_checked_count(self) -> None:
        self._write("a.json", '{}')
        self._write("b.yaml", "k: v\n")
        self._write("c.json", '{"x": 1}')
        report = self.cv.scan()
        self.assertEqual(report.files_checked, 3)

    def test_json_checked_count(self) -> None:
        self._write("a.json", '{}')
        self._write("b.json", '{"x": 1}')
        self._write("c.yaml", "k: v\n")
        report = self.cv.scan()
        self.assertEqual(report.json_checked, 2)

    def test_yaml_checked_count(self) -> None:
        self._write("a.yaml", "k: v\n")
        self._write("b.yml", "enabled: true\n")
        self._write("c.json", '{}')
        report = self.cv.scan()
        self.assertEqual(report.yaml_checked, 2)

    def test_skips_git_dir(self) -> None:
        self._write(".git/config.json", "{not json}")  # in .git — should be skipped
        self._write("ok.json", '{}')
        report = self.cv.scan()
        self.assertTrue(report.ok)

    def test_skips_pycache(self) -> None:
        self._write("__pycache__/data.json", "{not json}")
        self._write("ok.json", '{}')
        report = self.cv.scan()
        self.assertTrue(report.ok)

    def test_recurses_into_subdirs(self) -> None:
        self._write("sub/dir/deep.json", '{"nested": true}')
        report = self.cv.scan()
        self.assertTrue(report.ok)
        self.assertEqual(report.files_checked, 1)

    def test_report_has_version(self) -> None:
        report = self.cv.scan()
        self.assertIsNotNone(report.version)
        self.assertGreater(len(report.version), 0)

    def test_empty_dir_is_ok(self) -> None:
        report = self.cv.scan()
        self.assertTrue(report.ok)
        self.assertEqual(report.files_checked, 0)

    def test_report_to_dict(self) -> None:
        report = self.cv.scan()
        d = report.to_dict()
        self.assertIn("ok", d)
        self.assertIn("files_checked", d)
        self.assertIn("errors", d)
        self.assertIn("version", d)

    def test_error_details_include_path(self) -> None:
        self._write("broken.json", "[1, 2,]")
        report = self.cv.scan()
        self.assertFalse(report.ok)
        error_paths = [e.path for e in report.errors]
        self.assertTrue(any("broken.json" in p for p in error_paths))

    def test_custom_skip_dirs(self) -> None:
        cv = ConfigValidator(self.td, skip_dirs={"vendor", ".git", "__pycache__"})
        self._write("vendor/pkg.json", "{bad json}")
        self._write("ok.json", '{}')
        report = cv.scan()
        self.assertTrue(report.ok)


if __name__ == "__main__":
    unittest.main()
