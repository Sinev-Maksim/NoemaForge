#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_evolution_skills_registry.py
Zone: tests
Version: 0.33.0
Created: 2026-07-18
Modified: 2026-07-18
Purpose: Validate purpose/capability/risk-aware skill discovery and execution.
Inputs: Temporary skill registries and the Evolution skill fragment.
Outputs: pytest assertions only.
Side effects: Temporary files only.
Tests: pytest -q noemaforge/tests/test_evolution_skills_registry.py
Notes: Access decisions contain no hardcoded persona-name exceptions.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import skills_registry as registry  # noqa: E402


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _base(skills: list[dict] | None = None) -> dict:
    return {"apiVersion": "noemaforge.skills/v1", "kind": "SkillsRegistry", "skills": skills or []}


def _skill(
    skill_id: str,
    *,
    purposes: list[str],
    capabilities: list[str],
    default: str = "R1",
    approval: str | None = None,
    forbidden: str | None = "R4",
    skill_type: str = "spec",
) -> dict:
    return {
        "id": skill_id,
        "title": skill_id,
        "type": skill_type,
        "description": "test skill",
        "purpose_tags": purposes,
        "capabilities_required": capabilities,
        "risk": {
            "default_class": default,
            "approval_required_from": approval,
            "forbidden_from": forbidden,
        },
        "evidence_contract": [],
        "provenance": {
            "classification": "UAT request findings resolution",
            "reference_material": "local-only",
            "external_source_code_imported": False,
            "source_family": "test",
        },
        "status": "curated",
    }


def test_shipped_evolution_skills_validate_against_contract() -> None:
    schema = json.loads((ROOT / "contracts" / "skill_definition.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    fragment = yaml.safe_load((ROOT / "configs" / "skills.d" / "evolution.yaml").read_text(encoding="utf-8"))
    skills = fragment.get("skills") or []
    assert len(skills) >= 18
    assert len({skill["id"] for skill in skills}) == len(skills)
    for skill in skills:
        jsonschema.Draft202012Validator(schema).validate(skill)


def test_fragments_merge_deterministically_and_duplicates_fail_closed(tmp_path: Path) -> None:
    base = tmp_path / "skills.yaml"
    fragments = tmp_path / "skills.d"
    _write(base, _base([_skill("alpha.skill", purposes=["general"], capabilities=[])]))
    _write(fragments / "10-beta.yaml", {"skills": [_skill("beta.skill", purposes=["general"], capabilities=[])]})
    _write(fragments / "20-duplicate.yaml", {"skills": [_skill("alpha.skill", purposes=["general"], capabilities=[])]})
    document = registry.load_registry(str(base), fragments_dir=str(fragments))
    assert [skill["id"] for skill in document["skills"]] == ["beta.skill"]
    assert document["registry_errors"][0]["code"] == "duplicate_skill_id"
    assert document["registry_errors"][0]["skill_id"] == "alpha.skill"


def test_legacy_listing_remains_unfiltered(tmp_path: Path) -> None:
    base = tmp_path / "skills.yaml"
    _write(base, _base([
        _skill("creative.skill", purposes=["creative.visual"], capabilities=[]),
        _skill("perimeter.skill", purposes=["assurance.perimeter"], capabilities=["network.observe"]),
    ]))
    result = registry.list_skills(str(base), fragments_dir=str(tmp_path / "none"))
    assert result["ok"] is True
    assert {item["id"] for item in result["skills"]} == {"creative.skill", "perimeter.skill"}
    assert all("access" not in item for item in result["skills"])


def test_artist_like_profile_does_not_receive_perimeter_or_mutation_skills(tmp_path: Path) -> None:
    base = tmp_path / "skills.yaml"
    _write(base, _base([
        _skill("creative.skill", purposes=["creative.visual"], capabilities=["artifact.write"]),
        _skill("perimeter.skill", purposes=["assurance.perimeter"], capabilities=["network.observe"]),
        _skill("mutation.skill", purposes=["engineering.code"], capabilities=["fs.write"], default="R2", approval="R2"),
    ]))
    artist = {
        "persona_id": "artist",
        "purposes": ["creative.visual"],
        "capabilities": ["artifact.write"],
        "autonomy_ceiling": "R1",
    }
    visible = registry.list_skills(
        str(base), fragments_dir=str(tmp_path / "none"), persona_context=artist,
        task_context={"purpose": "creative.visual", "risk_class": "R1", "approval_granted": False},
    )
    assert [item["id"] for item in visible["skills"]] == ["creative.skill"]
    audited = registry.list_skills(
        str(base), fragments_dir=str(tmp_path / "none"), persona_context=artist,
        task_context={"purpose": "engineering.code", "risk_class": "R2", "approval_granted": True},
        include_denied=True,
    )
    mutation = next(item for item in audited["skills"] if item["id"] == "mutation.skill")
    assert mutation["access"]["allowed"] is False
    assert "persona_purpose_mismatch" in mutation["access"]["reasons"]
    assert "risk_above_persona_ceiling" in mutation["access"]["reasons"]


@pytest.mark.parametrize(
    "persona,skill,purpose",
    [
        (
            {"persona_id": "scary", "purposes": ["assurance.diagnostics"], "capabilities": ["fs.read", "exec.test"], "autonomy_ceiling": "R3"},
            _skill("diagnose", purposes=["assurance.diagnostics"], capabilities=["fs.read", "exec.test"]),
            "assurance.diagnostics",
        ),
        (
            {"persona_id": "architect", "purposes": ["engineering.architecture"], "capabilities": ["fs.read", "git.read"], "autonomy_ceiling": "R2"},
            _skill("architecture", purposes=["engineering.architecture"], capabilities=["fs.read", "git.read"]),
            "engineering.architecture",
        ),
        (
            {"persona_id": "qa", "purposes": ["assurance.quality"], "capabilities": ["fs.read", "git.read"], "autonomy_ceiling": "R2"},
            _skill("review", purposes=["assurance.quality"], capabilities=["fs.read", "git.read"]),
            "assurance.quality",
        ),
        (
            {"persona_id": "home-assistant", "purposes": ["home.perimeter"], "capabilities": ["network.observe"], "autonomy_ceiling": "R1"},
            _skill("home-inventory", purposes=["home.perimeter"], capabilities=["network.observe"]),
            "home.perimeter",
        ),
    ],
)
def test_persona_label_does_not_matter_when_policy_matches(persona: dict, skill: dict, purpose: str) -> None:
    decision = registry.evaluate_skill_access(
        skill, persona_context=persona,
        task_context={"purpose": purpose, "risk_class": "R1", "approval_granted": False},
    )
    assert decision["allowed"] is True


def test_invocation_risk_cannot_be_lowered_by_default_or_approval() -> None:
    skill = _skill("risky", purposes=["engineering.code"], capabilities=["fs.write"], default="R1", approval="R2")
    persona = {
        "persona_id": "developer", "purposes": ["engineering.code"],
        "capabilities": ["fs.write"], "autonomy_ceiling": "R2",
    }
    decision = registry.evaluate_skill_access(
        skill, persona_context=persona,
        task_context={"purpose": "engineering.code", "risk_class": "R3", "approval_granted": True},
    )
    assert decision["effective_risk"] == "R3"
    assert decision["allowed"] is False
    assert "risk_above_persona_ceiling" in decision["reasons"]


def test_approval_does_not_override_purpose_or_missing_capabilities() -> None:
    skill = _skill("mutate", purposes=["engineering.code"], capabilities=["fs.write"], default="R2", approval="R2")
    persona = {
        "persona_id": "observer", "purposes": ["assurance.quality"],
        "capabilities": ["fs.read"], "autonomy_ceiling": "R4",
    }
    decision = registry.evaluate_skill_access(
        skill, persona_context=persona,
        task_context={"purpose": "engineering.code", "risk_class": "R2", "approval_granted": True},
    )
    assert decision["allowed"] is False
    assert "persona_purpose_mismatch" in decision["reasons"]
    assert any(reason.startswith("missing_capabilities:") for reason in decision["reasons"])


def test_scoped_access_fails_closed_for_unclassified_legacy_skill(tmp_path: Path) -> None:
    base = tmp_path / "skills.yaml"
    _write(base, _base([{
        "id": "legacy.unclassified", "title": "Legacy", "type": "tool",
        "description": "No purpose/capability/risk metadata", "action": {"tool_action": "legacy.action"},
    }]))
    result = registry.list_skills(
        str(base), fragments_dir=str(tmp_path / "none"),
        persona_context={"persona_id": "any", "purposes": ["general"], "capabilities": [], "autonomy_ceiling": "R4"},
        task_context={"purpose": "general", "risk_class": "R0"}, include_denied=True,
    )
    assert result["skills"][0]["access"]["allowed"] is False
    assert any(reason.startswith("skill_policy_metadata_missing:") for reason in result["skills"][0]["access"]["reasons"])


def test_environment_policy_can_deny_capability_and_lower_risk_ceiling() -> None:
    skill = _skill("environment.bound", purposes=["engineering.code"], capabilities=["fs.write"], default="R2", approval="R2")
    persona = {
        "persona_id": "developer", "purposes": ["engineering.code"],
        "capabilities": ["fs.write"], "autonomy_ceiling": "R4",
    }
    decision = registry.evaluate_skill_access(
        skill, persona_context=persona,
        task_context={
            "purpose": "engineering.code", "risk_class": "R2", "approval_granted": True,
            "environment_risk_ceiling": "R1", "environment_denied_capabilities": ["fs.write"],
        },
    )
    assert decision["allowed"] is False
    assert "risk_above_environment_ceiling" in decision["reasons"]
    assert "environment_denied_capabilities:fs.write" in decision["reasons"]


def test_run_skill_denies_before_tasks_or_artifacts_are_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    skill = _skill("restricted.macro", purposes=["assurance.perimeter"], capabilities=["network.observe"], skill_type="macro")
    skill["steps"] = [{"title": "must not run"}]
    base = tmp_path / "skills.yaml"
    _write(base, _base([skill]))
    calls: list[dict] = []
    monkeypatch.setattr(registry.task_tools, "create_user_task", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(registry, "OUTBOX", str(tmp_path / "outbox"))
    with pytest.raises(PermissionError):
        registry.run_skill(
            skill_id="restricted.macro", project_id="p1", path=str(base),
            fragments_dir=str(tmp_path / "none"),
            persona_context={
                "persona_id": "artist", "purposes": ["creative.visual"],
                "capabilities": ["artifact.write"], "autonomy_ceiling": "R1",
            },
            task_context={"purpose": "assurance.perimeter", "risk_class": "R1", "approval_granted": True},
        )
    assert calls == []
    assert not (tmp_path / "outbox").exists()
