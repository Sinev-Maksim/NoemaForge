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
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import noema_upgrade as nu  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
