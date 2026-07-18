#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_evolution_contracts.py
Zone: tests
Version: 0.33.0
Created: 2026-07-18
Modified: 2026-07-18
Purpose: Validate NF-native execution contracts for code evolution.
Inputs: JSON Schema files under noemaforge/contracts.
Outputs: pytest assertions only.
Side effects: None.
Tests: pytest -q noemaforge/tests/test_evolution_contracts.py
Notes: UAT request findings resolution; reference implementations remain local-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"
HEAD, OTHER_HEAD, HASH = "a" * 40, "b" * 40, "c" * 64
TS = "2026-07-18T09:00:00Z"


def validate(name: str, payload: dict) -> None:
    schema = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    ).validate(payload)


VALID = {
    "evolution_run.schema.json": {
        "apiVersion": "noemaforge.evolution.run/v1", "kind": "EvolutionRun",
        "run_id": "evo:0330:contracts", "project_id": "noemaforge",
        "mission": "Introduce contract-first execution without changing the active runtime.",
        "status": "planned", "created_at": TS, "updated_at": TS,
        "source_adapter": "current-loop", "policy_epoch": "epoch-00001",
        "exact_base_head": HEAD, "current_stage": "contract_definition",
        "work_item_ids": ["wi:contracts"], "approval_state": "pending",
        "provenance": {
            "classification": "UAT request findings resolution",
            "reference_material": "local-only",
            "external_source_code_imported": False,
        },
    },
    "evolution_work_item.schema.json": {
        "apiVersion": "noemaforge.evolution.work-item/v1", "kind": "EvolutionWorkItem",
        "work_item_id": "wi:contracts", "run_id": "evo:0330:contracts",
        "title": "Define Evolution execution contracts", "status": "ready",
        "risk_class": "R1",
        "task_scope": {
            "repository": "Sinev-Maksim/NoemaForge", "base_ref": "release/0.33.0-dev",
            "allowed_paths": ["noemaforge/contracts/", "noemaforge/tests/"],
            "forbidden_paths": ["noemaforge/systemd/"], "network_allowed": False,
            "privileged_actions_allowed": False,
        },
        "required_skills": ["evolution.contract_definition", "assurance.contract_validation"],
        "assigned_persona": "tatlin", "dependencies": [], "attempt_budget": 3,
        "semantic_attempts_used": 0, "provider_attempts_used": 0,
        "exact_head": HEAD, "blocker_fingerprint": None,
    },
    "evolution_event.schema.json": {
        "apiVersion": "noemaforge.evolution.event/v1", "kind": "EvolutionEvent",
        "event_id": "event:0001", "run_id": "evo:0330:contracts",
        "work_item_id": "wi:contracts", "sequence": 1, "occurred_at": TS,
        "event_type": "run_created", "actor": {"type": "controller", "id": "nf-evolution"},
        "idempotency_key": "evo:0330:contracts:event:0001", "payload": {"status": "planned"},
    },
    "agent_execution_request.schema.json": {
        "apiVersion": "noemaforge.agent.execution-request/v1", "kind": "AgentExecutionRequest",
        "request_id": "agent-request:0001", "run_id": "evo:0330:contracts",
        "work_item_id": "wi:contracts", "persona_id": "grace-hopper",
        "skill_ids": ["engineering.bounded_patch_plan"],
        "provider": {"adapter": "local-code-model", "model": "candidate", "local": True},
        "context_artifacts": ["artifact://context/contracts"], "tool_capabilities": ["fs.read"],
        "resource_requirements": {
            "cpu_slots": 2, "ram_mb": 4096, "vram_mb": 0,
            "network": False, "exclusive_resources": [],
        },
        "token_budget": 8192, "timeout_seconds": 900,
        "workspace": {"id": "worktree:contracts", "mode": "read_only", "exact_head": HEAD},
        "risk_class": "R1", "approval_ref": None, "requested_at": TS,
    },
    "agent_execution_result.schema.json": {
        "apiVersion": "noemaforge.agent.execution-result/v1", "kind": "AgentExecutionResult",
        "request_id": "agent-request:0001", "attempt_id": "attempt:0001",
        "status": "completed", "started_at": TS, "finished_at": "2026-07-18T09:01:00Z",
        "output_artifacts": ["artifact://candidate/contracts"],
        "evidence_refs": ["artifact://logs/contracts"],
        "usage": {
            "input_tokens": 100, "output_tokens": 50, "cached_tokens": 0,
            "wall_seconds": 60.0, "peak_ram_mb": 512, "peak_vram_mb": None,
        },
        "failure": None,
    },
    "resource_lease.schema.json": {
        "apiVersion": "noemaforge.resource.lease/v1", "kind": "ResourceLease",
        "lease_id": "lease:repo:contracts", "resource_type": "read_only_repo",
        "resource_key": "Sinev-Maksim/NoemaForge",
        "holder": {
            "run_id": "evo:0330:contracts", "work_item_id": "wi:contracts",
            "worker_id": "worker:local:1",
        },
        "mode": "shared", "status": "active", "acquired_at": TS,
        "expires_at": "2026-07-18T09:15:00Z",
        "limits": {"max_parallel": 4, "token_budget": 8192, "ram_mb": 4096, "vram_mb": 0},
    },
    "mutation_evidence.schema.json": {
        "apiVersion": "noemaforge.evolution.mutation-evidence/v1", "kind": "MutationEvidence",
        "evidence_id": "mutation:0001", "run_id": "evo:0330:contracts",
        "work_item_id": "wi:contracts", "workspace_id": "worktree:contracts",
        "base_head": HEAD, "candidate_head": OTHER_HEAD,
        "changed_files": ["noemaforge/contracts/evolution_run.schema.json"],
        "diff_sha256": HASH,
        "tests": [{"id": "test_evolution_contracts", "status": "passed", "artifact_ref": "artifact://tests/contracts"}],
        "rollback_ref": "artifact://rollback/contracts", "mutator_persona": "grace-hopper",
        "provenance": {
            "classification": "UAT request findings resolution",
            "reference_material": "local-only", "external_source_code_imported": False,
            "reference_runtime_shipped": False,
        },
        "created_at": TS,
    },
    "review_evidence.schema.json": {
        "apiVersion": "noemaforge.evolution.review-evidence/v1", "kind": "ReviewEvidence",
        "review_id": "review:0001", "run_id": "evo:0330:contracts",
        "work_item_id": "wi:contracts", "reviewed_head": OTHER_HEAD,
        "reviewer_persona": "solon", "mutator_persona": "grace-hopper",
        "reviewer_independent": True, "verdict": "pass", "findings": [],
        "checks": ["schema_valid", "exact_head_verified"], "reviewed_at": TS, "stale": False,
    },
    "release_gate_result.schema.json": {
        "apiVersion": "noemaforge.release.gate-result/v1", "kind": "ReleaseGateResult",
        "gate_id": "gate:manual-uat", "run_id": "evo:0330:contracts",
        "gate_name": "manual_target_host_uat", "evaluated_head": OTHER_HEAD,
        "status": "pass", "evidence_refs": ["artifact://uat/manual"],
        "manual_required": True, "manual_marker_present": True,
        "evaluated_at": TS, "evaluator": "operator",
    },
}


@pytest.mark.parametrize("schema_name,payload", VALID.items())
def test_valid_contract_examples(schema_name: str, payload: dict) -> None:
    validate(schema_name, payload)


def rejects(schema_name: str, payload: dict) -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate(schema_name, payload)


def test_manual_release_gate_requires_real_marker() -> None:
    payload = copy.deepcopy(VALID["release_gate_result.schema.json"])
    payload["manual_marker_present"] = False
    rejects("release_gate_result.schema.json", payload)


def test_review_must_be_independent_and_non_stale() -> None:
    payload = copy.deepcopy(VALID["review_evidence.schema.json"])
    payload["reviewer_independent"] = False
    rejects("review_evidence.schema.json", payload)
    payload = copy.deepcopy(VALID["review_evidence.schema.json"])
    payload["stale"] = True
    rejects("review_evidence.schema.json", payload)


def test_reference_code_cannot_be_imported_or_shipped() -> None:
    payload = copy.deepcopy(VALID["mutation_evidence.schema.json"])
    payload["provenance"]["external_source_code_imported"] = True
    rejects("mutation_evidence.schema.json", payload)
    payload = copy.deepcopy(VALID["mutation_evidence.schema.json"])
    payload["provenance"]["reference_runtime_shipped"] = True
    rejects("mutation_evidence.schema.json", payload)


def test_unknown_fields_are_rejected() -> None:
    payload = copy.deepcopy(VALID["evolution_run.schema.json"])
    payload["implicit_superuser"] = True
    rejects("evolution_run.schema.json", payload)
