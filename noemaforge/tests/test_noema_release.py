#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_noema_release.py
Zone: tests/release
Version: 0.33.0
Created: 2026-06-07
Modified: 2026-06-07
Purpose: Unit tests for noema_release (release-manifest pack + verify).
Inputs: temp directories.
Outputs: unittest results.
Side effects: temp dirs only.
Tests: python3 -m unittest test_noema_release
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

import noema_release as nr  # noqa: E402


class NoemaReleaseTests(unittest.TestCase):
    def _make_tree(self, d: Path):
        (d / "a.txt").write_text("alpha", encoding="utf-8")
        (d / "sub").mkdir()
        (d / "sub" / "b.bin").write_bytes(b"\x00\x01\x02beta")
        # Noise that must be excluded from the manifest.
        (d / "__pycache__").mkdir()
        (d / "__pycache__" / "x.pyc").write_bytes(b"junk")
        (d / "mod.pyc").write_bytes(b"junk")

    def test_build_manifest_conforms_to_contract(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); self._make_tree(d)
            m = nr.build_manifest(d, version="0.33.0", contract_epoch="epoch-1", channel="dev")
        self.assertEqual(m["apiVersion"], "noemaforge.release-manifest/v1")
        self.assertEqual(m["version"], "0.33.0")
        self.assertEqual(m["contract_epoch"], "epoch-1")
        self.assertEqual(m["channel"], "dev")
        self.assertIn("generated_at", m)
        paths = sorted(a["path"] for a in m["artifacts"])
        self.assertEqual(paths, ["a.txt", "sub/b.bin"])  # pyc + __pycache__ excluded
        for a in m["artifacts"]:
            self.assertRegex(a["sha256"], r"^[a-f0-9]{64}$")
            self.assertIsInstance(a["bytes"], int)

    def test_pack_then_verify_roundtrip_ok(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); self._make_tree(d)
            m = nr.build_manifest(d, version="0.33.0", contract_epoch="e1")
            res = nr.verify_manifest(m, d)
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(res["checked"], 2)
        self.assertEqual(res["errors"], [])

    def test_verify_detects_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); self._make_tree(d)
            m = nr.build_manifest(d, version="0.33.0", contract_epoch="e1")
            (d / "a.txt").write_text("tampered", encoding="utf-8")  # change after packing
            res = nr.verify_manifest(m, d)
        self.assertFalse(res["ok"])
        self.assertTrue(any("sha256 mismatch" in e for e in res["errors"]))

    def test_verify_detects_missing_file(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); self._make_tree(d)
            m = nr.build_manifest(d, version="0.33.0", contract_epoch="e1")
            (d / "a.txt").unlink()
            res = nr.verify_manifest(m, d)
        self.assertFalse(res["ok"])
        self.assertTrue(any("missing on disk" in e for e in res["errors"]))

    def test_verify_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); self._make_tree(d)
            m = nr.build_manifest(d, version="0.33.0", contract_epoch="e1")
            m["artifacts"].append({"path": "../escape.txt", "sha256": "a" * 64})
            res = nr.verify_manifest(m, d)
        self.assertFalse(res["ok"])
        self.assertTrue(any("outside the release root" in e for e in res["errors"]))

    def test_verify_rejects_bad_structure(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); self._make_tree(d)
            res = nr.verify_manifest({"apiVersion": "wrong", "artifacts": []}, d)
        self.assertFalse(res["ok"])
        self.assertTrue(any("apiVersion" in e for e in res["errors"]))
        self.assertTrue(any("non-empty list" in e for e in res["errors"]))

    def test_require_signature_fails_when_absent(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); self._make_tree(d)
            m = nr.build_manifest(d, version="0.33.0", contract_epoch="e1")
            res = nr.verify_manifest(m, d, require_signature=True)
        self.assertFalse(res["ok"])
        self.assertTrue(any("signature required" in e for e in res["errors"]))

    def test_cli_pack_and_verify_roundtrip(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); self._make_tree(d)
            out = d / "release-manifest.json"
            rc_pack = nr.main(["pack", "--root", str(d), "--version", "0.33.0",
                               "--contract-epoch", "e1", "--out", str(out)])
            self.assertEqual(rc_pack, 0)
            self.assertTrue(out.is_file())
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc_verify = nr.main(["verify", str(out), "--root", str(d), "--json"])
            self.assertEqual(rc_verify, 0)
            payload = json.loads(buf.getvalue())
            self.assertTrue(payload["ok"])

    def test_cli_verify_exit_1_on_tamper(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); self._make_tree(d)
            out = d / "release-manifest.json"
            nr.main(["pack", "--root", str(d), "--version", "0.33.0",
                     "--contract-epoch", "e1", "--out", str(out)])
            (d / "sub" / "b.bin").write_bytes(b"changed")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = nr.main(["verify", str(out), "--root", str(d)])
            self.assertEqual(rc, 1)
            self.assertIn("OVERALL: FAILED", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
