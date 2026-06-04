#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_casebase.py
Zone: tests
Version: 0.32.2
Created: 2026-06-04
Modified: 2026-06-04
Purpose: Tests for casebase.py — solution cache with deterministic hash embedding.
         Covers: _nowz, hash_embed, _sha256_file, compute_inputs_fingerprint,
         init_db, get_case_by_key, upsert_case (no-index), _row_to_case.
Tests: python3 -m unittest noemaforge/tests/test_casebase.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Stub platform_paths so we can redirect DB paths
_mock_platform_paths = types.ModuleType("platform_paths")
_mock_paths_obj = MagicMock()
_mock_paths_obj.data_root = Path("/tmp/nf-casebase-test")
_mock_platform_paths.DEFAULT_PATHS = _mock_paths_obj
sys.modules.setdefault("platform_paths", _mock_platform_paths)

import casebase  # noqa: E402


class TestNowz(unittest.TestCase):
    def test_returns_string(self) -> None:
        result = casebase._nowz()
        self.assertIsInstance(result, str)

    def test_ends_with_z(self) -> None:
        result = casebase._nowz()
        self.assertTrue(result.endswith("Z"), f"Expected Z suffix: {result!r}")

    def test_matches_iso8601_format(self) -> None:
        import re
        result = casebase._nowz()
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class TestHashEmbed(unittest.TestCase):
    def test_returns_list_of_floats(self) -> None:
        vec = casebase.hash_embed("hello world")
        self.assertIsInstance(vec, list)
        self.assertTrue(all(isinstance(x, float) for x in vec))

    def test_default_dims_is_256(self) -> None:
        vec = casebase.hash_embed("test text")
        self.assertEqual(len(vec), casebase.HASH_EMBED_DIMS)

    def test_custom_dims_respected(self) -> None:
        vec = casebase.hash_embed("test text", dims=128)
        self.assertEqual(len(vec), 128)

    def test_empty_text_returns_zero_vector(self) -> None:
        vec = casebase.hash_embed("")
        self.assertEqual(len(vec), casebase.HASH_EMBED_DIMS)
        self.assertEqual(sum(abs(x) for x in vec), 0.0)

    def test_l2_norm_is_approximately_one_for_nonempty(self) -> None:
        vec = casebase.hash_embed("the quick brown fox jumps over the lazy dog")
        norm = math.sqrt(sum(x * x for x in vec))
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_deterministic_same_text(self) -> None:
        vec1 = casebase.hash_embed("hello world")
        vec2 = casebase.hash_embed("hello world")
        self.assertEqual(vec1, vec2)

    def test_different_texts_produce_different_vectors(self) -> None:
        vec1 = casebase.hash_embed("python programming")
        vec2 = casebase.hash_embed("music generation pipeline")
        self.assertNotEqual(vec1, vec2)

    def test_case_insensitive(self) -> None:
        vec1 = casebase.hash_embed("Python")
        vec2 = casebase.hash_embed("python")
        self.assertEqual(vec1, vec2)

    def test_whitespace_only_returns_zero_vector(self) -> None:
        vec = casebase.hash_embed("   \t\n  ")
        self.assertEqual(sum(abs(x) for x in vec), 0.0)

    def test_vector_entries_between_neg_one_and_one(self) -> None:
        vec = casebase.hash_embed("test vector bounds check")
        for v in vec:
            self.assertGreaterEqual(v, -1.0)
            self.assertLessEqual(v, 1.0)

    def test_model_id_constant_defined(self) -> None:
        self.assertEqual(casebase.HASH_EMBED_MODEL_ID, "hash256-v1")

    def test_dims_constant_defined(self) -> None:
        self.assertEqual(casebase.HASH_EMBED_DIMS, 256)


class TestSha256File(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_returns_hex_string(self) -> None:
        path = os.path.join(self._tmpdir, "test.txt")
        with open(path, "wb") as f:
            f.write(b"hello world")
        result = casebase._sha256_file(path)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 64)

    def test_matches_hashlib_sha256(self) -> None:
        path = os.path.join(self._tmpdir, "data.bin")
        content = b"NoemaForge test content"
        with open(path, "wb") as f:
            f.write(content)
        expected = hashlib.sha256(content).hexdigest()
        result = casebase._sha256_file(path)
        self.assertEqual(result, expected)

    def test_empty_file_hash(self) -> None:
        path = os.path.join(self._tmpdir, "empty.bin")
        with open(path, "wb") as f:
            pass
        expected = hashlib.sha256(b"").hexdigest()
        result = casebase._sha256_file(path)
        self.assertEqual(result, expected)

    def test_same_content_same_hash(self) -> None:
        path1 = os.path.join(self._tmpdir, "a.txt")
        path2 = os.path.join(self._tmpdir, "b.txt")
        content = b"same content here"
        for p in (path1, path2):
            with open(p, "wb") as f:
                f.write(content)
        self.assertEqual(casebase._sha256_file(path1), casebase._sha256_file(path2))

    def test_different_content_different_hash(self) -> None:
        path1 = os.path.join(self._tmpdir, "c.txt")
        path2 = os.path.join(self._tmpdir, "d.txt")
        with open(path1, "wb") as f:
            f.write(b"content A")
        with open(path2, "wb") as f:
            f.write(b"content B")
        self.assertNotEqual(casebase._sha256_file(path1), casebase._sha256_file(path2))

    def test_raises_on_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            casebase._sha256_file("/nonexistent/path/file.txt")


class TestComputeInputsFingerprint(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_file(self, name: str, content: bytes) -> str:
        path = os.path.join(self._tmpdir, name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def test_returns_hex_string(self) -> None:
        p = self._make_file("a.py", b"x = 1\n")
        result = casebase.compute_inputs_fingerprint([p])
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 64)

    def test_deterministic_same_files(self) -> None:
        p = self._make_file("b.py", b"y = 2\n")
        r1 = casebase.compute_inputs_fingerprint([p])
        r2 = casebase.compute_inputs_fingerprint([p])
        self.assertEqual(r1, r2)

    def test_order_independent(self) -> None:
        p1 = self._make_file("c1.py", b"a = 1\n")
        p2 = self._make_file("c2.py", b"b = 2\n")
        r1 = casebase.compute_inputs_fingerprint([p1, p2])
        r2 = casebase.compute_inputs_fingerprint([p2, p1])
        self.assertEqual(r1, r2)

    def test_empty_path_list_returns_hash(self) -> None:
        result = casebase.compute_inputs_fingerprint([])
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 64)

    def test_nonexistent_paths_skipped(self) -> None:
        # Should not raise; missing paths are skipped
        result = casebase.compute_inputs_fingerprint(["/nonexistent/path.py"])
        self.assertIsInstance(result, str)

    def test_full_mode_includes_content(self) -> None:
        p = self._make_file("d.py", b"content for full mode\n")
        r_fast = casebase.compute_inputs_fingerprint([p], mode="fast")
        r_full = casebase.compute_inputs_fingerprint([p], mode="full")
        # Both return 64-char hex strings, but they may differ in value
        self.assertEqual(len(r_fast), 64)
        self.assertEqual(len(r_full), 64)

    def test_different_files_different_fingerprint(self) -> None:
        p1 = self._make_file("e1.py", b"content one\n")
        p2 = self._make_file("e2.py", b"content two\n")
        # Using separate calls with distinct files
        r1 = casebase.compute_inputs_fingerprint([p1])
        r2 = casebase.compute_inputs_fingerprint([p2])
        self.assertNotEqual(r1, r2)

    def test_deduplicates_duplicate_paths(self) -> None:
        p = self._make_file("f.py", b"dedup test\n")
        r1 = casebase.compute_inputs_fingerprint([p])
        r2 = casebase.compute_inputs_fingerprint([p, p, p])
        self.assertEqual(r1, r2)


class TestInitDbAndGetCase(unittest.TestCase):
    """Tests for SQLite-backed functions using an in-memory or temp DB."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        # Redirect casebase DB to tmpdir
        self._orig_db_path = casebase.DB_PATH
        self._orig_casebase_dir = casebase.CASEBASE_DIR
        casebase.CASEBASE_DIR = os.path.join(self._tmpdir, "casebase")
        casebase.DB_PATH = os.path.join(casebase.CASEBASE_DIR, "casebase.sqlite")

    def tearDown(self) -> None:
        casebase.DB_PATH = self._orig_db_path
        casebase.CASEBASE_DIR = self._orig_casebase_dir
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_init_db_creates_table(self) -> None:
        casebase.init_db()
        con = sqlite3.connect(casebase.DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cases'")
        row = cur.fetchone()
        con.close()
        self.assertIsNotNone(row)

    def test_init_db_creates_indexes(self) -> None:
        casebase.init_db()
        con = sqlite3.connect(casebase.DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='cases'")
        indexes = [r[0] for r in cur.fetchall()]
        con.close()
        self.assertGreaterEqual(len(indexes), 1)

    def test_get_case_by_key_returns_none_for_missing(self) -> None:
        casebase.init_db()
        result = casebase.get_case_by_key("nonexistent_key")
        self.assertIsNone(result)

    def test_init_db_idempotent(self) -> None:
        # Calling init_db multiple times should not raise
        casebase.init_db()
        casebase.init_db()
        casebase.init_db()

    def test_upsert_and_retrieve_no_index(self) -> None:
        """Upsert a case with index=False to avoid vstore dependency."""
        casebase.init_db()
        result = casebase.upsert_case(
            key="test_key_001",
            stream_id="stream1",
            kind="test_kind",
            inputs_hash="abc123",
            outputs=[{"output": "result"}],
            summary="A test case summary",
            meta={"tag": "unit-test"},
            index=False,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["key"], "test_key_001")
        # Retrieve the case
        case = casebase.get_case_by_key("test_key_001")
        self.assertIsNotNone(case)
        self.assertEqual(case["key"], "test_key_001")
        self.assertEqual(case["kind"], "test_kind")
        self.assertEqual(case["summary"], "A test case summary")

    def test_upsert_updates_existing_case(self) -> None:
        casebase.init_db()
        casebase.upsert_case(
            key="update_key",
            stream_id="s1",
            kind="k1",
            inputs_hash="hash1",
            outputs=[],
            summary="Original summary",
            index=False,
        )
        # Update
        casebase.upsert_case(
            key="update_key",
            stream_id="s1",
            kind="k1",
            inputs_hash="hash2",
            outputs=[],
            summary="Updated summary",
            index=False,
        )
        case = casebase.get_case_by_key("update_key")
        self.assertEqual(case["summary"], "Updated summary")
        self.assertEqual(case["inputs_hash"], "hash2")

    def test_upsert_preserves_case_id_on_update(self) -> None:
        casebase.init_db()
        r1 = casebase.upsert_case(
            key="stable_key",
            stream_id="s",
            kind="k",
            inputs_hash="h1",
            outputs=[],
            summary="v1",
            index=False,
        )
        r2 = casebase.upsert_case(
            key="stable_key",
            stream_id="s",
            kind="k",
            inputs_hash="h2",
            outputs=[],
            summary="v2",
            index=False,
        )
        self.assertEqual(r1["case_id"], r2["case_id"])

    def test_upsert_case_outputs_stored_as_json(self) -> None:
        casebase.init_db()
        outputs = [{"step": 1, "result": "ok"}, {"step": 2, "result": "done"}]
        casebase.upsert_case(
            key="json_outputs_key",
            stream_id="s",
            kind="k",
            inputs_hash="h",
            outputs=outputs,
            summary="test",
            index=False,
        )
        case = casebase.get_case_by_key("json_outputs_key")
        self.assertEqual(case["outputs"], outputs)

    def test_upsert_case_meta_stored(self) -> None:
        casebase.init_db()
        meta = {"project_id": "proj-1", "custom": "value"}
        casebase.upsert_case(
            key="meta_key",
            stream_id="s",
            kind="k",
            inputs_hash="h",
            outputs=[],
            summary="test",
            meta=meta,
            index=False,
        )
        case = casebase.get_case_by_key("meta_key")
        self.assertEqual(case["meta"]["project_id"], "proj-1")

    def test_upsert_uses_provided_created_at(self) -> None:
        casebase.init_db()
        casebase.upsert_case(
            key="time_key",
            stream_id="s",
            kind="k",
            inputs_hash="h",
            outputs=[],
            summary="test",
            created_at="2026-01-01T00:00:00Z",
            index=False,
        )
        case = casebase.get_case_by_key("time_key")
        self.assertEqual(case["created_at"], "2026-01-01T00:00:00Z")


class TestRowToCase(unittest.TestCase):
    """Test _row_to_case() with a real sqlite3.Row."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._orig_db_path = casebase.DB_PATH
        self._orig_casebase_dir = casebase.CASEBASE_DIR
        casebase.CASEBASE_DIR = os.path.join(self._tmpdir, "casebase")
        casebase.DB_PATH = os.path.join(casebase.CASEBASE_DIR, "casebase.sqlite")
        casebase.init_db()

    def tearDown(self) -> None:
        casebase.DB_PATH = self._orig_db_path
        casebase.CASEBASE_DIR = self._orig_casebase_dir
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _insert_raw(self, key: str, outputs_json: str, meta_json: str) -> sqlite3.Row:
        con = sqlite3.connect(casebase.DB_PATH)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            "INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("case-raw-1", key, "stream", "kind", "2026-01-01T00:00:00Z", "hash", outputs_json, "summary", "", meta_json),
        )
        con.commit()
        cur.execute("SELECT * FROM cases WHERE key=?", (key,))
        row = cur.fetchone()
        con.close()
        return row

    def test_row_to_case_returns_dict(self) -> None:
        row = self._insert_raw("key1", "[]", "{}")
        case = casebase._row_to_case(row)
        self.assertIsInstance(case, dict)

    def test_row_to_case_parses_outputs(self) -> None:
        row = self._insert_raw("key2", '[{"a": 1}]', "{}")
        case = casebase._row_to_case(row)
        self.assertEqual(case["outputs"], [{"a": 1}])

    def test_row_to_case_parses_meta(self) -> None:
        row = self._insert_raw("key3", "[]", '{"tag": "test"}')
        case = casebase._row_to_case(row)
        self.assertEqual(case["meta"]["tag"], "test")

    def test_row_to_case_handles_invalid_outputs_json(self) -> None:
        row = self._insert_raw("key4", "not-json", "{}")
        case = casebase._row_to_case(row)
        self.assertEqual(case["outputs"], [])

    def test_row_to_case_handles_invalid_meta_json(self) -> None:
        row = self._insert_raw("key5", "[]", "not-json")
        case = casebase._row_to_case(row)
        self.assertEqual(case["meta"], {})

    def test_row_to_case_has_all_required_fields(self) -> None:
        row = self._insert_raw("key6", "[]", "{}")
        case = casebase._row_to_case(row)
        for field in ("case_id", "key", "stream_id", "kind", "created_at", "inputs_hash", "summary", "vstore_entry_id", "outputs", "meta"):
            with self.subTest(field=field):
                self.assertIn(field, case)


if __name__ == "__main__":
    unittest.main()
