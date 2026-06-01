#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_code_evolution_loop.py
Zone: tests
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Tests for code_evolution_loop.py — the autonomous code-improvement loop.
         Verifies: task picking from TODO.md, proposal generation (no file writes),
         dry-run safety, state persistence, Admin GUI endpoint wiring.
Tests: python3 -m unittest noemaforge/tests/test_code_evolution_loop.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Stubs
stub_ver = types.ModuleType("noemaforge_version")
stub_ver.RUNTIME_VERSION = "0.32.2"
sys.modules.setdefault("noemaforge_version", stub_ver)


class TestCodeEvolutionLoop(unittest.TestCase):
    """Core loop behaviour."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        # Create minimal TODO.md with one open task
        docs_dir = Path(self._tmpdir) / "noemaforge" / "docs"
        history_dir = docs_dir / "history"
        docs_dir.mkdir(parents=True)
        history_dir.mkdir(parents=True)
        self._todo_path = docs_dir / "TODO.md"
        self._todo_path.write_text(
            "# TODO\n\n"
            "- [ ] **task-999 (MEDIUM): Add unit tests for the new widget module**\n"
            "  Details: cover create, update, delete paths.\n"
            "- [x] **task-998 (LOW): Already done task** Done 2026-06-01.\n",
            encoding="utf-8",
        )
        (history_dir / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

        # Minimal src dir
        (Path(self._tmpdir) / "noemaforge" / "src").mkdir(parents=True, exist_ok=True)

        # State dir inside tmpdir
        self._state_dir = Path(self._tmpdir) / "code-evolution-state"

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_loop(self, dry_run: bool = True):
        from code_evolution_loop import CodeEvolutionLoop
        from platform_paths import NoemaForgePaths
        paths = NoemaForgePaths(root=Path(self._tmpdir),
                                data_root=Path(self._tmpdir) / "data")
        # Point state dir into tmpdir
        with patch.dict(os.environ, {"NOEMAFORGE_CODE_EVOLUTION_STATE": str(self._state_dir)}):
            loop = CodeEvolutionLoop(
                project_root=Path(self._tmpdir),
                paths=paths,
                python_exe=sys.executable,
                dry_run=dry_run,
            )
        return loop

    # --- pick_next_task -----------------------------------------------------

    def test_picks_first_open_task(self) -> None:
        loop = self._make_loop()
        task = loop.pick_next_task()
        self.assertIsNotNone(task)
        self.assertEqual(task["task_id"], "task-999")
        self.assertEqual(task["priority"], "MEDIUM")
        self.assertIn("widget", task["summary"])

    def test_skips_completed_tasks(self) -> None:
        loop = self._make_loop()
        task = loop.pick_next_task()
        # task-998 is [x] — should not be picked
        self.assertNotEqual(task["task_id"], "task-998")

    def test_returns_none_when_no_open_tasks(self) -> None:
        self._todo_path.write_text("# TODO\n\n- [x] **task-1 (HIGH): Done**\n",
                                   encoding="utf-8")
        loop = self._make_loop()
        task = loop.pick_next_task()
        self.assertIsNone(task)

    def test_picks_from_provided_text(self) -> None:
        from code_evolution_loop import CodeEvolutionLoop
        loop = self._make_loop()
        text = "- [ ] **task-777 (HIGH): Fix critical race condition**\n"
        task = loop.pick_next_task(todo_text=text)
        self.assertEqual(task["task_id"], "task-777")
        self.assertEqual(task["priority"], "HIGH")

    # --- propose_patch (no file writes) ------------------------------------

    def test_propose_does_not_write_source_files(self) -> None:
        """propose_patch() must not modify any source file."""
        src_dir = Path(self._tmpdir) / "noemaforge" / "src"
        before = {f: f.stat().st_mtime for f in src_dir.rglob("*.py")}
        loop = self._make_loop()
        task = loop.pick_next_task()
        analysis = loop.analyze_task(task)
        loop.propose_patch(task, analysis)
        after = {f: f.stat().st_mtime for f in src_dir.rglob("*.py")}
        self.assertEqual(before, after,
                         "propose_patch() must not touch source files")

    def test_proposal_written_to_state_dir(self) -> None:
        loop = self._make_loop()
        task = loop.pick_next_task()
        analysis = loop.analyze_task(task)
        proposal = loop.propose_patch(task, analysis)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        # Check the proposal file was created in state dir
        proposal_files = list(self._state_dir.glob("prop_*.json"))
        self.assertEqual(len(proposal_files), 1,
                         "Exactly one proposal JSON must be written to state dir")

    def test_proposal_has_required_fields(self) -> None:
        loop = self._make_loop()
        task = loop.pick_next_task()
        proposal = loop.propose_patch(task, loop.analyze_task(task))
        for field in ("proposal_id", "task_id", "task_summary", "analysis",
                      "patches", "created_at", "applied", "committed"):
            with self.subTest(field=field):
                self.assertIn(field, proposal)

    def test_proposal_applied_false_by_default(self) -> None:
        loop = self._make_loop()
        task = loop.pick_next_task()
        proposal = loop.propose_patch(task, loop.analyze_task(task))
        self.assertFalse(proposal["applied"])
        self.assertFalse(proposal["committed"])

    # --- dry_run safety -----------------------------------------------------

    def test_apply_patch_no_op_in_dry_run(self) -> None:
        """apply_patch() with dry_run=True must not call patch_fn."""
        called = []
        def fake_patch(p):
            called.append(p)

        loop = self._make_loop(dry_run=True)
        task = loop.pick_next_task()
        proposal = loop.propose_patch(task, loop.analyze_task(task))
        loop.apply_patch(proposal, fake_patch)
        self.assertEqual(called, [], "patch_fn must NOT be called in dry_run mode")
        self.assertFalse(proposal.get("applied"),
                         "proposal.applied must remain False after dry_run apply")

    def test_commit_no_op_in_dry_run(self) -> None:
        loop = self._make_loop(dry_run=True)
        task = loop.pick_next_task()
        proposal = loop.propose_patch(task, loop.analyze_task(task))
        result = loop.commit_changes(proposal)
        self.assertFalse(result, "commit_changes must return False in dry_run")

    def test_commit_refuses_placeholder_patch_file(self) -> None:
        """commit_changes() must not stage the worktree for placeholder proposals."""
        loop = self._make_loop(dry_run=False)
        task = loop.pick_next_task()
        proposal = loop.propose_patch(task, loop.analyze_task(task))
        with patch("code_evolution_loop.subprocess.run") as run_mock:
            result = loop.commit_changes(proposal)
        self.assertFalse(result)
        self.assertEqual(run_mock.call_count, 0, "git must not run without explicit files")
        self.assertEqual(proposal.get("commit_error"), "no_explicit_files_to_stage")

    def test_commit_stages_only_declared_patch_files(self) -> None:
        """commit_changes() must stage only files named in proposal patches."""
        loop = self._make_loop(dry_run=False)
        target = Path(self._tmpdir) / "noemaforge" / "src" / "widget.py"
        target.write_text("x = 1\n", encoding="utf-8")
        proposal = {
            "proposal_id": "prop_task-999_test",
            "task_id": "task-999",
            "task_summary": "Update widget",
            "patches": [{"file": "noemaforge/src/widget.py", "action": "edit"}],
        }
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("code_evolution_loop.subprocess.run", return_value=completed) as run_mock:
            result = loop.commit_changes(proposal)
        self.assertTrue(result)
        first_call = run_mock.call_args_list[0].args[0]
        expected_path = str(Path("noemaforge") / "src" / "widget.py")
        self.assertEqual(first_call, ["git", "add", "--", expected_path])

    def test_run_tests_uses_state_pycache_prefix(self) -> None:
        """Code-evolution checks must not write __pycache__ under source files."""
        target = Path(self._tmpdir) / "noemaforge" / "src" / "widget.py"
        target.write_text("x = 1\n", encoding="utf-8")
        loop = self._make_loop()
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("code_evolution_loop.subprocess.run", return_value=completed) as run_mock:
            result = loop.run_tests()
        self.assertTrue(result["ok"])
        compile_cmd = run_mock.call_args_list[0].args[0]
        self.assertEqual(compile_cmd[0], sys.executable)
        self.assertEqual(compile_cmd[1], "-X")
        self.assertTrue(compile_cmd[2].startswith("pycache_prefix="), compile_cmd)
        self.assertIn(str(self._state_dir / "pycache"), compile_cmd[2])
        self.assertEqual(compile_cmd[3:5], ["-m", "py_compile"])

    # --- run_one_cycle -----------------------------------------------------

    def test_run_one_cycle_returns_task_and_proposal(self) -> None:
        loop = self._make_loop()
        result = loop.run_one_cycle(apply=False)
        self.assertIn("task", result)
        self.assertIsNotNone(result["task"])
        self.assertEqual(result["task"]["task_id"], "task-999")
        self.assertIn("proposal", result)

    def test_run_one_cycle_status_proposed(self) -> None:
        loop = self._make_loop()
        result = loop.run_one_cycle(apply=False)
        self.assertIn(result["status"], {"proposed", "tests_failed"})

    def test_run_one_cycle_no_open_task_returns_gracefully(self) -> None:
        self._todo_path.write_text("# TODO\n\n- [x] **task-1 (HIGH): Done**\n",
                                   encoding="utf-8")
        loop = self._make_loop()
        result = loop.run_one_cycle()
        self.assertEqual(result["status"], "no_open_task")

    # --- state persistence --------------------------------------------------

    def test_last_run_summary_after_cycle(self) -> None:
        loop = self._make_loop()
        loop.run_one_cycle(apply=False)
        summary = loop.last_run_summary()
        self.assertEqual(summary["last_task_id"], "task-999")
        self.assertIsNotNone(summary["last_run_at"])
        self.assertGreater(summary["total_cycles"], 0)

    def test_state_persisted_to_disk(self) -> None:
        loop = self._make_loop()
        loop.run_one_cycle(apply=False)
        state_file = self._state_dir / "code_evolution_state.json"
        self.assertTrue(state_file.exists(), "State file must be created on disk")
        data = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(data["last_task_id"], "task-999")


class TestCodeEvolutionSourceGuards(unittest.TestCase):
    """Source-guard tests for admin_gui_server.py wiring."""

    _ADMIN_SRC = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")

    def test_code_evolution_propose_endpoint_wired(self) -> None:
        """/api/code-evolution/propose must be handled in do_POST."""
        self.assertIn('"/api/code-evolution/propose"', self._ADMIN_SRC,
                      "admin_gui_server must handle /api/code-evolution/propose")

    def test_code_evolution_status_endpoint_wired(self) -> None:
        """/api/code-evolution/status must be handled in HTTP dispatch."""
        self.assertIn('"/api/code-evolution/status"', self._ADMIN_SRC,
                      "admin_gui_server must handle /api/code-evolution/status")

    def test_code_evolution_status_endpoint_is_gettable(self) -> None:
        """/api/code-evolution/status must be available through do_GET."""
        do_get_start = self._ADMIN_SRC.index("def do_GET")
        do_post_start = self._ADMIN_SRC.index("def do_POST")
        do_get_src = self._ADMIN_SRC[do_get_start:do_post_start]
        self.assertIn('"/api/code-evolution/status"', do_get_src)

    def test_code_evolution_propose_method_defined(self) -> None:
        """AdminGuiServer must define code_evolution_propose()."""
        self.assertIn("def code_evolution_propose(self)", self._ADMIN_SRC,
                      "AdminGuiServer must define code_evolution_propose()")

    def test_code_evolution_status_method_defined(self) -> None:
        """AdminGuiServer must define code_evolution_status()."""
        self.assertIn("def code_evolution_status(self)", self._ADMIN_SRC,
                      "AdminGuiServer must define code_evolution_status()")

    def test_platform_paths_imported(self) -> None:
        """admin_gui_server.py must import from platform_paths."""
        self.assertIn("from platform_paths import", self._ADMIN_SRC,
                      "admin_gui_server must import from platform_paths")


if __name__ == "__main__":
    unittest.main()
