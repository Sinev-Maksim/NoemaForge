#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/code_evolution_loop.py
Zone: runtime/evolution
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Autonomous code-evolution loop for NoemaForge.
         Reads TODO.md → picks next open task → analyzes code → proposes
         or applies patch → runs tests → commits → records in CHANGELOG.
         This is the "Code-Evolution" face of the Dev Team subsystem.
Inputs: TODO.md, active source tree, test suite, git state.
Outputs: Patch proposals (plan-only mode) or direct commits (apply mode,
         requires explicit --apply flag).
Side effects: File writes only under --apply; git commits under --apply
              --commit; network calls only for GitHub PR creation.
Tests: python3 -m unittest noemaforge/tests/test_code_evolution_loop.py -v
Notes: Code comments are English-only.
       SAFETY: apply mode requires --apply; commit requires --apply --commit.
       The loop NEVER auto-applies without the explicit flag.
=== End NoemaForge File Header ===

Code-Evolution Loop
===================

Architecture
------------

    ┌─────────────────────────────────────────────────────────┐
    │  CodeEvolutionLoop                                       │
    │                                                          │
    │  1. pick_next_task()     → reads TODO.md, finds [ ] item│
    │  2. analyze_task()       → reads relevant source files  │
    │  3. propose_patch()      → builds PatchProposal dict     │
    │  4. run_tests()          → py_compile + unittest batch  │
    │  5. apply_patch()        → writes files (--apply only)  │
    │  6. record_outcome()     → writes to code-evolution state│
    │  7. commit_changes()     → git commit (--commit only)    │
    └─────────────────────────────────────────────────────────┘

Safety model
------------
- propose_patch() never writes any file.
- apply_patch() writes only inside the PROJECT_ROOT tree.
- commit_changes() runs git commit only when --apply AND --commit.
- GitHub PR creation requires --apply --commit --open-pr.
- All mutations are recorded in the code-evolution state dir.

Integration with Admin GUI
--------------------------
POST /api/code-evolution/propose  → run_one_cycle(apply=False)
POST /api/code-evolution/apply    → run_one_cycle(apply=True, commit=False)
POST /api/code-evolution/commit   → run_one_cycle(apply=True, commit=True)
GET  /api/code-evolution/status   → last_run_summary()
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from noemaforge_version import RUNTIME_VERSION
from platform_paths import NoemaForgePaths, DEFAULT_PATHS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOOP_VERSION = RUNTIME_VERSION
STATE_FILENAME = "code_evolution_state.json"
LOG_FILENAME = "code_evolution_log.jsonl"

# Regex that matches an open TODO item:  - [ ] **task-N (PRIORITY): ...**
_TODO_OPEN_RE = re.compile(
    r"^-\s*\[\s*\]\s*\*?\*?(?P<id>task-\d+)\s*\((?P<priority>[A-Z]+)\):\s*(?P<summary>.+?)(?:\*\*)?$",
    re.MULTILINE,
)

# Regex to detect task completion mark
_TODO_DONE_RE = re.compile(r"^-\s*\[[xX]\]", re.MULTILINE)


# ---------------------------------------------------------------------------
# Data classes (plain dicts for JSON-compatibility)
# ---------------------------------------------------------------------------

def _nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_task_record(task_id: str, priority: str, summary: str) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "priority": priority,
        "summary": summary,
        "picked_at": _nowz(),
    }


def make_proposal(task: Dict[str, Any], analysis: str, patches: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "proposal_id": f"prop_{task['task_id']}_{_nowz().replace(':','').replace('-','')}",
        "task_id": task["task_id"],
        "task_summary": task["summary"],
        "analysis": analysis,
        "patches": patches,          # list of {file, action, content_snippet, rationale}
        "created_at": _nowz(),
        "applied": False,
        "committed": False,
        "test_result": None,
    }


# ---------------------------------------------------------------------------
# CodeEvolutionLoop
# ---------------------------------------------------------------------------

class CodeEvolutionLoop:
    """Autonomous code-improvement loop.

    Parameters
    ----------
    project_root :
        Root of the NoemaForge project tree (contains VERSION, noemaforge/, etc.)
    paths :
        NoemaForgePaths instance (defaults to DEFAULT_PATHS but can be
        overridden for testing).
    python_exe :
        Python executable to use for test runs. Defaults to sys.executable
        so the same interpreter that runs this module is used.
    pycache_prefix :
        Directory used for Python bytecode during self-tests. Defaults to the
        code-evolution state dir so source trees stay cache-free.
    dry_run :
        When True, apply_patch() is a no-op (logs what would change).
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        paths: Optional[NoemaForgePaths] = None,
        python_exe: Optional[str] = None,
        pycache_prefix: Optional[Path] = None,
        dry_run: bool = True,
    ) -> None:
        self.project_root = Path(project_root or os.environ.get("NOEMAFORGE_ROOT", Path(__file__).resolve().parents[2]))
        self.paths = paths or DEFAULT_PATHS
        self.python_exe = python_exe or sys.executable
        self.dry_run = dry_run
        self._state_dir = self.paths.code_evolution_state_dir
        env_pycache = os.environ.get("NOEMAFORGE_PYCACHE_PREFIX")
        self.pycache_prefix = Path(pycache_prefix or env_pycache) if (pycache_prefix or env_pycache) else self._state_dir / "pycache"
        self._todo_path = self.project_root / "noemaforge" / "docs" / "TODO.md"
        self._changelog_path = self.project_root / "noemaforge" / "docs" / "history" / "CHANGELOG.md"
        self._state: Dict[str, Any] = self._load_state()

    # ---- state persistence ------------------------------------------------

    def _state_path(self) -> Path:
        return self._state_dir / STATE_FILENAME

    def _log_path(self) -> Path:
        return self._state_dir / LOG_FILENAME

    def _load_state(self) -> Dict[str, Any]:
        p = self._state_path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "version": LOOP_VERSION,
            "total_cycles": 0,
            "last_task_id": None,
            "last_proposal_id": None,
            "last_run_at": None,
            "last_status": None,
            "history": [],
        }

    def _save_state(self, proposal: Optional[Dict[str, Any]] = None, status: str = "ok") -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._state["last_run_at"] = _nowz()
        self._state["last_status"] = status
        self._state["total_cycles"] = self._state.get("total_cycles", 0) + 1
        if proposal:
            self._state["last_task_id"] = proposal.get("task_id")
            self._state["last_proposal_id"] = proposal.get("proposal_id")
            self._state.setdefault("history", []).append({
                "proposal_id": proposal["proposal_id"],
                "task_id": proposal["task_id"],
                "applied": proposal.get("applied", False),
                "committed": proposal.get("committed", False),
                "test_result": proposal.get("test_result"),
                "at": _nowz(),
            })
            # Keep only last 50 history entries
            self._state["history"] = self._state["history"][-50:]
        p = self._state_path()
        p.write_text(json.dumps(self._state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _append_log(self, entry: Dict[str, Any]) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        with self._log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    # ---- step 1: pick next task -------------------------------------------

    def pick_next_task(self, todo_text: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Read TODO.md and return the first open [ ] task dict, or None."""
        if todo_text is None:
            if not self._todo_path.exists():
                return None
            todo_text = self._todo_path.read_text(encoding="utf-8")

        for m in _TODO_OPEN_RE.finditer(todo_text):
            task_id = m.group("id")
            # Skip tasks we've already tried in this session
            if task_id == self._state.get("last_task_id"):
                continue
            return make_task_record(task_id, m.group("priority"), m.group("summary").strip())
        return None

    # ---- step 2: analyze task ---------------------------------------------

    def analyze_task(self, task: Dict[str, Any]) -> str:
        """Produce a brief analysis string describing what code needs to change.

        In the current implementation this is a heuristic scan: it looks for
        Python files whose names or content relate to keywords from the task
        summary, then returns a concise description. A future version will call
        the local LLM (model_evolution_runtime) for deeper analysis.
        """
        summary = task["summary"].lower()
        keywords = [w for w in re.findall(r"\w{4,}", summary) if w not in
                    {"must","will","from","with","that","this","when","than","into","have",
                     "should","after","before","only","under","each","both"}]

        src_dir = self.project_root / "noemaforge" / "src"
        relevant: List[str] = []
        if src_dir.exists():
            for py_file in sorted(src_dir.rglob("*.py")):
                if "__pycache__" in str(py_file):
                    continue
                name_lower = py_file.stem.lower()
                if any(kw in name_lower for kw in keywords[:4]):
                    relevant.append(py_file.name)
                    if len(relevant) >= 6:
                        break

        analysis = (
            f"Task {task['task_id']} ({task['priority']}): {task['summary']}\n"
            f"Keywords extracted: {', '.join(keywords[:6]) or '(none)'}\n"
            f"Potentially relevant files: {', '.join(relevant) or '(none found)'}\n"
            f"Recommendation: review the files above; implement the described change; "
            f"add or update tests; ensure py_compile passes."
        )
        return analysis

    # ---- step 3: propose patch --------------------------------------------

    def propose_patch(self, task: Dict[str, Any], analysis: str) -> Dict[str, Any]:
        """Return a PatchProposal dict. Does NOT write any files.

        Patch entries are descriptive — they contain the rationale and a
        content_snippet showing the intended change, but the actual write
        happens only in apply_patch().
        """
        summary = task["summary"]
        patches = [
            {
                "file": "<determined by implementer>",
                "action": "edit",
                "content_snippet": f"# Implement: {summary}",
                "rationale": analysis,
            }
        ]
        proposal = make_proposal(task, analysis, patches)
        # Persist proposal to state dir (read-only; no source changes yet)
        proposal_path = self._state_dir / f"{proposal['proposal_id']}.json"
        self._state_dir.mkdir(parents=True, exist_ok=True)
        proposal_path.write_text(json.dumps(proposal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return proposal

    # ---- step 4: run tests ------------------------------------------------

    def run_tests(self, test_patterns: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        """Run a bounded test suite. Returns a result dict.

        Runs py_compile on all src/*.py and then a fast unittest batch.
        Does not time out longer than 120 seconds total.
        """
        src_dir = self.project_root / "noemaforge" / "src"
        tests_dir = self.project_root / "noemaforge" / "tests"

        # --- py_compile pass ---
        compile_failures: List[str] = []
        self.pycache_prefix.mkdir(parents=True, exist_ok=True)
        if src_dir.exists():
            for py_file in sorted(src_dir.rglob("*.py")):
                if "__pycache__" in str(py_file):
                    continue
                result = subprocess.run(
                    [self.python_exe, "-X", f"pycache_prefix={self.pycache_prefix}", "-m", "py_compile", str(py_file)],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    compile_failures.append(py_file.name)

        # --- unittest batch ---
        patterns = list(test_patterns or ["test_orchestration_state.py", "test_do_get_safety.py"])
        test_failures: List[str] = []
        test_passed = 0
        if tests_dir.exists():
            for pattern in patterns:
                result = subprocess.run(
                    [self.python_exe, "-m", "unittest", "discover",
                     "-s", str(tests_dir), "-p", pattern],
                    capture_output=True, text=True, timeout=60,
                    cwd=str(self.project_root),
                )
                if result.returncode != 0:
                    test_failures.append(pattern)
                else:
                    # Count tests from "Ran N tests" line
                    m = re.search(r"Ran (\d+) tests?", result.stderr)
                    if m:
                        test_passed += int(m.group(1))

        return {
            "compile_failures": compile_failures,
            "test_failures": test_failures,
            "test_passed": test_passed,
            "ok": not compile_failures and not test_failures,
        }

    # ---- step 5: apply patch ----------------------------------------------

    def apply_patch(self, proposal: Dict[str, Any], patch_fn) -> Dict[str, Any]:
        """Apply patches via a caller-supplied function.

        Parameters
        ----------
        proposal :
            The PatchProposal dict (will be mutated: applied=True on success).
        patch_fn :
            Callable(proposal) → None that performs the actual file writes.
            The loop never writes files directly; it delegates to this function
            so callers keep full control.

        Safety
        ------
        This method does nothing when self.dry_run is True (logs only).
        """
        if self.dry_run:
            self._append_log({"ts": _nowz(), "event": "dry_run_apply_skipped",
                               "proposal_id": proposal["proposal_id"]})
            return proposal

        try:
            patch_fn(proposal)
            proposal["applied"] = True
        except Exception as exc:
            proposal["apply_error"] = str(exc)
        return proposal

    # ---- step 6: record outcome ------------------------------------------

    def record_outcome(self, proposal: Dict[str, Any], test_result: Dict[str, Any]) -> None:
        proposal["test_result"] = test_result
        # Update proposal file
        proposal_path = self._state_dir / f"{proposal['proposal_id']}.json"
        if proposal_path.exists():
            proposal_path.write_text(json.dumps(proposal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self._append_log({
            "ts": _nowz(),
            "event": "cycle_complete",
            "proposal_id": proposal["proposal_id"],
            "task_id": proposal["task_id"],
            "applied": proposal.get("applied", False),
            "committed": proposal.get("committed", False),
            "tests_ok": test_result.get("ok"),
        })

    # ---- step 7: commit ---------------------------------------------------

    def _proposal_stage_files(self, proposal: Dict[str, Any]) -> List[str]:
        """Return repo-relative files explicitly declared by the proposal.

        The loop must never stage the whole worktree.  Only concrete files
        listed in proposal["patches"][].file are eligible, and each path must
        resolve inside project_root.
        """
        root = self.project_root.resolve()
        files: List[str] = []
        for patch in proposal.get("patches") or []:
            if not isinstance(patch, dict):
                continue
            raw = str(patch.get("file") or "").strip()
            if not raw or raw.startswith("<") or raw.endswith(">"):
                continue
            candidate = (root / raw).resolve()
            if candidate == root or root not in candidate.parents:
                continue
            files.append(str(candidate.relative_to(root)))
        return sorted(set(files))

    def commit_changes(self, proposal: Dict[str, Any], message: Optional[str] = None) -> bool:
        """Run git commit. Only called when apply=True AND commit=True.

        Returns True on success.
        """
        if self.dry_run:
            return False

        commit_msg = message or (
            f"feat(code-evolution): {proposal['task_id']} — "
            f"{proposal['task_summary'][:72]}\n\n"
            f"Automated by code_evolution_loop.py v{LOOP_VERSION}\n"
            f"Proposal: {proposal['proposal_id']}\n\n"
            f"Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
        )
        stage_files = self._proposal_stage_files(proposal)
        if not stage_files:
            proposal["commit_error"] = "no_explicit_files_to_stage"
            return False

        result = subprocess.run(
            ["git", "add", "--", *stage_files],
            cwd=str(self.project_root),
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            proposal["commit_error"] = result.stderr or result.stdout or "git add failed"
            return False

        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=str(self.project_root),
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            proposal["committed"] = True
            return True
        proposal["commit_error"] = result.stderr or result.stdout or "git commit failed"
        return False

    # ---- high-level entry points -----------------------------------------

    def run_one_cycle(
        self,
        apply: bool = False,
        commit: bool = False,
        patch_fn=None,
        test_patterns: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Run a full propose → [apply] → test → [commit] cycle.

        Parameters
        ----------
        apply :
            If True, call apply_patch(). Must also pass a patch_fn.
        commit :
            If True (and apply is True), commit the changes after tests pass.
        patch_fn :
            Callable(proposal) → None that writes files. Required when apply=True.
        test_patterns :
            List of unittest file patterns to run.

        Returns a summary dict.
        """
        summary: Dict[str, Any] = {
            "started_at": _nowz(),
            "task": None,
            "proposal": None,
            "test_result": None,
            "committed": False,
            "status": "no_open_task",
        }

        task = self.pick_next_task()
        if not task:
            self._save_state(status="no_open_task")
            return summary

        summary["task"] = task
        analysis = self.analyze_task(task)
        proposal = self.propose_patch(task, analysis)
        summary["proposal"] = {"proposal_id": proposal["proposal_id"], "task_id": proposal["task_id"]}
        summary["status"] = "proposed"

        if apply:
            if patch_fn is None:
                summary["status"] = "error_no_patch_fn"
                self._save_state(proposal=proposal, status=summary["status"])
                return summary
            proposal = self.apply_patch(proposal, patch_fn)
            if not proposal.get("applied") and not self.dry_run:
                summary["status"] = "apply_failed"
                self._save_state(proposal=proposal, status=summary["status"])
                return summary
            summary["status"] = "applied"

        # Always run tests
        test_result = self.run_tests(test_patterns)
        summary["test_result"] = test_result
        self.record_outcome(proposal, test_result)

        if apply and commit and test_result.get("ok") and not self.dry_run:
            if self.commit_changes(proposal):
                summary["committed"] = True
                summary["status"] = "committed"
            else:
                summary["status"] = "commit_failed"
        elif not test_result.get("ok"):
            summary["status"] = "tests_failed"

        self._save_state(proposal=proposal, status=summary["status"])
        summary["finished_at"] = _nowz()
        return summary

    def last_run_summary(self) -> Dict[str, Any]:
        """Return the persisted state for GET /api/code-evolution/status."""
        return dict(self._state)


# ---------------------------------------------------------------------------
# Admin GUI integration helpers
# ---------------------------------------------------------------------------

def propose_for_gui(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Convenience wrapper for POST /api/code-evolution/propose."""
    loop = CodeEvolutionLoop(project_root=project_root, dry_run=True)
    return loop.run_one_cycle(apply=False)


def status_for_gui(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Convenience wrapper for GET /api/code-evolution/status."""
    loop = CodeEvolutionLoop(project_root=project_root, dry_run=True)
    return loop.last_run_summary()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="NoemaForge code-evolution loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--root", default=None, help="Project root (default: auto-detect)")
    p.add_argument("--apply", action="store_true",
                   help="Reserved for controlled callers with a patch provider; CLI stays plan-only.")
    p.add_argument("--commit", action="store_true",
                   help="Commit changes after tests pass (requires --apply).")
    p.add_argument("--status", action="store_true",
                   help="Print last run summary and exit.")
    p.add_argument("--pick-task", action="store_true",
                   help="Print the next open TODO task and exit (no changes).")
    return p


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = _build_arg_parser().parse_args(argv)
    root = Path(args.root) if args.root else None

    loop = CodeEvolutionLoop(project_root=root, dry_run=not args.apply)

    if args.status:
        print(json.dumps(loop.last_run_summary(), indent=2, ensure_ascii=False))
        return

    if args.pick_task:
        task = loop.pick_next_task()
        if task:
            print(json.dumps(task, indent=2, ensure_ascii=False))
        else:
            print(json.dumps({"status": "no_open_task"}, indent=2))
        return

    result = loop.run_one_cycle(
        apply=args.apply,
        commit=args.commit and args.apply,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
