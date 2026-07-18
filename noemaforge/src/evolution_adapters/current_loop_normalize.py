"""Normalize current-loop issue and PR state into Evolution work items."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from .current_loop_io import exact_head, integer, read_json, stable_hash


def _status(phase: str) -> str:
    value = str(phase or "").lower()
    if value in {"merged", "completed", "done"}:
        return "completed"
    if any(token in value for token in ("duplicate", "blocked", "quarantine", "failed")):
        return "blocked"
    if any(token in value for token in ("pause", "defer", "waiting")):
        return "paused"
    if value in {"planned", "queued", "discovered"}:
        return "planned"
    return "running"


def _scope(repo: str) -> Dict[str, Any]:
    return {
        "repository": repo,
        "base_ref": None,
        "allowed_paths": [],
        "forbidden_paths": [],
        "network_allowed": True,
        "privileged_actions_allowed": False,
    }


def issue_work_items(root: Path, repo: str, warnings: List[str]) -> Tuple[List[Dict[str, Any]], set[int]]:
    items: List[Dict[str, Any]] = []
    linked_prs: set[int] = set()
    directory = root / "work-items-v51"
    for path in sorted(directory.glob("issue-*.json")) if directory.is_dir() else []:
        relative = str(path.relative_to(root))
        payload = read_json(root, relative, warnings)
        if not payload:
            continue
        issue = integer(payload.get("issue"))
        if issue <= 0:
            warnings.append(f"{relative}:invalid_issue_number")
            continue
        pr = integer(payload.get("pr"))
        reason = str(payload.get("reason") or "")
        if pr > 0:
            linked_prs.add(pr)
        items.append({
            "apiVersion": "noemaforge.evolution.work-item/v1",
            "kind": "EvolutionWorkItem",
            "work_item_id": f"current-loop:issue:{issue}",
            "run_id": "__RUN_ID__",
            "title": f"Resolve issue #{issue}",
            "status": _status(str(payload.get("phase") or "")),
            "risk_class": "R2",
            "task_scope": _scope(repo),
            "required_skills": [
                "engineering.root_cause_analysis",
                "engineering.worktree_mutation",
                "engineering.deterministic_validation",
            ],
            "assigned_persona": None,
            "dependencies": [],
            "attempt_budget": 3,
            "semantic_attempts_used": 0,
            "provider_attempts_used": 0,
            "exact_head": exact_head(payload.get("head")),
            "blocker_fingerprint": stable_hash({
                "issue": issue,
                "phase": payload.get("phase"),
                "reason": reason,
            }) if reason else None,
        })
    return items, linked_prs


def pr_work_items(root: Path, repo: str, linked_prs: set[int], warnings: List[str]) -> List[Dict[str, Any]]:
    paths: List[Path] = []
    for name in ("scheduler", "scheduler-v51", "scheduler-v47"):
        directory = root / name
        if directory.is_dir():
            paths.extend(directory.glob("pr-*.json"))
    items: List[Dict[str, Any]] = []
    for path in sorted(set(paths)):
        relative = str(path.relative_to(root))
        payload = read_json(root, relative, warnings)
        if not payload:
            continue
        pr = integer(payload.get("pr"))
        if pr <= 0 or pr in linked_prs:
            continue
        head = exact_head(payload.get("last_seen_head"))
        trusted = bool(payload.get("history_trusted"))
        reviewed = bool(payload.get("broad_review_done")) and head is not None and payload.get("reviewed_head") == head
        items.append({
            "apiVersion": "noemaforge.evolution.work-item/v1",
            "kind": "EvolutionWorkItem",
            "work_item_id": f"current-loop:pr:{pr}",
            "run_id": "__RUN_ID__",
            "title": f"Review or remediate PR #{pr}",
            "status": "completed" if trusted and reviewed else ("blocked" if not trusted else "running"),
            "risk_class": "R1",
            "task_scope": _scope(repo),
            "required_skills": ["assurance.independent_review", "assurance.exact_head_verification"],
            "assigned_persona": None,
            "dependencies": [],
            "attempt_budget": 3,
            "semantic_attempts_used": 0,
            "provider_attempts_used": 0,
            "exact_head": head,
            "blocker_fingerprint": None if trusted else stable_hash({
                "pr": pr,
                "history_source": payload.get("history_source"),
            }),
        })
    return items
