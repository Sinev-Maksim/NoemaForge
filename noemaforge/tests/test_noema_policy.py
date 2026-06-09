#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_noema_policy.py
Zone: tests/cli
Version: 0.33.0
Created: 2026-06-08
Modified: 2026-06-08
Purpose: Unit tests for noema_policy (deny-by-default policy contract validator).
Inputs: temp dirs + the real package root.
Outputs: unittest results.
Side effects: temp dirs only.
Tests: python3 -m unittest test_noema_policy
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

import noema_policy as npol  # noqa: E402

PKG = Path(__file__).resolve().parents[1]  # noemaforge/

GOOD_TOOLPROXY = "package noemaforge.toolproxy\n\nimport rego.v1\n\ndefault allow := false\n"
GOOD_RELEASE = "package noemaforge.release\n\ndefault publishable := false\n"


def _policies(root: Path, files: dict):
    (root / "policies").mkdir(parents=True)
    for name, content in files.items():
        (root / "policies" / name).write_text(content, encoding="utf-8")


class NoemaPolicyTests(unittest.TestCase):
    def test_good_policies_pass(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _policies(root, {"toolproxy.rego": GOOD_TOOLPROXY, "release.rego": GOOD_RELEASE})
            rep = npol.check_policies(root)
        self.assertTrue(rep["ok"], rep)
        self.assertEqual(rep["checked"], 2)
        self.assertEqual(rep["missing_required"], [])

    def test_allow_true_fails_deny_by_default(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            bad = "package noemaforge.toolproxy\n\ndefault allow := true\n"
            _policies(root, {"toolproxy.rego": bad, "release.rego": GOOD_RELEASE})
            rep = npol.check_policies(root)
        self.assertFalse(rep["ok"])
        tp = next(r for r in rep["policies"] if r["file"].endswith("toolproxy.rego"))
        self.assertTrue(any("deny-by-default" in v for v in tp["violations"]))

    def test_missing_package_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _policies(root, {"toolproxy.rego": "default allow := false\n", "release.rego": GOOD_RELEASE})
            rep = npol.check_policies(root)
        tp = next(r for r in rep["policies"] if r["file"].endswith("toolproxy.rego"))
        self.assertFalse(tp["ok"])
        self.assertTrue(any("package" in v for v in tp["violations"]))

    def test_wrong_package_on_known_policy_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            wrong = "package noemaforge.wrong\n\ndefault allow := false\n"
            _policies(root, {"toolproxy.rego": wrong, "release.rego": GOOD_RELEASE})
            rep = npol.check_policies(root)
        self.assertFalse(rep["ok"])

    def test_missing_required_policy_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _policies(root, {"toolproxy.rego": GOOD_TOOLPROXY})  # release.rego absent
            rep = npol.check_policies(root)
        self.assertFalse(rep["ok"])
        self.assertIn("release.rego", rep["missing_required"])

    def test_real_policies_pass(self):
        rep = npol.check_policies(PKG)
        self.assertTrue(rep["ok"], rep)
        files = {r["file"] for r in rep["policies"]}
        self.assertIn("policies/toolproxy.rego", files)
        self.assertIn("policies/release.rego", files)

    def test_cli_exit_codes_and_json(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _policies(root, {"toolproxy.rego": GOOD_TOOLPROXY, "release.rego": GOOD_RELEASE})
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = npol.main(["test", "--root", str(root), "--json"])
            self.assertEqual(rc, 0)
            self.assertTrue(json.loads(buf.getvalue())["ok"])
            # bad policy -> exit 1
            (root / "policies" / "toolproxy.rego").write_text(
                "package noemaforge.toolproxy\ndefault allow := true\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                rc2 = npol.main(["test", "--root", str(root)])
            self.assertEqual(rc2, 1)

    def test_wired_into_dispatcher(self):
        import noema_cli
        self.assertIn("policy", noema_cli._subcommands())


if __name__ == "__main__":
    unittest.main()
