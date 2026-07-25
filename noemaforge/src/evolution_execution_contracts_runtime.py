#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/evolution_execution_contracts_runtime.py
Zone: release/package
Version: 0.33.0
Created: 2026-07-18
Modified: 2026-07-18
Purpose: Validate NF-native Evolution execution contracts without launching runtime work.
Inputs: Evolution execution contract schemas and local example set.
Outputs: JSON-compatible validation report.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_evolution_execution_contracts_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


API_VERSION = "noemaforge.evolution-execution/v1"
PROVENANCE = "UAT request findings resolution"
REPORT_KIND = "EvolutionExecutionContractsValidationReport"

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
CONTRACTS_ROOT = PACKAGE_ROOT / "contracts"
DEFAULT_EXAMPLE = PROJECT_ROOT / "prelaunch" / "governance" / "evolution_execution_contracts.example.json"

CONTRACT_KINDS = {
    "EvolutionRun": "evolution_run.schema.json",
    "EvolutionWorkItem": "evolution_work_item.schema.json",
    "EvolutionEvent": "evolution_event.schema.json",
    "EvolutionAgentRequest": "evolution_agent_request.schema.json",
    "EvolutionAgentResult": "evolution_agent_result.schema.json",
    "EvolutionResourceLease": "evolution_resource_lease.schema.json",
    "EvolutionMutationEvidence": "evolution_mutation_evidence.schema.json",
    "EvolutionIndependentReviewEvidence": "evolution_independent_review_evidence.schema.json",
    "EvolutionReleaseGateResult": "evolution_release_gate_result.schema.json",
}

TOP_LEVEL_KEYS = {
    "EvolutionRun": {
        "apiVersion",
        "kind",
        "run_id",
        "created_at",
        "provenance",
        "runtime_neutral",
        "external_reference_policy",
        "safety_invariants",
        "work_items",
        "resource_leases",
        "events",
        "agent_requests",
        "agent_results",
        "mutation_evidence",
        "review_evidence",
        "release_gate_results",
    },
    "EvolutionWorkItem": {
        "apiVersion",
        "kind",
        "work_item_id",
        "run_id",
        "status",
        "provenance",
        "objective",
        "requires_operator_approval",
        "toolproxy_required",
        "allowed_actions",
        "forbidden_actions",
    },
    "EvolutionEvent": {
        "apiVersion",
        "kind",
        "event_id",
        "run_id",
        "work_item_id",
        "created_at",
        "provenance",
        "event_type",
        "severity",
        "message",
        "evidence_ref",
    },
    "EvolutionAgentRequest": {
        "apiVersion",
        "kind",
        "request_id",
        "run_id",
        "work_item_id",
        "created_at",
        "provenance",
        "agent_role",
        "capability_token_ref",
        "toolproxy_required",
        "approval_required",
        "requested_actions",
        "forbidden_actions",
    },
    "EvolutionAgentResult": {
        "apiVersion",
        "kind",
        "result_id",
        "request_id",
        "run_id",
        "created_at",
        "provenance",
        "agent_role",
        "status",
        "artifacts",
        "machine_readable_result",
    },
    "EvolutionResourceLease": {
        "apiVersion",
        "kind",
        "lease_id",
        "run_id",
        "created_at",
        "provenance",
        "resource_kind",
        "exclusive",
        "approval_required",
        "one_active_heavy_worker_limit",
        "expires_at",
    },
    "EvolutionMutationEvidence": {
        "apiVersion",
        "kind",
        "evidence_id",
        "run_id",
        "work_item_id",
        "created_at",
        "provenance",
        "mutation_mode",
        "runtime_neutral",
        "reference_source_policy",
        "artifacts",
    },
    "EvolutionIndependentReviewEvidence": {
        "apiVersion",
        "kind",
        "review_id",
        "run_id",
        "work_item_id",
        "created_at",
        "provenance",
        "producer_agent_id",
        "reviewer_agent_id",
        "reviewed_head",
        "target_head",
        "fresh_until",
        "decision",
        "findings",
    },
    "EvolutionReleaseGateResult": {
        "apiVersion",
        "kind",
        "gate_id",
        "run_id",
        "created_at",
        "provenance",
        "gate_type",
        "status",
        "manual_marker",
        "operator_approved",
        "evidence_refs",
        "failures",
    },
}


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def schema_paths() -> List[Path]:
    return [CONTRACTS_ROOT / filename for filename in CONTRACT_KINDS.values()]


def load_example_set(example_path: Path | str = DEFAULT_EXAMPLE) -> Dict[str, Any]:
    return _load_json(example_path)


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _schema_failures(schema: Mapping[str, Any], *, path: Path) -> List[str]:
    failures: List[str] = []
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        failures.append(f"schema_draft_invalid:{path.name}")
    if not str(schema.get("$id") or "").endswith(path.name):
        failures.append(f"schema_id_invalid:{path.name}")
    if schema.get("type") != "object":
        failures.append(f"schema_type_not_object:{path.name}")
    if schema.get("additionalProperties") is not False:
        failures.append(f"schema_top_level_allows_unknown_fields:{path.name}")
    props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    required = schema.get("required") if isinstance(schema.get("required"), list) else []
    if "apiVersion" not in required or "kind" not in required or "provenance" not in required:
        failures.append(f"schema_required_core_fields_missing:{path.name}")
    if props.get("apiVersion", {}).get("const") != API_VERSION:
        failures.append(f"schema_api_version_const_invalid:{path.name}")
    if props.get("provenance", {}).get("const") != PROVENANCE:
        failures.append(f"schema_provenance_const_invalid:{path.name}")
    return failures


def _base_failures(doc: Mapping[str, Any], expected_kind: str) -> List[str]:
    failures: List[str] = []
    if doc.get("apiVersion") != API_VERSION:
        failures.append(f"{expected_kind}:api_version_invalid")
    if doc.get("kind") != expected_kind:
        failures.append(f"{expected_kind}:kind_invalid")
    if doc.get("provenance") != PROVENANCE:
        failures.append(f"{expected_kind}:provenance_invalid")
    unknown = sorted(set(doc) - TOP_LEVEL_KEYS[expected_kind])
    if unknown:
        failures.append(f"{expected_kind}:unknown_top_level_fields:{','.join(unknown)}")
    return failures


def validate_manual_gate(gate: Mapping[str, Any]) -> List[str]:
    failures = _base_failures(gate, "EvolutionReleaseGateResult")
    if gate.get("gate_type") == "manual" and gate.get("status") == "passed":
        marker = str(gate.get("manual_marker") or "").strip()
        if not marker:
            failures.append("manual_gate_passed_without_manual_marker")
        if gate.get("operator_approved") is not True:
            failures.append("manual_gate_passed_without_operator_approval")
    return failures


def validate_independent_review(review: Mapping[str, Any], *, now: datetime | None = None) -> List[str]:
    failures = _base_failures(review, "EvolutionIndependentReviewEvidence")
    if str(review.get("producer_agent_id") or "") == str(review.get("reviewer_agent_id") or ""):
        failures.append("review_evidence_not_independent")
    if str(review.get("reviewed_head") or "") != str(review.get("target_head") or ""):
        failures.append("review_evidence_stale_head")
    fresh_until = _parse_time(review.get("fresh_until"))
    if fresh_until is None:
        failures.append("review_evidence_fresh_until_invalid")
    else:
        check_time = now or datetime.now(timezone.utc)
        if fresh_until <= check_time:
            failures.append("review_evidence_stale_time")
    return failures


def validate_mutation_evidence(evidence: Mapping[str, Any]) -> List[str]:
    failures = _base_failures(evidence, "EvolutionMutationEvidence")
    if evidence.get("runtime_neutral") is not True:
        failures.append("mutation_evidence_not_runtime_neutral")
    policy = evidence.get("reference_source_policy") if isinstance(evidence.get("reference_source_policy"), dict) else {}
    if policy.get("imported_reference_source") is not False:
        failures.append("mutation_evidence_claims_imported_reference_source")
    if policy.get("shipped_reference_runtime") is not False:
        failures.append("mutation_evidence_claims_shipped_reference_runtime")
    if policy.get("source_sample_disposition") != "local_only_not_shipped":
        failures.append("mutation_evidence_reference_source_not_local_only")
    return failures


def _validate_resource_lease(lease: Mapping[str, Any]) -> List[str]:
    failures = _base_failures(lease, "EvolutionResourceLease")
    if lease.get("resource_kind") in {"heavy_llm", "gpu", "model_worker"}:
        if lease.get("exclusive") is not True:
            failures.append("resource_lease_heavy_not_exclusive")
        if lease.get("approval_required") is not True:
            failures.append("resource_lease_heavy_without_approval")
        if lease.get("one_active_heavy_worker_limit") is not True:
            failures.append("resource_lease_heavy_limit_missing")
    return failures


def _validate_run(run: Mapping[str, Any]) -> List[str]:
    failures = _base_failures(run, "EvolutionRun")
    if run.get("runtime_neutral") is not True:
        failures.append("run_not_runtime_neutral")
    policy = run.get("external_reference_policy") if isinstance(run.get("external_reference_policy"), dict) else {}
    if policy.get("source_samples_local_only") is not True:
        failures.append("run_reference_samples_not_local_only")
    if policy.get("reference_runtime_shipped") is not False:
        failures.append("run_reference_runtime_shipped")
    invariants = run.get("safety_invariants") if isinstance(run.get("safety_invariants"), dict) else {}
    for key in [
        "single_active_heavy_llm",
        "explicit_operator_approval",
        "toolproxy_capability_boundary",
        "contract_epochs_runtime_immutable",
        "no_hidden_llm_media_camera_microphone_gpu_autostart",
    ]:
        if invariants.get(key) is not True:
            failures.append(f"run_invariant_missing:{key}")
    return failures


def validate_contract_doc(doc: Mapping[str, Any], *, now: datetime | None = None) -> List[str]:
    kind = str(doc.get("kind") or "")
    if kind == "EvolutionReleaseGateResult":
        return validate_manual_gate(doc)
    if kind == "EvolutionIndependentReviewEvidence":
        return validate_independent_review(doc, now=now)
    if kind == "EvolutionMutationEvidence":
        return validate_mutation_evidence(doc)
    if kind == "EvolutionResourceLease":
        return _validate_resource_lease(doc)
    if kind == "EvolutionRun":
        return _validate_run(doc)
    if kind in TOP_LEVEL_KEYS:
        return _base_failures(doc, kind)
    return [f"unknown_contract_kind:{kind}"]


def iter_example_contracts(example_set: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    examples = example_set.get("examples") if isinstance(example_set.get("examples"), dict) else {}
    for kind in CONTRACT_KINDS:
        item = examples.get(kind)
        if isinstance(item, dict):
            yield item


def validate_example_set(example_set: Mapping[str, Any], *, now: datetime | None = None) -> Dict[str, Any]:
    failures: List[str] = []
    if example_set.get("apiVersion") != API_VERSION:
        failures.append("example_set_api_version_invalid")
    if example_set.get("kind") != "EvolutionExecutionContractExampleSet":
        failures.append("example_set_kind_invalid")
    if example_set.get("provenance") != PROVENANCE:
        failures.append("example_set_provenance_invalid")
    examples = example_set.get("examples") if isinstance(example_set.get("examples"), dict) else {}
    for kind in CONTRACT_KINDS:
        if kind not in examples:
            failures.append(f"example_missing:{kind}")
    for doc in iter_example_contracts(example_set):
        failures.extend(validate_contract_doc(doc, now=now))
    return {
        "ok": not failures,
        "failures": failures,
        "contract_count": len(CONTRACT_KINDS),
        "example_count": sum(1 for _ in iter_example_contracts(example_set)),
    }


def validate_all(
    *,
    contracts_root: Path = CONTRACTS_ROOT,
    example_path: Path = DEFAULT_EXAMPLE,
    now: datetime | None = None,
) -> Dict[str, Any]:
    failures: List[str] = []
    schema_reports: List[Dict[str, Any]] = []
    for filename in CONTRACT_KINDS.values():
        path = contracts_root / filename
        if not path.exists():
            failures.append(f"schema_missing:{filename}")
            schema_reports.append({"path": str(path), "ok": False, "failures": [f"schema_missing:{filename}"]})
            continue
        schema = _load_json(path)
        schema_failures = _schema_failures(schema, path=path)
        failures.extend(schema_failures)
        schema_reports.append({"path": str(path), "ok": not schema_failures, "failures": schema_failures})

    example_set = load_example_set(example_path)
    example_report = validate_example_set(example_set, now=now)
    failures.extend(example_report["failures"])
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "provenance": PROVENANCE,
        "schema_reports": schema_reports,
        "example_report": example_report,
        "failures": failures,
        "runtime_effects": {
            "starts_processes": False,
            "mutates_github": False,
            "invokes_model": False,
            "mutates_services": False,
            "mutates_live_state": False,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NF-native Evolution execution contracts.")
    parser.add_argument("--contracts-root", default=str(CONTRACTS_ROOT))
    parser.add_argument("--example", default=str(DEFAULT_EXAMPLE))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = validate_all(contracts_root=Path(args.contracts_root), example_path=Path(args.example))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
