#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/coordinator_fanout.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: src/coordinator_fanout.py
# Purpose: Provide the module 'coordinator_fanout'.
# Invoked by / imported from:
#   - src/toolproxy.py
# Public API / entry functions:
#   - fanout
# Inputs:
#   - project_id
#   - prompt
#   - --worker-count
#   - --focus
#   - Common path inputs: /var/lib/noemaforge/outbox/coordinator
#   - Imports: __future__, datetime, json, os, uuid, typing, task_tools, argparse
# Output formats / side effects:
#   - JSON files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===


import datetime as dt
import json
import os
import uuid
from typing import Any, Dict, List, Optional

import task_tools
from platform_paths import DEFAULT_PATHS as _pp

OUTBOX = str(_pp.data_root / "outbox/coordinator")


# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Implement the routine ' nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/bundles.py
#   - src/caps.py
#   - src/casebase.py
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
#   - src/glove_agent.py
# Calls:
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


# === NoemaForge Autodoc Function Header ===
# Function: _slug()
# Purpose: Implement the routine ' slug'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/team_memory_sync.py
#   - src/worktree_manager.py
# Calls:
#   - strftime, uuid4, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _slug() -> str:
    return dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


# === NoemaForge Autodoc Function Header ===
# Function: _default_focuses(worker_count: int)
# Purpose: Implement the routine ' default focuses'.
# Inputs:
#   - worker_count: int
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - max, int
# Returns / emits: List[str]
# Key locals:
#   - base
# === End NoemaForge Autodoc Function Header ===
def _default_focuses(worker_count: int) -> List[str]:
    base = [
        "Codebase reconnaissance and dependency mapping",
        "Implementation options and trade-offs",
        "Verification and regression risks",
        "Migration / rollout plan",
        "Documentation and operator UX",
    ]
    return base[: max(1, int(worker_count))]


# === NoemaForge Autodoc Function Header ===
# Function: fanout(project_id: str, prompt: str, worker_count: int = 3, focus_areas: Optional[List[str]] = None, actor: str = 'toolproxy')
# Purpose: Implement the routine 'fanout'.
# Inputs:
#   - project_id: str
#   - prompt: str
#   - worker_count: int = 3
#   - focus_areas: Optional[List[str]] = None
#   - actor: str = 'toolproxy'
# Called by:
#   - src/toolproxy.py
# Calls:
#   - enumerate, join, makedirs, strip, ValueError, _default_focuses, create_user_task, append, dirname, open, write, get
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - creates directories
#   - appends to logs or files
# Key locals:
#   - created, f, focus_areas, lines, path, report, t, tasks
# === End NoemaForge Autodoc Function Header ===
def fanout(
    *,
    project_id: str,
    prompt: str,
    worker_count: int = 3,
    focus_areas: Optional[List[str]] = None,
    actor: str = "toolproxy",
) -> Dict[str, Any]:
    if not str(project_id).strip():
        raise ValueError("missing_project_id")
    focus_areas = [str(x).strip() for x in (focus_areas or []) if str(x).strip()] or _default_focuses(worker_count)
    tasks = []
    for idx, focus in enumerate(focus_areas, start=1):
        created = task_tools.create_user_task(
            project_id=project_id,
            title=f"Coordinator research #{idx}",
            description=f"{prompt}\n\nFocus: {focus}",
            kind="coordinator.readonly",
            status="queued",
            owner="coordinator_worker",
            priority_class="normal",
            metadata={"read_only": True, "focus": focus},
            actor=actor,
        )
        tasks.append(created.get("task"))
    lines = [
        f"# Coordinator fanout — {project_id}",
        "",
        f"- Generated at: `{_nowz()}`",
        f"- Worker count: `{len(tasks)}`",
        "",
        "## Prompt",
        prompt.strip(),
        "",
        "## Focus areas",
    ]
    for idx, focus in enumerate(focus_areas, start=1):
        lines.append(f"- {idx}. {focus}")
    lines += ["", "## Spawned tasks"]
    for t in tasks:
        lines.append(f"- {t.get('user_task_id')}: {t.get('title')} / {t.get('description')[:120]}")
    report = "\n".join(lines).strip() + "\n"
    path = os.path.join(OUTBOX, project_id, f"{_slug()}-fanout.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    return {"ok": True, "project_id": project_id, "report_path": path, "tasks": tasks}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("project_id")
    ap.add_argument("prompt")
    ap.add_argument("--worker-count", type=int, default=3)
    ap.add_argument("--focus", action="append", default=[])
    ns = ap.parse_args()
    print(json.dumps(fanout(project_id=ns.project_id, prompt=ns.prompt, worker_count=ns.worker_count, focus_areas=ns.focus), ensure_ascii=False, indent=2))
