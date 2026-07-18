#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/skills_registry.py
Zone: release/package
Version: 0.33.0
Created: 2026-05-14
Modified: 2026-07-18
Purpose: Load, filter and execute skills through persona-purpose, capability and risk policy.
Inputs: Base skills registry, deterministic registry fragments, persona/task contexts.
Outputs: Filtered skill views and local skill-run artifacts.
Side effects: Macro execution may create tasks and writes a local run artifact.
Tests: pytest -q noemaforge/tests/test_evolution_skills_registry.py
Notes: No persona names or Security exception tables are used in access decisions.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

import task_tools
from platform_paths import DEFAULT_PATHS as _pp

CFG_PATH = os.environ.get("NOEMAFORGE_SKILLS_PATH", str(_pp.root / "configs/skills.yaml"))
CFG_DIR = os.environ.get("NOEMAFORGE_SKILLS_DIR", str(_pp.root / "configs/skills.d"))
OUTBOX = str(_pp.data_root / "outbox/skills")
RISK_ORDER = {f"R{level}": level for level in range(5)}


def _nowz() -> str:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None).isoformat() + "Z"


def _load_yaml(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        return payload if isinstance(payload, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def _fragment_paths(root: Optional[str]) -> List[str]:
    base = str(root or CFG_DIR)
    return sorted(set(glob.glob(os.path.join(base, "*.yaml")) + glob.glob(os.path.join(base, "*.yml"))))


def _skill_id(value: Any) -> str:
    return str(value.get("id") or "").strip() if isinstance(value, dict) else ""


def _strings(value: Any) -> Set[str]:
    if not isinstance(value, (list, tuple, set)):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _risk_value(value: Any, default: str = "R0") -> int:
    return RISK_ORDER.get(str(value or default), RISK_ORDER[default])


def load_registry(path: str = CFG_PATH, *, fragments_dir: Optional[str] = None) -> Dict[str, Any]:
    """Load base registry and lexical fragments; duplicate IDs fail closed."""
    base = _load_yaml(path)
    sources: List[Tuple[str, Dict[str, Any]]] = [(path, base)] if base else []
    sources.extend((item, doc) for item in _fragment_paths(fragments_dir) if (doc := _load_yaml(item)))

    skills: Dict[str, Dict[str, Any]] = {}
    source_by_id: Dict[str, str] = {}
    invalid: Set[str] = set()
    errors: List[Dict[str, Any]] = []
    for source, document in sources:
        for raw in document.get("skills", []) or []:
            if not isinstance(raw, dict):
                errors.append({"code": "invalid_skill_record", "source": source})
                continue
            skill_id = _skill_id(raw)
            if not skill_id:
                errors.append({"code": "missing_skill_id", "source": source})
                continue
            if skill_id in skills or skill_id in invalid:
                errors.append({
                    "code": "duplicate_skill_id",
                    "skill_id": skill_id,
                    "sources": sorted({source_by_id.get(skill_id, ""), source} - {""}),
                })
                skills.pop(skill_id, None)
                invalid.add(skill_id)
                continue
            record = dict(raw)
            record["_registry_source"] = source
            skills[skill_id] = record
            source_by_id[skill_id] = source

    return {
        "apiVersion": str(base.get("apiVersion") or "noemaforge.skills/v1"),
        "kind": str(base.get("kind") or "SkillsRegistry"),
        "skills": [skills[key] for key in sorted(skills) if key not in invalid],
        "registry_errors": errors,
        "registry_sources": [source for source, _ in sources],
    }


def evaluate_skill_access(
    skill: Dict[str, Any],
    *,
    persona_context: Optional[Dict[str, Any]],
    task_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate purpose, capability, environment, risk and approval without name exceptions."""
    task = dict(task_context or {})
    default_risk = str((skill.get("risk") or {}).get("default_class") or "R0")
    if persona_context is None:
        return {
            "allowed": not bool(task),
            "reasons": ["persona_context_required"] if task else ["legacy_unscoped_call"],
            "effective_risk": default_risk,
            "approval_required": False,
        }

    persona = dict(persona_context)
    reasons: List[str] = []
    missing_policy = [key for key in ("purpose_tags", "capabilities_required", "risk") if key not in skill]
    if missing_policy:
        reasons.append("skill_policy_metadata_missing:" + ",".join(missing_policy))

    skill_purposes = _strings(skill.get("purpose_tags"))
    persona_purposes = _strings(persona.get("purposes"))
    task_purposes = _strings(task.get("purposes"))
    if task.get("purpose"):
        task_purposes.add(str(task["purpose"]).strip())
    if skill_purposes and "general" not in skill_purposes and not skill_purposes & persona_purposes:
        reasons.append("persona_purpose_mismatch")
    if task_purposes and skill_purposes and "general" not in skill_purposes and not skill_purposes & task_purposes:
        reasons.append("task_purpose_mismatch")

    required = _strings(skill.get("capabilities_required")) | _strings(task.get("required_capabilities"))
    missing = sorted(required - _strings(persona.get("capabilities")))
    if missing:
        reasons.append("missing_capabilities:" + ",".join(missing))
    denied = sorted(required & _strings(task.get("environment_denied_capabilities")))
    if denied:
        reasons.append("environment_denied_capabilities:" + ",".join(denied))

    risk = dict(skill.get("risk") or {})
    effective = max(_risk_value(risk.get("default_class")), _risk_value(task.get("risk_class")))
    if effective > _risk_value(persona.get("autonomy_ceiling")):
        reasons.append("risk_above_persona_ceiling")
    if effective > _risk_value(task.get("environment_risk_ceiling"), "R4"):
        reasons.append("risk_above_environment_ceiling")
    forbidden = risk.get("forbidden_from")
    if forbidden is not None and effective >= _risk_value(forbidden):
        reasons.append("risk_forbidden_for_skill")
    approval_from = risk.get("approval_required_from")
    approval_required = approval_from is not None and effective >= _risk_value(approval_from)
    if approval_required and not bool(task.get("approval_granted")):
        reasons.append("approval_required")

    return {
        "allowed": not reasons,
        "reasons": reasons,
        "effective_risk": f"R{max(0, min(4, effective))}",
        "approval_required": approval_required,
        "persona_id": str(persona.get("persona_id") or ""),
    }


def _summary(skill: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _skill_id(skill),
        "title": str(skill.get("title") or ""),
        "type": str(skill.get("type") or "macro"),
        "description": str(skill.get("description") or ""),
        "steps": skill.get("steps") or [],
        "bundle": skill.get("bundle") or {},
        "flow_id": str(skill.get("flow_id") or ""),
        "action": skill.get("action") or {},
        "purpose_tags": sorted(_strings(skill.get("purpose_tags"))),
        "capabilities_required": sorted(_strings(skill.get("capabilities_required"))),
        "risk": dict(skill.get("risk") or {}),
        "evidence_contract": list(skill.get("evidence_contract") or []),
        "provenance": dict(skill.get("provenance") or {}),
        "status": str(skill.get("status") or ""),
        "registry_source": str(skill.get("_registry_source") or ""),
    }


def list_skills(
    path: str = CFG_PATH,
    *,
    fragments_dir: Optional[str] = None,
    persona_context: Optional[Dict[str, Any]] = None,
    task_context: Optional[Dict[str, Any]] = None,
    include_denied: bool = False,
) -> Dict[str, Any]:
    document = load_registry(path, fragments_dir=fragments_dir)
    visible: List[Dict[str, Any]] = []
    for skill in document.get("skills", []) or []:
        item = _summary(skill)
        decision = evaluate_skill_access(skill, persona_context=persona_context, task_context=task_context)
        if persona_context is not None or task_context:
            item["access"] = decision
        if decision["allowed"] or include_denied:
            visible.append(item)
    return {
        "ok": not bool(document.get("registry_errors")),
        "skills": visible,
        "registry_errors": document.get("registry_errors") or [],
        "registry_sources": document.get("registry_sources") or [],
    }


def run_skill(
    *,
    skill_id: str,
    project_id: str = "",
    inputs: Optional[Dict[str, Any]] = None,
    actor: str = "toolproxy",
    persona_context: Optional[Dict[str, Any]] = None,
    task_context: Optional[Dict[str, Any]] = None,
    path: str = CFG_PATH,
    fragments_dir: Optional[str] = None,
) -> Dict[str, Any]:
    document = load_registry(path, fragments_dir=fragments_dir)
    if document.get("registry_errors"):
        raise ValueError("invalid_skill_registry")
    skill = next((dict(item) for item in document.get("skills", []) if _skill_id(item) == str(skill_id)), None)
    if not skill:
        raise ValueError("unknown_skill")
    decision = evaluate_skill_access(skill, persona_context=persona_context, task_context=task_context)
    if not decision["allowed"]:
        raise PermissionError("skill_access_denied:" + ";".join(decision["reasons"]))

    run = {
        "skill_id": skill_id,
        "project_id": project_id,
        "type": str(skill.get("type") or "macro"),
        "started_at": _nowz(),
        "inputs": inputs if isinstance(inputs, dict) else {},
        "planned_steps": skill.get("steps") or [],
        "created_tasks": [],
        "bundle": skill.get("bundle") or {},
        "flow_id": skill.get("flow_id") or "",
        "action": skill.get("action") or {},
        "access_decision": decision,
        "persona_id": str((persona_context or {}).get("persona_id") or ""),
        "effective_risk": decision["effective_risk"],
    }
    if run["type"] == "macro" and project_id:
        for index, step in enumerate(run["planned_steps"], start=1):
            if not isinstance(step, dict):
                continue
            created = task_tools.create_user_task(
                project_id=project_id,
                title=str(step.get("title") or f"{skill_id} step {index}"),
                description=str(step.get("description") or ""),
                kind=f"skill.{skill_id}",
                status="queued",
                owner=str(step.get("owner") or "dev"),
                priority_class=str(step.get("priority_class") or "normal"),
                metadata={"skill_id": skill_id, "step_index": index},
                actor=actor,
            )
            run["created_tasks"].append(created.get("task"))

    artifact_path = os.path.join(OUTBOX, skill_id, dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ") + ".json")
    os.makedirs(os.path.dirname(artifact_path), exist_ok=True)
    with open(artifact_path, "w", encoding="utf-8") as handle:
        json.dump(run, handle, ensure_ascii=False, indent=2)
    run["artifact_path"] = artifact_path
    return {"ok": True, "run": run}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    command = sub.add_parser("run")
    command.add_argument("skill_id")
    command.add_argument("--project-id", default="")
    args = parser.parse_args()
    result = list_skills() if args.cmd == "list" else run_skill(skill_id=args.skill_id, project_id=args.project_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
