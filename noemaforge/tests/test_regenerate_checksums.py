#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_regenerate_checksums.py
Zone: tests
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Unit tests for noemaforge/bootstrap/regenerate-checksums.py (new in 0.32.2).
         Validates sha256_file(), collect(), exclusion logic, and CLI behaviour.
Inputs: noemaforge/bootstrap/regenerate-checksums.py functions.
Outputs: unittest assertions only.
Side effects: Creates and removes temporary directories/files via tempfile.
Tests: python3 -m unittest noemaforge/tests/test_regenerate_checksums.py -v
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Load the module under test from its non-importable file name
# (the file is named "regenerate-checksums.py" with a hyphen, so we use
# importlib to load it explicitly rather than relying on Python's import
# machinery which cannot handle hyphens in module names).
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).resolve().parent.parent / "bootstrap" / "regenerate-checksums.py"
_SPEC = importlib.util.spec_from_file_location("regenerate_checksums", _SCRIPT)
_MOD = importlib.util.module_from_spec(_SPEC)  # type: ignore[arg-type]
_SPEC.loader.exec_module(_MOD)  # type: ignore[union-attr]

sha256_file = _MOD.sha256_file
collect = _MOD.collect
EXCLUDE_PATHS = _MOD.EXCLUDE_PATHS
EXCLUDE_SUFFIXES = _MOD.EXCLUDE_SUFFIXES
EXCLUDE_DIRS = _MOD.EXCLUDE_DIRS
EXCLUDE_NAMES = _MOD.EXCLUDE_NAMES
main = _MOD.main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tmpdir() -> Path:
    return Path(tempfile.mkdtemp())


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Tests for sha256_file()
# ---------------------------------------------------------------------------

class TestSha256File(unittest.TestCase):
    """sha256_file() must produce the correct SHA-256 hex digest for a file."""

    def setUp(self) -> None:
        self._tmpdir = _make_tmpdir()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write(self, name: str, data: bytes) -> Path:
        p = self._tmpdir / name
        p.write_bytes(data)
        return p

    def test_empty_file(self) -> None:
        """SHA-256 of an empty file is the well-known constant."""
        p = self._write("empty.txt", b"")
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        self.assertEqual(sha256_file(p), expected)

    def test_known_content(self) -> None:
        """SHA-256 of b'hello world' matches the reference value."""
        data = b"hello world"
        p = self._write("hw.txt", data)
        self.assertEqual(sha256_file(p), _sha256_bytes(data))

    def test_binary_content(self) -> None:
        """SHA-256 of arbitrary binary content is computed correctly."""
        data = bytes(range(256))
        p = self._write("binary.bin", data)
        self.assertEqual(sha256_file(p), _sha256_bytes(data))

    def test_large_file_chunked_correctly(self) -> None:
        """Files larger than one chunk (65 536 bytes) hash correctly."""
        # 3 × 65 536 + 1 to cross two chunk boundaries
        data = b"x" * (65536 * 3 + 1)
        p = self._write("large.bin", data)
        self.assertEqual(sha256_file(p), _sha256_bytes(data))

    def test_returns_lowercase_hex_string(self) -> None:
        """The returned digest is a 64-character lowercase hex string."""
        p = self._write("a.txt", b"abc")
        result = sha256_file(p)
        self.assertEqual(len(result), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in result))

    def test_different_content_gives_different_digest(self) -> None:
        """Two files with different content must have different digests."""
        p1 = self._write("f1.txt", b"content-one")
        p2 = self._write("f2.txt", b"content-two")
        self.assertNotEqual(sha256_file(p1), sha256_file(p2))

    def test_same_content_same_digest(self) -> None:
        """Two files with identical content must have the same digest."""
        data = b"identical content"
        p1 = self._write("f1.txt", data)
        p2 = self._write("f2.txt", data)
        self.assertEqual(sha256_file(p1), sha256_file(p2))


# ---------------------------------------------------------------------------
# Tests for collect()
# ---------------------------------------------------------------------------

class TestCollect(unittest.TestCase):
    """collect() must return sorted (hash, rel_path) pairs with exclusions."""

    def setUp(self) -> None:
        self._tmpdir = _make_tmpdir()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write(self, rel: str, data: bytes = b"x") -> Path:
        p = self._tmpdir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    # --- Basic collection -------------------------------------------------

    def test_empty_dir_returns_empty_list(self) -> None:
        """An empty directory yields no rows."""
        self.assertEqual(collect(self._tmpdir), [])

    def test_single_file_collected(self) -> None:
        """A single regular file is collected once."""
        self._write("hello.txt", b"hi")
        rows = collect(self._tmpdir)
        self.assertEqual(len(rows), 1)
        rel = rows[0][1]
        self.assertEqual(rel, "hello.txt")

    def test_result_is_sorted_by_path(self) -> None:
        """Results are sorted lexicographically by relative path."""
        self._write("z.txt", b"z")
        self._write("a.txt", b"a")
        self._write("m.txt", b"m")
        paths = [r[1] for r in collect(self._tmpdir)]
        self.assertEqual(paths, sorted(paths))

    def test_nested_file_relative_path_uses_posix_separator(self) -> None:
        """Nested file relative paths use forward slash (POSIX)."""
        self._write("sub/nested.txt", b"nested")
        rows = collect(self._tmpdir)
        self.assertEqual(len(rows), 1)
        self.assertIn("/", rows[0][1])
        self.assertNotIn("\\", rows[0][1])

    def test_hash_values_match_sha256_file(self) -> None:
        """The hash in each row matches sha256_file() for that file."""
        data = b"test-data"
        p = self._write("f.txt", data)
        rows = collect(self._tmpdir)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], _sha256_bytes(data))

    # --- Exclusion: checksums/SHA256SUMS ----------------------------------

    def test_checksums_sha256sums_excluded(self) -> None:
        """checksums/SHA256SUMS is excluded from the output."""
        self._write("regular.txt", b"keep")
        self._write("checksums/SHA256SUMS", b"exclude-me")
        rows = collect(self._tmpdir)
        paths = [r[1] for r in rows]
        self.assertIn("regular.txt", paths)
        self.assertNotIn("checksums/SHA256SUMS", paths)

    def test_only_checksums_file_gives_empty(self) -> None:
        """If the only file is checksums/SHA256SUMS, collect returns []."""
        self._write("checksums/SHA256SUMS", b"hash-data")
        self.assertEqual(collect(self._tmpdir), [])

    # --- Exclusion: .pyc files -------------------------------------------

    def test_pyc_files_excluded(self) -> None:
        """Files with .pyc suffix are excluded."""
        self._write("module.py", b"code")
        self._write("module.pyc", b"bytecode")
        rows = collect(self._tmpdir)
        paths = [r[1] for r in rows]
        self.assertIn("module.py", paths)
        self.assertNotIn("module.pyc", paths)

    # --- Exclusion: __pycache__ directory --------------------------------

    def test_pycache_directory_excluded(self) -> None:
        """Files inside __pycache__ are excluded."""
        self._write("src/__pycache__/module.cpython-310.pyc", b"cached")
        self._write("src/module.py", b"source")
        rows = collect(self._tmpdir)
        paths = [r[1] for r in rows]
        self.assertIn("src/module.py", paths)
        self.assertNotIn("src/__pycache__/module.cpython-310.pyc", paths)

    def test_pycache_at_root_excluded(self) -> None:
        """A __pycache__ directory at the root level is also excluded."""
        self._write("__pycache__/foo.pyc", b"x")
        self.assertEqual(collect(self._tmpdir), [])

    # --- Exclusion: llm-gateway binaries ----------------------------------

    def test_noemaforge_llm_gateway_excluded(self) -> None:
        """noemaforge-llm-gateway binary is excluded by name."""
        self._write("noemaforge-llm-gateway", b"ELF")
        self._write("other.sh", b"#!/bin/sh")
        rows = collect(self._tmpdir)
        paths = [r[1] for r in rows]
        self.assertNotIn("noemaforge-llm-gateway", paths)
        self.assertIn("other.sh", paths)

    def test_noemaforge_llm_gateway_exe_excluded(self) -> None:
        """noemaforge-llm-gateway.exe binary is excluded by name."""
        self._write("noemaforge-llm-gateway.exe", b"MZ")
        self.assertEqual(collect(self._tmpdir), [])

    # --- Combined exclusions ----------------------------------------------

    def test_multiple_exclusions_applied_simultaneously(self) -> None:
        """All exclusion rules apply simultaneously without interference."""
        self._write("keep.txt", b"keep")
        self._write("module.pyc", b"bytecode")
        self._write("__pycache__/x.pyc", b"cached")
        self._write("checksums/SHA256SUMS", b"sums")
        self._write("noemaforge-llm-gateway", b"ELF")
        rows = collect(self._tmpdir)
        paths = [r[1] for r in rows]
        self.assertEqual(paths, ["keep.txt"])

    def test_subdirectory_files_collected(self) -> None:
        """Files in regular subdirectories (not excluded) are collected."""
        self._write("src/a.py", b"a")
        self._write("src/b.py", b"b")
        self._write("docs/README.md", b"readme")
        rows = collect(self._tmpdir)
        self.assertEqual(len(rows), 3)

    # --- Edge cases -------------------------------------------------------

    def test_file_whose_name_starts_with_pycache_not_excluded(self) -> None:
        """A file named '__pycache__something' should NOT be excluded (only directory component)."""
        # EXCLUDE_DIRS checks path parts, not file names substring
        # A file at root named similar to __pycache__ but not exactly is kept
        self._write("__pycache__extra/keep.txt", b"x")
        # The directory is named '__pycache__extra', which is NOT in EXCLUDE_DIRS
        rows = collect(self._tmpdir)
        paths = [r[1] for r in rows]
        # Only '__pycache__' exact match is excluded
        self.assertIn("__pycache__extra/keep.txt", paths)


# ---------------------------------------------------------------------------
# Tests for EXCLUDE_* constants
# ---------------------------------------------------------------------------

class TestExcludeConstants(unittest.TestCase):
    """Verify the exclusion constant sets contain the expected values."""

    def test_exclude_paths_contains_checksums(self) -> None:
        self.assertIn("checksums/SHA256SUMS", EXCLUDE_PATHS)

    def test_exclude_suffixes_contains_pyc(self) -> None:
        self.assertIn(".pyc", EXCLUDE_SUFFIXES)

    def test_exclude_dirs_contains_pycache(self) -> None:
        self.assertIn("__pycache__", EXCLUDE_DIRS)

    def test_exclude_names_contains_gateway(self) -> None:
        self.assertIn("noemaforge-llm-gateway", EXCLUDE_NAMES)
        self.assertIn("noemaforge-llm-gateway.exe", EXCLUDE_NAMES)


# ---------------------------------------------------------------------------
# Tests for main() CLI
# ---------------------------------------------------------------------------

class TestMain(unittest.TestCase):
    """main() must write SHA256SUMS correctly and support dry-run."""

    def setUp(self) -> None:
        self._tmpdir = _make_tmpdir()
        self._orig_argv = sys.argv[:]

    def tearDown(self) -> None:
        sys.argv = self._orig_argv
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write(self, rel: str, data: bytes = b"x") -> Path:
        p = self._tmpdir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def test_writes_output_file_by_default(self) -> None:
        """main() writes <root>/checksums/SHA256SUMS when no --out is given."""
        self._write("hello.txt", b"hello")
        sys.argv = ["regenerate-checksums.py", str(self._tmpdir)]
        rc = main()
        self.assertEqual(rc, 0)
        out = self._tmpdir / "checksums" / "SHA256SUMS"
        self.assertTrue(out.exists(), "checksums/SHA256SUMS must be created")

    def test_output_file_format(self) -> None:
        """Each line of the output file must be '<hash>  <path>'."""
        data = b"content"
        self._write("file.txt", data)
        sys.argv = ["regenerate-checksums.py", str(self._tmpdir)]
        main()
        out = self._tmpdir / "checksums" / "SHA256SUMS"
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        parts = lines[0].split("  ", 1)
        self.assertEqual(len(parts), 2)
        digest, rel = parts
        self.assertEqual(len(digest), 64)
        self.assertEqual(rel, "file.txt")
        self.assertEqual(digest, _sha256_bytes(data))

    def test_dry_run_does_not_write_file(self) -> None:
        """--dry-run must not create the checksums/SHA256SUMS file."""
        self._write("file.txt", b"hello")
        sys.argv = ["regenerate-checksums.py", str(self._tmpdir), "--dry-run"]
        rc = main()
        self.assertEqual(rc, 0)
        out = self._tmpdir / "checksums" / "SHA256SUMS"
        self.assertFalse(out.exists(), "Dry-run must not write the output file")

    def test_custom_out_path(self) -> None:
        """--out <path> writes the file to the specified location."""
        self._write("a.txt", b"a")
        custom_out = self._tmpdir / "custom" / "output.txt"
        sys.argv = [
            "regenerate-checksums.py",
            str(self._tmpdir),
            "--out", str(custom_out),
        ]
        rc = main()
        self.assertEqual(rc, 0)
        self.assertTrue(custom_out.exists())

    def test_invalid_root_returns_nonzero(self) -> None:
        """A non-existent root directory must return exit code 1."""
        sys.argv = ["regenerate-checksums.py", "/nonexistent/path/xyz"]
        rc = main()
        self.assertNotEqual(rc, 0)

    def test_output_excludes_checksums_sums_file(self) -> None:
        """The generated SHA256SUMS must not include itself in the listing."""
        self._write("real.txt", b"real")
        # Pre-create a checksums/SHA256SUMS so it exists before collect runs
        self._write("checksums/SHA256SUMS", b"old-sums")
        sys.argv = ["regenerate-checksums.py", str(self._tmpdir)]
        main()
        out = self._tmpdir / "checksums" / "SHA256SUMS"
        content = out.read_text(encoding="utf-8")
        self.assertNotIn("checksums/SHA256SUMS", content)
        self.assertIn("real.txt", content)

    def test_output_is_deterministic(self) -> None:
        """Running main() twice produces identical output files."""
        self._write("b.txt", b"b")
        self._write("a.txt", b"a")
        sys.argv = ["regenerate-checksums.py", str(self._tmpdir)]
        main()
        out = self._tmpdir / "checksums" / "SHA256SUMS"
        first = out.read_text(encoding="utf-8")
        main()
        second = out.read_text(encoding="utf-8")
        self.assertEqual(first, second)

    def test_output_sorted_lexicographically(self) -> None:
        """Output lines appear in lexicographic order of the path component."""
        self._write("z.txt", b"z")
        self._write("a.txt", b"a")
        self._write("m.txt", b"m")
        sys.argv = ["regenerate-checksums.py", str(self._tmpdir)]
        main()
        out = self._tmpdir / "checksums" / "SHA256SUMS"
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        paths = [line.split("  ", 1)[1] for line in lines]
        self.assertEqual(paths, sorted(paths))

    def test_pyc_excluded_from_output(self) -> None:
        """main() output must not include .pyc files."""
        self._write("source.py", b"code")
        self._write("source.pyc", b"bytecode")
        sys.argv = ["regenerate-checksums.py", str(self._tmpdir)]
        main()
        out = self._tmpdir / "checksums" / "SHA256SUMS"
        content = out.read_text(encoding="utf-8")
        self.assertNotIn("source.pyc", content)
        self.assertIn("source.py", content)


if __name__ == "__main__":
    unittest.main()
