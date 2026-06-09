#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_noema_catalog.py
Zone: tests/cli
Version: 0.33.0
Created: 2026-06-08
Modified: 2026-06-08
Purpose: Unit tests for noema_catalog (knowledge projection / capability catalog).
Inputs: temp dirs + the real package root.
Outputs: unittest results.
Side effects: temp dirs only.
Tests: python3 -m unittest test_noema_catalog
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import noema_catalog as nc  # noqa: E402

PKG = Path(__file__).resolve().parents[1]  # noemaforge/


def _fixture(root: Path):
    (root / "schemas").mkdir(parents=True)
    (root / "schemas" / "thing.schema.json").write_text(
        json.dumps({"$id": "https://x/thing", "title": "Thing", "required": ["a", "b"]}),
        encoding="utf-8")
    (root / "policies").mkdir(parents=True)
    (root / "policies" / "guard.rego").write_text(
        "package noemaforge.guard\n\ndefault allow := false\n", encoding="utf-8")
    (root / "src").mkdir(parents=True)
    (root / "src" / "noema_widget.py").write_text("def main(argv=None):\n    return 0\n",
                                                  encoding="utf-8")
    (root / "src" / "noema_cli.py").write_text("def main(argv=None):\n    return 0\n",
                                               encoding="utf-8")  # dispatcher excluded
    (root / "VERSION").write_text("0.33.0\n", encoding="utf-8")


class NoemaCatalogTests(unittest.TestCase):
    def test_build_catalog_on_fixture(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _fixture(root)
            cat = nc.build_catalog(root)
        self.assertEqual(cat["projection_type"], "capability-catalog/v1")
        self.assertIn("not_source_of_truth", cat)
        self.assertEqual(cat["version"], "0.33.0")
        self.assertEqual(len(cat["schemas"]), 1)
        self.assertEqual(cat["schemas"][0]["title"], "Thing")
        self.assertEqual(cat["schemas"][0]["required"], ["a", "b"])
        self.assertEqual(cat["policies"][0]["package"], "noemaforge.guard")
        self.assertEqual(cat["cli_commands"], ["widget"])  # noema_cli excluded
        self.assertIn("digest", cat)
        self.assertIn("generated_at", cat)

    def test_digest_stable_excluding_generated_at(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _fixture(root)
            a = nc.build_catalog(root)
            b = nc.build_catalog(root)
        # Same inputs -> same digest, even though generated_at differs.
        self.assertEqual(a["digest"], b["digest"])

    def test_digest_changes_with_content(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _fixture(root)
            a = nc.build_catalog(root)
            (root / "policies" / "more.rego").write_text("package noemaforge.more\n", encoding="utf-8")
            b = nc.build_catalog(root)
        self.assertNotEqual(a["digest"], b["digest"])

    def test_format_markdown_sections(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _fixture(root)
            md = nc.format_markdown(nc.build_catalog(root))
        self.assertIn("capability catalog", md)
        self.assertIn("GENERATED PROJECTION", md)
        self.assertIn("`noema widget`", md)
        self.assertIn("Published schemas", md)

    def test_real_package_root_has_known_contracts(self):
        cat = nc.build_catalog(PKG)
        files = {s["file"] for s in cat["schemas"]}
        self.assertIn("schemas/capability-token.schema.json", files)
        self.assertIn("schemas/release-manifest.schema.json", files)
        pol = {p["file"] for p in cat["policies"]}
        self.assertIn("policies/toolproxy.rego", pol)
        # the real dispatcher's commands include the upgrade/doctor/release surface
        self.assertIn("upgrade", cat["cli_commands"])
        self.assertIn("catalog", cat["cli_commands"])

    def test_cli_json_and_out(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _fixture(root)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = nc.main(["--root", str(root), "--json"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["projection_type"], "capability-catalog/v1")
            out = root / "catalog.json"
            rc2 = nc.main(["--root", str(root), "--json", "--out", str(out)])
            self.assertEqual(rc2, 0)
            self.assertTrue(out.is_file())

    def test_wired_into_dispatcher(self):
        import noema_cli
        self.assertIn("catalog", noema_cli._subcommands())


if __name__ == "__main__":
    unittest.main()
