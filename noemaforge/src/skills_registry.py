#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/skills_registry.py
Zone: release/package
Version: 0.31.13.alpha
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
# File: src/skills_registry.py
# Purpose: Provide the module 'skills_registry'.
# Invoked by / imported from:
#   - src/toolproxy.py
# Public API / entry functions:
#   - load_registry
#   - list_skills
#   - run_skill
# Inputs:
#   - skill_id
#   - --project-id
#   - Environment: NOEMAFORGE_SKILLS_PATH
#   - Common path inputs: /opt/noemaforge/configs/skills.yaml, /var/lib/noemaforge/outbox/skills
#   - Imports: __future__, datetime, json, os, typing, yaml, task_tools, argparse
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===


import datetime as dt
import json
import os
from typing import Any, Dict, List, Optional

import yaml

import task_tools

CFG_PATH = os.environ.get("NOEMAFORGE_SKILLS_PATH", "/opt/noemaforge/configs/skills.yaml")
OUTBOX = "/var/lib/noemaforge/outbox/skills"


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
#   - src/coordinator_fanout.py
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
# Calls:
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


# === NoemaForge Autodoc Function Header ===
# Function: load_registry(path: str = CFG_PATH)
# Purpose: Implement the routine 'load registry'.
# Inputs:
#   - path: str = CFG_PATH
# Called by:
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/model_registry.py
#   - src/surgeon_auto.py
# Calls:
#   - open, isinstance, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, obj
# === End NoemaForge Autodoc Function Header ===
def load_registry(path: str = CFG_PATH) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = yaml.safe_load(f) or {}
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: list_skills(path: str = CFG_PATH)
# Purpose: Implement the routine 'list skills'.
# Inputs:
#   - path: str = CFG_PATH
# Called by:
#   - src/toolproxy.py
# Calls:
#   - load_registry, get, append, isinstance, str
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - doc, s, skills
# === End NoemaForge Autodoc Function Header ===
def list_skills(path: str = CFG_PATH) -> Dict[str, Any]:
    doc = load_registry(path)
    skills = []
    for s in doc.get("skills", []) or []:
        if not isinstance(s, dict):
            continue
        skills.append(
            {
                "id": str(s.get("id") or ""),
                "title": str(s.get("title") or ""),
                "type": str(s.get("type") or "macro"),
                "description": str(s.get("description") or ""),
                "steps": s.get("steps") or [],
                "bundle": s.get("bundle") or {},
                "flow_id": str(s.get("flow_id") or ""),
                "action": s.get("action") or {},
            }
        )
    return {"ok": True, "skills": skills}


# === NoemaForge Autodoc Function Header ===
# Function: run_skill(skill_id: str, project_id: str = '', inputs: Optional[Dict[str, Any]] = None, actor: str = 'toolproxy')
# Purpose: Implement the routine 'run skill'.
# Inputs:
#   - skill_id: str
#   - project_id: str = ''
#   - inputs: Optional[Dict[str, Any]] = None
#   - actor: str = 'toolproxy'
# Called by:
#   - src/toolproxy.py
# Calls:
#   - load_registry, join, makedirs, get, ValueError, isinstance, str, _nowz, enumerate, dirname, open, dump
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - created, doc, f, inputs, path, run, s, skill, title
# === End NoemaForge Autodoc Function Header ===
def run_skill(
    *,
    skill_id: str,
    project_id: str = "",
    inputs: Optional[Dict[str, Any]] = None,
    actor: str = "toolproxy",
) -> Dict[str, Any]:
    doc = load_registry()
    skill = None
    for s in doc.get("skills", []) or []:
        if isinstance(s, dict) and str(s.get("id") or "") == str(skill_id):
            skill = dict(s)
            break
    if not skill:
        raise ValueError("unknown_skill")
    inputs = inputs if isinstance(inputs, dict) else {}
    run = {
        "skill_id": skill_id,
        "project_id": project_id,
        "type": str(skill.get("type") or "macro"),
        "started_at": _nowz(),
        "inputs": inputs,
        "planned_steps": skill.get("steps") or [],
        "created_tasks": [],
        "bundle": skill.get("bundle") or {},
        "flow_id": skill.get("flow_id") or "",
        "action": skill.get("action") or {},
    }
    if run["type"] == "macro" and project_id:
        for idx, step in enumerate(run["planned_steps"], start=1):
            if not isinstance(step, dict):
                continue
            title = str(step.get("title") or f"{skill_id} step {idx}")
            created = task_tools.create_user_task(
                project_id=project_id,
                title=title,
                description=str(step.get("description") or ""),
                kind=f"skill.{skill_id}",
                status="queued",
                owner=str(step.get("owner") or "dev"),
                priority_class=str(step.get("priority_class") or "normal"),
                metadata={"skill_id": skill_id, "step_index": idx},
                actor=actor,
            )
            run["created_tasks"].append(created.get("task"))
    path = os.path.join(OUTBOX, skill_id, f"{dt.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    run["artifact_path"] = path
    return {"ok": True, "run": run}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("run")
    p.add_argument("skill_id")
    p.add_argument("--project-id", default="")
    ns = ap.parse_args()
    out = list_skills() if ns.cmd == "list" else run_skill(skill_id=ns.skill_id, project_id=ns.project_id)
    print(json.dumps(out, ensure_ascii=False, indent=2))
