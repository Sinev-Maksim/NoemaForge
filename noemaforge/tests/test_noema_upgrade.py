#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_noema_upgrade.py
Zone: tests/upgrade
Version: 0.33.0
Created: 2026-06-07
Modified: 2026-06-07
Purpose: Unit tests for noema_upgrade — focus on the data-safety invariants (never delete,
  never overwrite protected user/machine state).
Inputs: temp directories.
Outputs: unittest results.
Side effects: temp dirs only.
Tests: python3 -m unittest test_noema_upgrade
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
import io
import json
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import noema_upgrade as nu  # noqa: E402


def _tar_bytes(files, *, symlink=None, traversal=None):
    """Build an in-memory .tar (gzip) for fetch tests. files: list of (name, content)."""
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w:gz") as tf:
        for name, content in files:
            data = content.encode("utf-8")
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
        if traversal:
            data = b"evil"
            ti = tarfile.TarInfo(traversal)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
        if symlink:
            ti = tarfile.TarInfo(symlink)
            ti.type = tarfile.SYMTYPE
            ti.linkname = "/etc/passwd"
            tf.addfile(ti)
    return bio.getvalue()


def _zip_bytes(files, *, traversal=None):
    """Build an in-memory .zip for fetch tests. files: list of (name, content)."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        for name, content in files:
            zf.writestr(name, content)
        if traversal:
            zf.writestr(traversal, "evil")
    return bio.getvalue()


def _w(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


class NoemaUpgradeTests(unittest.TestCase):
    def _roots(self, stack):
        cur = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        inc = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        return cur, inc

    def test_classification_basic(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur, inc = self._roots(stack)
            _w(cur, "noemaforge/src/app.py", "old")
            _w(inc, "noemaforge/src/app.py", "new")          # replace (managed, in both)
            _w(inc, "noemaforge/src/new_mod.py", "fresh")    # add (new)
            _w(cur, "user_notes.dat", "mine")                # unmanaged, current-only -> kept
            _w(inc, "noemaforge/data.bin", "x")              # unmanaged ext, new -> add
            plan = nu.plan_upgrade(cur, inc)
        self.assertIn("noemaforge/src/app.py", plan["replace"])
        self.assertIn("noemaforge/src/new_mod.py", plan["add"])
        self.assertIn("user_notes.dat", plan["kept_current_only"])

    def test_context_md_is_always_preserved(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur, inc = self._roots(stack)
            _w(cur, "context.md", "MY MACHINE STATE")
            _w(inc, "context.md", "release default context")
            plan = nu.plan_upgrade(cur, inc)
        self.assertIn("context.md", plan["preserve"])
        self.assertNotIn("context.md", plan["replace"])
        self.assertNotIn("context.md", plan["add"])

    def test_protected_dirs_and_secrets_preserved(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur, inc = self._roots(stack)
            _w(inc, "data/db.sqlite", "x")
            _w(inc, "memory/MEMORY.md", "x")
            _w(inc, "sessions/s1.json", "x")
            _w(inc, "secrets/gateway-token.txt", "x")    # protected dir
            _w(inc, "gateway.token", "x")                 # protected suffix
            _w(inc, "tls.key", "x")
            _w(inc, "settings.local", "x")
            # A release schema that merely contains "token" in its NAME must remain upgradable.
            _w(cur, "noemaforge/schemas/capability-token.schema.json", "old")
            _w(inc, "noemaforge/schemas/capability-token.schema.json", "new")
            plan = nu.plan_upgrade(cur, inc)
            for rel in ("data/db.sqlite", "memory/MEMORY.md", "sessions/s1.json",
                        "secrets/gateway-token.txt", "gateway.token", "tls.key", "settings.local"):
                self.assertIn(rel, plan["preserve"], rel)
                self.assertNotIn(rel, plan["add"])
            self.assertIn("noemaforge/schemas/capability-token.schema.json", plan["replace"])
            self.assertNotIn("noemaforge/schemas/capability-token.schema.json", plan["preserve"])

    def test_apply_never_deletes_and_preserves_protected_content(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur, inc = self._roots(stack)
            _w(cur, "context.md", "MY MACHINE STATE")     # protected, modified by user
            _w(cur, "extra_user_file.py", "keep me")       # current-only -> must survive
            _w(cur, "noemaforge/src/app.py", "old")
            _w(inc, "context.md", "release default")        # must NOT overwrite cur context.md
            _w(inc, "noemaforge/src/app.py", "new")         # should replace
            _w(inc, "noemaforge/src/added.py", "added")     # should add
            plan = nu.plan_upgrade(cur, inc)
            result = nu.apply_plan(plan, dry_run=False)
            # Protected content untouched.
            self.assertEqual((cur / "context.md").read_text(encoding="utf-8"), "MY MACHINE STATE")
            # Current-only file not deleted.
            self.assertTrue((cur / "extra_user_file.py").is_file())
            # Managed file replaced; new file added.
            self.assertEqual((cur / "noemaforge/src/app.py").read_text(encoding="utf-8"), "new")
            self.assertEqual((cur / "noemaforge/src/added.py").read_text(encoding="utf-8"), "added")
            self.assertIn("noemaforge/src/app.py", result["applied"])

    def test_apply_dry_run_writes_nothing(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur, inc = self._roots(stack)
            _w(cur, "noemaforge/src/app.py", "old")
            _w(inc, "noemaforge/src/app.py", "new")
            plan = nu.plan_upgrade(cur, inc)
            result = nu.apply_plan(plan, dry_run=True)
            self.assertTrue(result["dry_run"])
            self.assertEqual((cur / "noemaforge/src/app.py").read_text(encoding="utf-8"), "old")

    def test_extra_preserve_glob(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur, inc = self._roots(stack)
            _w(cur, "noemaforge/configs/site.json", "user-tuned")
            _w(inc, "noemaforge/configs/site.json", "release-default")
            plan = nu.plan_upgrade(cur, inc, preserve_globs=["noemaforge/configs/site.json"])
        self.assertIn("noemaforge/configs/site.json", plan["preserve"])
        self.assertNotIn("noemaforge/configs/site.json", plan["replace"])

    def test_cli_plan_and_apply_default_dry_run(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur, inc = self._roots(stack)
            _w(cur, "noemaforge/src/app.py", "old")
            _w(inc, "noemaforge/src/app.py", "new")
            rc_plan = nu.main(["plan", "--current", str(cur), "--incoming", str(inc), "--json"])
            self.assertEqual(rc_plan, 0)
            # apply without --apply must NOT write
            rc_apply = nu.main(["apply", "--current", str(cur), "--incoming", str(inc)])
            self.assertEqual(rc_apply, 0)
            self.assertEqual((cur / "noemaforge/src/app.py").read_text(encoding="utf-8"), "old")


class NoemaUpgradeFetchTests(unittest.TestCase):
    def test_resolve_release_latest_uses_tag_name(self):
        def fake(url):
            self.assertIn("/releases/latest", url)
            return json.dumps({"tag_name": "v0.33.0"}).encode("utf-8")
        rel = nu.resolve_release("owner/repo", None, fetcher=fake)
        self.assertEqual(rel["version"], "v0.33.0")
        self.assertIn("/tarball/v0.33.0", rel["archive_url"])

    def test_resolve_release_explicit_version_no_network(self):
        def boom(url):
            raise AssertionError("should not call network for explicit version")
        rel = nu.resolve_release("owner/repo", "v1.2.3", fetcher=boom)
        self.assertEqual(rel["version"], "v1.2.3")

    def test_resolve_release_rejects_bad_repo(self):
        with self.assertRaises(ValueError):
            nu.resolve_release("not-a-repo", "v1", fetcher=lambda u: b"{}")

    def test_fetch_and_extract_benign_tar(self):
        blob = _tar_bytes([("repo-abc123/app.py", "print(1)"),
                           ("repo-abc123/sub/readme.md", "hi")])
        with tempfile.TemporaryDirectory() as d:
            root = nu.fetch_and_extract("https://x/archive", Path(d), fetcher=lambda u: blob)
            self.assertEqual(root.name, "repo-abc123")
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), "print(1)")
            self.assertTrue((root / "sub" / "readme.md").is_file())

    def test_fetch_and_extract_rejects_path_traversal(self):
        blob = _tar_bytes([("repo/a.py", "ok")], traversal="../escape.txt")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                nu.fetch_and_extract("https://x/archive", Path(d), fetcher=lambda u: blob)

    def test_fetch_and_extract_rejects_symlink_member(self):
        blob = _tar_bytes([("repo/a.py", "ok")], symlink="repo/link")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                nu.fetch_and_extract("https://x/archive", Path(d), fetcher=lambda u: blob)

    def test_fetch_and_extract_enforces_size_cap(self):
        blob = _tar_bytes([("repo/a.py", "x" * 100)])
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                nu.fetch_and_extract("https://x/archive", Path(d),
                                     fetcher=lambda u: blob, max_bytes=10)

    def test_fetch_and_extract_benign_zip(self):
        blob = _zip_bytes([("repo-z/app.py", "print(2)"), ("repo-z/d/note.md", "hi")])
        with tempfile.TemporaryDirectory() as d:
            root = nu.fetch_and_extract("https://x/archive.zip", Path(d), fetcher=lambda u: blob)
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), "print(2)")

    def test_fetch_and_extract_rejects_zip_traversal(self):
        blob = _zip_bytes([("repo/a.py", "ok")], traversal="../zescape.txt")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                nu.fetch_and_extract("https://x/archive.zip", Path(d), fetcher=lambda u: blob)

    def test_fetch_and_extract_raises_on_garbage(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(tarfile.TarError):
                nu.fetch_and_extract("https://x/archive", Path(d),
                                     fetcher=lambda u: b"not-an-archive")

    def test_cli_fetch_handles_corrupt_archive_cleanly(self):
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(nu, "resolve_release",
                                  return_value={"version": "v1", "archive_url": "u", "kind": "tar"}), \
                mock.patch.object(nu, "fetch_and_extract", side_effect=tarfile.ReadError("bad")):
            buf = io.StringIO()
            import contextlib
            with contextlib.redirect_stdout(buf):
                rc = nu.main(["fetch", "--repo", "o/r", "--dest", d])
            self.assertEqual(rc, 1)
            self.assertIn("FAIL: fetch failed", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
