#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/graph_patch_provenance_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate graph patch format and provenance schema contracts.
Inputs: Graph patch provenance policy, schema, examples, registry refs and canonical docs.
Outputs: JSON validation reports and summaries.
Side effects: None; this validator never mutates graph state or applies patches.
Tests: noemaforge/tests/test_graph_patch_provenance_runtime.py, QA and performance tests.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


API_VERSION = "noemaforge.graph-patch-provenance/v1"
POLICY_KIND = "GraphPatchProvenancePolicy"
EXAMPLE_KIND = "GraphPatchProvenanceExampleSet"
PATCH_KIND = "GraphPatch"
REPORT_KIND = "GraphPatchProvenanceValidationReport"
POLICY_ID = "graph-patch-provenance-core"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_REVIEW_STATES = {"draft", "review", "approved", "rejected", "applied"}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]*$")
SHA256_RE = re.compile(r"^sha256:[a-fA-F0-9]{64}$")
REQUIRED_PATCH_FIELDS = {
    "apiVersion",
    "kind",
    "patch_id",
    "trace_id",
    "source_graph_ref",
    "source_graph_digest",
    "target_graph_ref",
    "created_at",
    "actor_role",
    "review_state",
    "review_decision",
    "rollback_plan",
    "operations",
}
REQUIRED_OPERATION_FIELDS = {"op_id", "op_type", "entity_type", "payload", "provenance"}
REQUIRED_PROVENANCE_FIELDS = {"source_refs", "artifact_refs", "rationale", "confidence", "created_by_role"}
ALLOWED_OPERATION_TYPES = {
    "add_node",
    "update_node",
    "add_edge",
    "update_edge",
    "annotate_claim",
    "resolve_conflict",
    "attach_artifact",
}
REQUIRED_CONTROLS = {
    "source_graph_digest_required",
    "trace_id_required",
    "actor_role_required",
    "review_decision_required",
    "rollback_plan_required",
    "citations_or_artifact_refs_required",
    "graph_patch_is_not_auto_applied",
    "no_live_graph_mutation",
}
REQUIRED_OUTPUTS = {
    "graph_patch_provenance_summary",
    "graph_patch_schema_contract",
    "operation_type_matrix",
    "provenance_requirements",
    "registry_attachment",
    "docs_changelog_trace",
}
REQUIRED_DOC_REFS = {
    "noemaforge/docs/README.md",
    "noemaforge/docs/TODO.md",
    "noemaforge/docs/reference/PROJECT_CONTEXT.md",
    "noemaforge/docs/backlog/ROADMAP_AND_TODO.md",
    "noemaforge/docs/history/CHANGELOG.md",
    "noemaforge/docs/wiki/pipelines/wiki-incremental-patch-pipeline.md",
}
PRIMARY_TODO = "Add graph patch format and provenance schema."

SRC_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SRC_DIR.parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "graph-patch-provenance-policy.json"


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _display_path(path: Path) -> str:
    return path.as_posix()


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _policy(payload: Dict[str, Any]) -> Dict[str, Any]:
    value = payload.get("policy")
    return value if isinstance(value, dict) else {}


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    return not any(part in {"", ".", ".."} for part in PurePosixPath(text).parts)


def _resolve_ref(ref: str, *, project_root: Path = PROJECT_ROOT, package_root: Path = PACKAGE_ROOT) -> Dict[str, Any]:
    normalized = ref.replace("\\", "/")
    candidates = [project_root / normalized, package_root / normalized]
    if normalized.startswith("noemaforge/"):
        candidates.append(project_root / normalized)
    else:
        candidates.append(project_root / "noemaforge" / normalized)
    checked: List[str] = []
    for candidate in candidates:
        checked.append(_display_path(candidate))
        if candidate.exists():
            return {"ok": True, "ref": ref, "path": _display_path(candidate.resolve()), "checked": checked}
    return {"ok": False, "ref": ref, "path": "", "checked": checked}


def load_policy(path: Path | str = DEFAULT_POLICY) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_example(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _graph_patch_failures(patch: Dict[str, Any], *, allowed_operation_types: set[str] | None = None) -> List[str]:
    failures: List[str] = []
    allowed = allowed_operation_types or ALLOWED_OPERATION_TYPES
    for field in sorted(REQUIRED_PATCH_FIELDS):
        if field not in patch:
            failures.append(f"patch_field_missing:{field}")
    if patch.get("apiVersion") != API_VERSION:
        failures.append("patch_api_version_invalid")
    if patch.get("kind") != PATCH_KIND:
        failures.append("patch_kind_invalid")
    if not SAFE_ID_RE.match(str(patch.get("patch_id") or "")):
        failures.append("patch_id_invalid")
    if not str(patch.get("trace_id") or "").strip():
        failures.append("patch_trace_id_missing")
    if not SHA256_RE.match(str(patch.get("source_graph_digest") or "")):
        failures.append("patch_source_graph_digest_invalid")
    if not str(patch.get("actor_role") or "").strip():
        failures.append("patch_actor_role_missing")
    if str(patch.get("review_state") or "") not in VALID_REVIEW_STATES:
        failures.append("patch_review_state_invalid")
    if not str(patch.get("review_decision") or "").strip():
        failures.append("patch_review_decision_missing")
    rollback = patch.get("rollback_plan") if isinstance(patch.get("rollback_plan"), dict) else {}
    for field in ["strategy", "pre_apply_snapshot_ref", "revert_patch_ref"]:
        if not str(rollback.get(field) or "").strip():
            failures.append(f"patch_rollback_field_missing:{field}")
    operations = patch.get("operations")
    if not isinstance(operations, list) or not operations:
        failures.append("patch_operations_empty")
        operations = []
    seen_ops = set()
    for raw in operations:
        if not isinstance(raw, dict):
            failures.append("patch_operation_not_object")
            continue
        op_id = str(raw.get("op_id") or "")
        if not SAFE_ID_RE.match(op_id):
            failures.append(f"operation_id_invalid:{op_id}")
        if op_id in seen_ops:
            failures.append(f"operation_duplicate:{op_id}")
        seen_ops.add(op_id)
        for field in sorted(REQUIRED_OPERATION_FIELDS):
            if field not in raw:
                failures.append(f"operation_field_missing:{op_id}:{field}")
        op_type = str(raw.get("op_type") or "")
        if op_type not in allowed:
            failures.append(f"operation_type_invalid:{op_id}:{op_type}")
        if not str(raw.get("entity_type") or "").strip():
            failures.append(f"operation_entity_type_missing:{op_id}")
        if not isinstance(raw.get("payload"), dict):
            failures.append(f"operation_payload_not_object:{op_id}")
        provenance = raw.get("provenance") if isinstance(raw.get("provenance"), dict) else {}
        for field in sorted(REQUIRED_PROVENANCE_FIELDS):
            if field not in provenance:
                failures.append(f"provenance_field_missing:{op_id}:{field}")
        source_refs = _as_string_list(provenance.get("source_refs"))
        artifact_refs = _as_string_list(provenance.get("artifact_refs"))
        if not source_refs and not artifact_refs:
            failures.append(f"provenance_refs_empty:{op_id}")
        if not str(provenance.get("rationale") or "").strip():
            failures.append(f"provenance_rationale_missing:{op_id}")
        if not str(provenance.get("created_by_role") or "").strip():
            failures.append(f"provenance_created_by_role_missing:{op_id}")
    return failures


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if payload.get("id") != POLICY_ID:
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if policy.get("mode") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if policy.get("activation_state") != "graph_patch_format_and_provenance_schema":
        failures.append("policy_activation_state_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_graph_mutation"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if policy.get("required_pipeline_ref") != "pipeline:firstboot-model-selection:0.32.1":
        failures.append("policy_required_pipeline_ref_invalid")
    if PRIMARY_TODO not in _as_string_list(policy.get("closed_todo_refs")):
        failures.append("policy_primary_closed_todo_missing")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for control in REQUIRED_CONTROLS:
        if controls.get(control) is not True:
            failures.append(f"policy_control_missing:{control}")
    for field in sorted(REQUIRED_PATCH_FIELDS - set(_as_string_list(policy.get("required_patch_fields")))):
        failures.append(f"policy_patch_field_missing:{field}")
    for field in sorted(REQUIRED_OPERATION_FIELDS - set(_as_string_list(policy.get("required_operation_fields")))):
        failures.append(f"policy_operation_field_missing:{field}")
    for field in sorted(REQUIRED_PROVENANCE_FIELDS - set(_as_string_list(policy.get("required_provenance_fields")))):
        failures.append(f"policy_provenance_field_missing:{field}")
    for op_type in sorted(ALLOWED_OPERATION_TYPES - set(_as_string_list(policy.get("allowed_operation_types")))):
        failures.append(f"policy_operation_type_missing:{op_type}")
    outputs = set(_as_string_list(policy.get("required_outputs")))
    for output in sorted(REQUIRED_OUTPUTS - outputs):
        failures.append(f"policy_required_output_missing:{output}")
    refs = set(_as_string_list(policy.get("required_refs"))) | set(_as_string_list(payload.get("refs")))
    for ref in REQUIRED_DOC_REFS - refs:
        failures.append(f"policy_doc_ref_missing:{ref}")
    return failures


def _ref_failures(payload: Dict[str, Any], *, project_root: Path = PROJECT_ROOT, package_root: Path = PACKAGE_ROOT) -> Dict[str, Any]:
    policy = _policy(payload)
    refs = _as_string_list(payload.get("refs")) + _as_string_list(policy.get("required_refs"))
    failures: List[str] = []
    resolved: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    unsafe: List[str] = []
    for ref in sorted(set(refs)):
        if not _is_safe_relative_ref(ref):
            unsafe.append(ref)
            failures.append(f"unsafe_ref:{ref}")
            continue
        result = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if result["ok"]:
            resolved.append(result)
        else:
            missing.append(result)
            failures.append(f"missing_ref:{ref}")
    return {"failures": failures, "resolved_refs": resolved, "missing_refs": missing, "unsafe_refs": unsafe}


def _example_failures(payload: Dict[str, Any], example_path: Path) -> Dict[str, Any]:
    failures: List[str] = []
    if not example_path.exists():
        return {"failures": [f"example_missing:{_display_path(example_path)}"], "patches": 0}
    example = load_example(example_path)
    if example.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example.get("kind") != EXAMPLE_KIND:
        failures.append("example_kind_invalid")
    patches = example.get("patches") if isinstance(example.get("patches"), list) else []
    allowed = set(_as_string_list(_policy(payload).get("allowed_operation_types"))) or ALLOWED_OPERATION_TYPES
    for idx, patch in enumerate(patches):
        if not isinstance(patch, dict):
            failures.append(f"example_patch_not_object:{idx}")
            continue
        failures.extend(f"example_{item}" for item in _graph_patch_failures(patch, allowed_operation_types=allowed))
    if not patches:
        failures.append("example_patches_empty")
    outputs = set(_as_string_list(_policy(payload).get("required_outputs")))
    for output in sorted(set(_as_string_list(example.get("expected_outputs"))) - outputs):
        failures.append(f"example_output_missing_from_policy:{output}")
    return {"failures": failures, "patches": len(patches)}


def validate_graph_patch_provenance_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    package_root: Path = PACKAGE_ROOT,
) -> Dict[str, Any]:
    policy = _policy(payload)
    ref_report = _ref_failures(payload, project_root=project_root, package_root=package_root)
    example_path = project_root / "prelaunch" / "governance" / "graph_patch_provenance.example.json"
    example_report = _example_failures(payload, example_path)
    failures = _policy_failures(payload) + ref_report["failures"] + example_report["failures"]
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "id": POLICY_ID,
        "version": str(payload.get("version") or ""),
        "generated_at": _nowz(),
        "ok": not failures,
        "failures": failures,
        "graph_patch_provenance_summary": {
            "patch_format_defined": True,
            "schema_contract_present": True,
            "safe_local_validator_only": True,
            "live_graph_mutation": False,
            "allowed_operation_type_count": len(_as_string_list(policy.get("allowed_operation_types"))),
            "required_patch_field_count": len(_as_string_list(policy.get("required_patch_fields"))),
            "required_provenance_field_count": len(_as_string_list(policy.get("required_provenance_fields"))),
            "example_patch_count": example_report["patches"],
        },
        "graph_patch_schema_contract": {
            "patch_fields": _as_string_list(policy.get("required_patch_fields")),
            "operation_fields": _as_string_list(policy.get("required_operation_fields")),
            "provenance_fields": _as_string_list(policy.get("required_provenance_fields")),
        },
        "operation_type_matrix": sorted(_as_string_list(policy.get("allowed_operation_types"))),
        "provenance_requirements": sorted(_as_string_list(policy.get("required_provenance_fields"))),
        "resolved_refs": ref_report["resolved_refs"],
        "missing_refs": ref_report["missing_refs"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge graph patch provenance policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    report = validate_graph_patch_provenance_policy(load_policy(args.policy))
    if args.summary:
        report = {
            "apiVersion": API_VERSION,
            "kind": "GraphPatchProvenanceSummary",
            "id": POLICY_ID,
            "ok": report["ok"],
            "failures": report["failures"],
            "metrics": report["graph_patch_provenance_summary"],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
