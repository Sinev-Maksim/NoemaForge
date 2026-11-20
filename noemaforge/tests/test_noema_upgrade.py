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
import hashlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
import unittest.mock as mock
import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import noema_upgrade as nu  # noqa: E402


def _release_tar(files, *, version="0.33.0", topdir="pkg", with_manifest=True, corrupt=False):
    """Build a gzip tarball mimicking a GitHub release (nested under one topdir), optionally with
    a release-manifest.json whose artifact hashes are correct (or corrupted)."""
    members = {f"{topdir}/{rel}": content.encode("utf-8") for rel, content in files}
    if with_manifest:
        artifacts = []
        for rel, content in files:
            b = content.encode("utf-8")
            digest = "0" * 64 if corrupt else hashlib.sha256(b).hexdigest()
            artifacts.append({"path": rel, "sha256": digest, "bytes": len(b)})
        manifest = {"apiVersion": "noemaforge.release-manifest/v1", "version": version,
                    "contract_epoch": "epoch-1", "generated_at": "2026-06-08T00:00:00Z",
                    "artifacts": artifacts}
        members[f"{topdir}/release-manifest.json"] = json.dumps(manifest).encode("utf-8")
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w:gz") as tf:
        for name, data in members.items():
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
    return bio.getvalue()


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


class NoemaUpgradeRunTests(unittest.TestCase):
    FILES = [("noemaforge/src/app.py", "new code"), ("README.md", "hello")]

    def _current(self, stack):
        cur = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        (cur / "noemaforge" / "src").mkdir(parents=True)
        (cur / "noemaforge" / "src" / "app.py").write_text("old code", encoding="utf-8")
        (cur / "context.md").write_text("MY STATE", encoding="utf-8")  # protected
        return cur

    def test_run_verified_dry_run(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur = self._current(stack)
            dest = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            blob = _release_tar(self.FILES)
            res = nu.run_upgrade(cur, "owner/repo", version="v1", fetcher=lambda u: blob, dest=dest)
            self.assertTrue(res["ok"], res)
            self.assertTrue(res["verified"])
            self.assertEqual(res["stage"], "plan")
            self.assertTrue(res["result"]["dry_run"])
            # dry-run wrote nothing
            self.assertEqual((cur / "noemaforge/src/app.py").read_text(encoding="utf-8"), "old code")

    def test_run_apply_writes_and_preserves(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur = self._current(stack)
            dest = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            blob = _release_tar(self.FILES)
            res = nu.run_upgrade(cur, "owner/repo", version="v1", apply=True,
                                 fetcher=lambda u: blob, dest=dest)
            self.assertTrue(res["ok"])
            self.assertEqual((cur / "noemaforge/src/app.py").read_text(encoding="utf-8"), "new code")
            self.assertEqual((cur / "README.md").read_text(encoding="utf-8"), "hello")
            self.assertEqual((cur / "context.md").read_text(encoding="utf-8"), "MY STATE")  # preserved

    def test_run_aborts_on_invalid_manifest(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur = self._current(stack)
            dest = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            blob = _release_tar(self.FILES, corrupt=True)
            res = nu.run_upgrade(cur, "owner/repo", version="v1", fetcher=lambda u: blob, dest=dest)
            self.assertFalse(res["ok"])
            self.assertEqual(res["stage"], "verify")
            self.assertTrue(res["verify_errors"])
            # nothing applied
            self.assertEqual((cur / "noemaforge/src/app.py").read_text(encoding="utf-8"), "old code")

    def test_run_aborts_when_no_manifest_and_not_allowed(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur = self._current(stack)
            dest = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            blob = _release_tar(self.FILES, with_manifest=False)
            res = nu.run_upgrade(cur, "owner/repo", version="v1", fetcher=lambda u: blob, dest=dest)
            self.assertFalse(res["ok"])
            self.assertEqual(res["stage"], "verify")

    def test_run_allow_unverified_proceeds(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur = self._current(stack)
            dest = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            blob = _release_tar(self.FILES, with_manifest=False)
            res = nu.run_upgrade(cur, "owner/repo", version="v1", allow_unverified=True,
                                 fetcher=lambda u: blob, dest=dest)
            self.assertTrue(res["ok"])
            self.assertIsNone(res["verified"])

    def test_cli_run_dry_run_exit_zero(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur = self._current(stack)
            dest = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            blob = _release_tar(self.FILES)
            with mock.patch.object(nu, "_default_fetcher", lambda u, **k: blob):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = nu.main(["run", "--current", str(cur), "--repo", "owner/repo",
                                  "--version", "v1", "--dest", str(dest)])
            self.assertEqual(rc, 0)
            self.assertIn("DRY-RUN", buf.getvalue())


def _write_unit(systemd_dir: Path, name: str, content: str) -> Path:
    p = systemd_dir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _link_wants(systemd_dir: Path, target_name: str, wants_dir: str) -> Path:
    wants = systemd_dir / wants_dir
    wants.mkdir(parents=True, exist_ok=True)
    link = wants / target_name
    # os.symlink can require elevated privileges on Windows; fall back to a plain file
    # that stands in for "an enablement entry exists at this path" -- the function under
    # test only needs the path to exist and be removable, exactly like a real symlink.
    try:
        link.symlink_to(systemd_dir / target_name)
    except OSError:
        link.write_text("", encoding="utf-8")
    return link


LEGACY_UNIT_CONTENT = (
    "[Unit]\n"
    "Description=Legacy BrainOS shutdown stop hook\n"
    "[Service]\n"
    "Type=oneshot\n"
    "ExecStart=/bin/sh -c 'source /usr/local/lib/brainos-common.sh; brainos_stop_all'\n"
    "ExecStop=/usr/local/sbin/brainos-stop\n"
)


class NoemaUpgradeLegacyBrainosCleanupTests(unittest.TestCase):
    """UAT request findings resolution (0.33.0): remove the legacy BrainOS shutdown hook's
    enablement symlinks left over from a BrainOS -> NoemaForge upgrade."""

    def test_fresh_install_no_unit_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            systemd_dir = Path(d)
            result = nu.remove_legacy_brainos_shutdown_hook(systemd_dir)
        self.assertFalse(result["unit_found"])
        self.assertFalse(result["unit_confirmed_legacy"])
        self.assertEqual(result["symlinks_removed"], [])
        self.assertEqual(result["removed_count"], 0)

    def test_brainos_upgrade_scenario_symlinks_removed(self):
        with tempfile.TemporaryDirectory() as d:
            systemd_dir = Path(d)
            _write_unit(systemd_dir, nu.LEGACY_BRAINOS_SHUTDOWN_UNIT_NAME, LEGACY_UNIT_CONTENT)
            link1 = _link_wants(systemd_dir, nu.LEGACY_BRAINOS_SHUTDOWN_UNIT_NAME,
                                "multi-user.target.wants")
            link2 = _link_wants(systemd_dir, nu.LEGACY_BRAINOS_SHUTDOWN_UNIT_NAME,
                                "shutdown.target.wants")
            result = nu.remove_legacy_brainos_shutdown_hook(systemd_dir)
            self.assertTrue(result["unit_found"])
            self.assertTrue(result["unit_confirmed_legacy"])
            self.assertEqual(result["removed_count"], 2)
            self.assertFalse(link1.exists())
            self.assertFalse(link2.exists())
            # The unit file itself is preserved as a forensic artifact, never deleted.
            self.assertTrue((systemd_dir / nu.LEGACY_BRAINOS_SHUTDOWN_UNIT_NAME).is_file())

    def test_reboot_lifecycle_unaffected_other_units_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            systemd_dir = Path(d)
            _write_unit(systemd_dir, nu.LEGACY_BRAINOS_SHUTDOWN_UNIT_NAME, LEGACY_UNIT_CONTENT)
            _link_wants(systemd_dir, nu.LEGACY_BRAINOS_SHUTDOWN_UNIT_NAME, "multi-user.target.wants")
            # A real NoemaForge unit + its own enablement symlink must survive untouched.
            _write_unit(systemd_dir, "noemaforge-llama.service", "[Unit]\nDescription=NoemaForge\n")
            noema_link = _link_wants(systemd_dir, "noemaforge-llama.service", "multi-user.target.wants")
            nu.remove_legacy_brainos_shutdown_hook(systemd_dir)
            self.assertTrue(noema_link.exists())
            self.assertTrue((systemd_dir / "noemaforge-llama.service").is_file())

    def test_idempotent_second_call_is_silent_noop(self):
        with tempfile.TemporaryDirectory() as d:
            systemd_dir = Path(d)
            _write_unit(systemd_dir, nu.LEGACY_BRAINOS_SHUTDOWN_UNIT_NAME, LEGACY_UNIT_CONTENT)
            _link_wants(systemd_dir, nu.LEGACY_BRAINOS_SHUTDOWN_UNIT_NAME, "multi-user.target.wants")
            first = nu.remove_legacy_brainos_shutdown_hook(systemd_dir)
            second = nu.remove_legacy_brainos_shutdown_hook(systemd_dir)
        self.assertEqual(first["removed_count"], 1)
        self.assertTrue(second["unit_found"])
        self.assertTrue(second["unit_confirmed_legacy"])
        self.assertEqual(second["symlinks_removed"], [])
        self.assertEqual(second["removed_count"], 0)

    def test_unrelated_same_named_file_left_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            systemd_dir = Path(d)
            # Same filename, but content has neither BrainOS signature: must not be treated
            # as the legacy artifact, and its enablement symlink must survive.
            _write_unit(systemd_dir, nu.LEGACY_BRAINOS_SHUTDOWN_UNIT_NAME,
                       "[Unit]\nDescription=Unrelated unit that happens to share this name\n")
            link = _link_wants(systemd_dir, nu.LEGACY_BRAINOS_SHUTDOWN_UNIT_NAME,
                               "multi-user.target.wants")
            result = nu.remove_legacy_brainos_shutdown_hook(systemd_dir)
            self.assertTrue(result["unit_found"])
            self.assertFalse(result["unit_confirmed_legacy"])
            self.assertEqual(result["removed_count"], 0)
            self.assertTrue(link.exists())

    def test_run_upgrade_apply_wires_in_cleanup(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            (cur / "noemaforge" / "src").mkdir(parents=True)
            (cur / "noemaforge" / "src" / "app.py").write_text("old code", encoding="utf-8")
            dest = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            systemd_dir = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            _write_unit(systemd_dir, nu.LEGACY_BRAINOS_SHUTDOWN_UNIT_NAME, LEGACY_UNIT_CONTENT)
            _link_wants(systemd_dir, nu.LEGACY_BRAINOS_SHUTDOWN_UNIT_NAME, "multi-user.target.wants")
            blob = _release_tar([("noemaforge/src/app.py", "new code")])
            res = nu.run_upgrade(cur, "owner/repo", version="v1", apply=True,
                                 fetcher=lambda u: blob, dest=dest, systemd_dir=systemd_dir)
        self.assertTrue(res["ok"])
        cleanup = res["legacy_brainos_cleanup"]
        self.assertIsNotNone(cleanup)
        self.assertEqual(cleanup["removed_count"], 1)

    def test_run_upgrade_dry_run_does_not_touch_systemd_state(self):
        import contextlib
        with contextlib.ExitStack() as stack:
            cur = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            (cur / "noemaforge" / "src").mkdir(parents=True)
            (cur / "noemaforge" / "src" / "app.py").write_text("old code", encoding="utf-8")
            dest = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            systemd_dir = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            _write_unit(systemd_dir, nu.LEGACY_BRAINOS_SHUTDOWN_UNIT_NAME, LEGACY_UNIT_CONTENT)
            link = _link_wants(systemd_dir, nu.LEGACY_BRAINOS_SHUTDOWN_UNIT_NAME,
                               "multi-user.target.wants")
            blob = _release_tar([("noemaforge/src/app.py", "new code")])
            res = nu.run_upgrade(cur, "owner/repo", version="v1", apply=False,
                                 fetcher=lambda u: blob, dest=dest, systemd_dir=systemd_dir)
            self.assertTrue(res["ok"])
            self.assertIsNone(res["legacy_brainos_cleanup"])
            self.assertTrue(link.exists())


if __name__ == "__main__":
    unittest.main()
