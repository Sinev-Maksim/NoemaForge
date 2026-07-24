#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/code_evolution_uat_preflight.py
Zone: runtime/evolution
Version: 0.33.0
Created: 2026-07-24
Modified: 2026-07-24
Purpose: Exercise the real code-evolution proposal/test pipeline before or at UAT start while proving that the source tree remains unchanged.
Inputs: Project root and isolated code-evolution state directory.
Outputs: Machine-readable UAT preflight report and proposal/test artifacts in the isolated state directory.
Side effects: Writes only code-evolution state, proposal, log, pycache and report artifacts; never applies or commits a patch.
Tests: noemaforge/tests/test_trusted_trigger_integration.py
Notes: UAT continues only when bounded tests execute successfully and both tracked-tree and git-worktree snapshots remain identical.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

from code_evolution_loop import CodeEvolutionLoop, make_task_record

DEFAULT_TEST_PATTERNS = (
    "test_code_evolution_loop.py",
    "test_do_get_safety.py",
    "test_orchestration_state.py",
)
_FALLBACK_ROOTS = (
    "VERSION",
    "noemaforge",
    "docs",
    "ci",
    ".github",
)
_EXCLUDED_PARTS = frozenset(
    {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
    }
)
_PREFLIGHT_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run_git(root: Path, args: Sequence[str]) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as exc:
        return {"ok": False, "stdout": "", "stderr": repr(exc), "returncode": None}
    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
    }


def _hash_file(hasher: "hashlib._Hash", root: Path, path: Path) -> None:
    relative = path.relative_to(root).as_posix()
    hasher.update(relative.encode("utf-8"))
    hasher.update(b"\0")
    if path.is_symlink():
        hasher.update(b"SYMLINK\0")
        hasher.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        hasher.update(b"\0")
        return
    hasher.update(b"FILE\0")
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    hasher.update(b"\0")


def _tracked_paths(root: Path) -> Optional[list[Path]]:
    result = _run_git(root, ["ls-files", "-z"])
    if not result["ok"]:
        return None
    raw = result["stdout"]
    return [root / item for item in raw.split("\0") if item]


def _fallback_paths(root: Path, state_dir: Path) -> Iterable[Path]:
    state_resolved = state_dir.resolve()
    for raw in _FALLBACK_ROOTS:
        candidate = root / raw
        if candidate.is_file() or candidate.is_symlink():
            yield candidate
            continue
        if not candidate.is_dir():
            continue
        for path in sorted(candidate.rglob("*"), key=lambda item: item.as_posix()):
            if any(part in _EXCLUDED_PARTS for part in path.parts):
                continue
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved == state_resolved or state_resolved in resolved.parents:
                continue
            if path.is_file() or path.is_symlink():
                yield path


def _tree_fingerprint(root: Path, state_dir: Path) -> Dict[str, Any]:
    paths = _tracked_paths(root)
    source = "git_tracked_files" if paths is not None else "fallback_roots"
    if paths is None:
        paths = list(_fallback_paths(root, state_dir))
    hasher = hashlib.sha256()
    count = 0
    failures = []
    for path in sorted(paths, key=lambda item: item.as_posix()):
        try:
            if not path.exists() and not path.is_symlink():
                relative = path.relative_to(root).as_posix()
                hasher.update(f"MISSING\0{relative}\0".encode("utf-8"))
            else:
                _hash_file(hasher, root, path)
            count += 1
        except Exception as exc:
            failures.append(f"{path}: {exc}")
    return {
        "source": source,
        "sha256": hasher.hexdigest(),
        "file_count": count,
        "failures": failures,
        "ok": not failures and count > 0,
    }


def _snapshot(root: Path, state_dir: Path) -> Dict[str, Any]:
    head = _run_git(root, ["rev-parse", "HEAD"])
    status = _run_git(root, ["status", "--porcelain=v1", "--untracked-files=all"])
    status_text = status["stdout"] if status["ok"] else ""
    return {
        "observed_at": _now_iso(),
        "git_available": bool(head["ok"] and status["ok"]),
        "git_head": head["stdout"].strip() if head["ok"] else None,
        "git_status_sha256": hashlib.sha256(status_text.encode("utf-8")).hexdigest() if status["ok"] else None,
        "git_status_line_count": len([line for line in status_text.splitlines() if line]),
        "tree": _tree_fingerprint(root, state_dir),
    }


def _snapshots_equal(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, bool]:
    tree_unchanged = (
        before.get("tree", {}).get("ok") is True
        and after.get("tree", {}).get("ok") is True
        and before.get("tree", {}).get("sha256") == after.get("tree", {}).get("sha256")
        and before.get("tree", {}).get("file_count") == after.get("tree", {}).get("file_count")
    )
    if before.get("git_available") and after.get("git_available"):
        git_unchanged = (
            before.get("git_head") == after.get("git_head")
            and before.get("git_status_sha256") == after.get("git_status_sha256")
        )
    else:
        git_unchanged = True
    return {"tree_unchanged": tree_unchanged, "git_unchanged": git_unchanged}


def _busy_report(state: Path, run_id: str) -> Dict[str, Any]:
    report_dir = state / "uat-preflight"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"self-improvement-{_stamp()}-{run_id}.json"
    report = {
        "apiVersion": "noemaforge.code-evolution-uat-preflight/v1",
        "kind": "CodeEvolutionUatPreflight",
        "run_id": run_id,
        "started_at": _now_iso(),
        "completed_at": _now_iso(),
        "ok": False,
        "status": "already_running",
        "mode": "proposal_test_only",
        "apply": False,
        "commit": False,
        "publish": False,
        "reason_codes": ["self_improvement_preflight_already_running"],
        "report_path": str(report_path),
        "allowed_mutation_root": str(state),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def run_uat_self_improvement_preflight(
    *,
    project_root: Path | str,
    state_dir: Path | str,
    test_patterns: Sequence[str] = DEFAULT_TEST_PATTERNS,
) -> Dict[str, Any]:
    root = Path(project_root).resolve()
    state = Path(state_dir).resolve()
    state.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    if not _PREFLIGHT_LOCK.acquire(blocking=False):
        return _busy_report(state, run_id)
    try:
        return _run_locked_preflight(
            root=root,
            state=state,
            run_id=run_id,
            test_patterns=test_patterns,
        )
    finally:
        _PREFLIGHT_LOCK.release()


def _run_locked_preflight(
    *,
    root: Path,
    state: Path,
    run_id: str,
    test_patterns: Sequence[str],
) -> Dict[str, Any]:
    report_dir = state / "uat-preflight"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"self-improvement-{_stamp()}-{run_id}.json"

    before = _snapshot(root, state)
    task = make_task_record(
        f"uat-self-improvement-preflight_{run_id[:12]}",
        "P0",
        "Exercise the self-improvement proposal and bounded-test pipeline without applying, committing or publishing changes.",
    )
    report: Dict[str, Any] = {
        "apiVersion": "noemaforge.code-evolution-uat-preflight/v1",
        "kind": "CodeEvolutionUatPreflight",
        "run_id": run_id,
        "started_at": _now_iso(),
        "ok": False,
        "status": "started",
        "mode": "proposal_test_only",
        "apply": False,
        "commit": False,
        "publish": False,
        "task": task,
        "test_patterns": list(test_patterns),
        "before": before,
        "after": None,
        "invariants": None,
        "proposal": None,
        "test_result": None,
        "report_path": str(report_path),
        "allowed_mutation_root": str(state),
    }

    previous_pycache = os.environ.get("PYTHONPYCACHEPREFIX")
    os.environ["PYTHONPYCACHEPREFIX"] = str(state / "pycache")
    try:
        loop = CodeEvolutionLoop(project_root=root, dry_run=True)
        loop._state_dir = state  # noqa: SLF001 - isolated UAT state boundary.
        loop.pycache_prefix = state / "pycache"
        loop._state = loop._load_state()  # noqa: SLF001
        analysis = loop.analyze_task(task)
        proposal = loop.propose_patch(task, analysis)
        test_result = loop.run_tests(tuple(test_patterns))
        loop.record_outcome(proposal, test_result)
        loop._save_state(  # noqa: SLF001
            proposal=proposal,
            status="uat_preflight_pass" if test_result.get("ok") else "uat_preflight_test_failed",
        )
        report["proposal"] = {
            "proposal_id": proposal.get("proposal_id"),
            "task_id": proposal.get("task_id"),
            "applied": bool(proposal.get("applied")),
            "committed": bool(proposal.get("committed")),
        }
        report["test_result"] = test_result
        report["status"] = "pipeline_exercised"
    except Exception as exc:
        report["status"] = "pipeline_error"
        report["error"] = repr(exc)
    finally:
        if previous_pycache is None:
            os.environ.pop("PYTHONPYCACHEPREFIX", None)
        else:
            os.environ["PYTHONPYCACHEPREFIX"] = previous_pycache

    after = _snapshot(root, state)
    invariants = _snapshots_equal(before, after)
    proposal = report.get("proposal") or {}
    test_result = report.get("test_result") or {}
    invariants.update(
        {
            "proposal_not_applied": proposal.get("applied") is False,
            "proposal_not_committed": proposal.get("committed") is False,
            "bounded_tests_ok": test_result.get("ok") is True,
            "tests_executed": int(test_result.get("test_passed") or 0) > 0,
        }
    )
    report["after"] = after
    report["invariants"] = invariants
    report["ok"] = all(invariants.values()) and report.get("status") == "pipeline_exercised"
    report["status"] = "pass" if report["ok"] else "fail"
    report["completed_at"] = _now_iso()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noemaforge code-evolution-uat-preflight")
    parser.add_argument("--root", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_uat_self_improvement_preflight(
        project_root=Path(args.root),
        state_dir=Path(args.state_dir),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(f"self-improvement UAT preflight: {report['status']}\nreport: {report['report_path']}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
