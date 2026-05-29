#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/artifact_registry_table_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate artifact registry table contracts for outputs, reviews and graph patches.
Inputs: Artifact registry table policy and local example records.
Outputs: JSON-compatible ArtifactRegistryTableValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_artifact_registry_table_runtime.py, QA and performance tests.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence


API_VERSION = "noemaforge.artifact-registry-table/v1"
POLICY_KIND = "ArtifactRegistryTablePolicy"
EXAMPLE_KIND = "ArtifactRegistryTableExampleSet"
REPORT_KIND = "ArtifactRegistryTableValidationReport"
POLICY_ID = "artifact-registry-table-core"
PRIMARY_TODO = "Add artifact registry table for outputs/reviews/graph patches."

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "artifact-registry-table-policy.json"
DEFAULT_EXAMPLE = PROJECT_ROOT / "prelaunch" / "governance" / "artifact_registry_table.example.json"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_TABLES = ["outputs", "reviews", "graph_patches"]
REQUIRED_COLUMNS = [
    "artifact_id",
    "table",
    "artifact_type",
    "path",
    "sha256",
    "trace_id",
    "producer",
    "review_state",
    "graph_patch_ref",
    "created_at",
]
SUMMARY_FIELDS = [
    "record_count",
    "table_counts",
    "review_state_counts",
    "graph_patch_records",
    "hashed_records",
]
REQUIRED_CONTROLS = [
    "sha256_required",
    "relative_paths_only",
    "trace_id_required",
    "review_rows_require_reviewer",
    "graph_patch_rows_require_graph_patch_ref",
    "no_live_filesystem_mutation",
    "docs_changelog_trace_required",
]
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,220}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    local = str(ref or "").strip().replace("\\", "/")
    candidates = [("project", project_root / local), ("package", package_root / local)]
    if not local.startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / local))
    checked: List[str] = []
    for owner, path in candidates:
        checked.append(_display_path(path))
        if path.exists():
            return {"ok": True, "ref": ref, "resolved_under": owner, "path": _display_path(path), "checked": checked}
    return {"ok": False, "ref": ref, "resolved_under": "", "path": "", "checked": checked}


def _resolve_refs(refs: Sequence[str], *, project_root: Path, package_root: Path, owner: str) -> Dict[str, Any]:
    failures: List[str] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            failures.append(f"unsafe_ref:{owner}:{ref}")
            unsafe_refs.append({"owner": owner, "ref": ref})
            continue
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        resolved["owner"] = owner
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            failures.append(f"missing_ref:{owner}:{ref}")
            missing_refs.append(resolved)
    return {"failures": failures, "resolved_refs": resolved_refs, "missing_refs": missing_refs, "unsafe_refs": unsafe_refs}


def _is_safe_artifact_path(value: Any) -> bool:
    text = str(value or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def load_policy(policy_path: Path | str = DEFAULT_POLICY) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def load_example(example_path: Path | str = DEFAULT_EXAMPLE) -> Dict[str, Any]:
    return json.loads(Path(example_path).read_text(encoding="utf-8"))


def summarize_artifact_registry_records(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    table_counts: Dict[str, int] = {}
    review_state_counts: Dict[str, int] = {}
    graph_patch_records = 0
    hashed_records = 0
    for record in records:
        table = str(record.get("table") or "")
        review_state = str(record.get("review_state") or "")
        table_counts[table] = table_counts.get(table, 0) + 1
        review_state_counts[review_state] = review_state_counts.get(review_state, 0) + 1
        if table == "graph_patches":
            graph_patch_records += 1
        if SHA256_RE.match(str(record.get("sha256") or "")):
            hashed_records += 1
    return {
        "record_count": len(records),
        "table_counts": table_counts,
        "review_state_counts": review_state_counts,
        "graph_patch_records": graph_patch_records,
        "hashed_records": hashed_records,
    }


def _record_failures(
    record: Dict[str, Any],
    *,
    allowed_artifact_types: set[str],
    allowed_review_states: set[str],
    index: int,
) -> List[str]:
    failures: List[str] = []
    for column in REQUIRED_COLUMNS:
        if column not in record:
            failures.append(f"artifact_column_missing:{index}:{column}")
    artifact_id = str(record.get("artifact_id") or "")
    if not SAFE_ID_RE.match(artifact_id):
        failures.append(f"artifact_id_invalid:{index}")
    table = str(record.get("table") or "")
    if table not in REQUIRED_TABLES:
        failures.append(f"artifact_table_invalid:{index}:{table}")
    artifact_type = str(record.get("artifact_type") or "")
    if artifact_type not in allowed_artifact_types:
        failures.append(f"artifact_type_invalid:{index}:{artifact_type}")
    if not _is_safe_artifact_path(record.get("path")):
        failures.append(f"artifact_path_invalid:{index}")
    if not SHA256_RE.match(str(record.get("sha256") or "")):
        failures.append(f"artifact_sha256_invalid:{index}")
    trace_id = str(record.get("trace_id") or "")
    if not SAFE_ID_RE.match(trace_id):
        failures.append(f"artifact_trace_id_invalid:{index}")
    producer = str(record.get("producer") or "")
    if not SAFE_ID_RE.match(producer):
        failures.append(f"artifact_producer_invalid:{index}")
    review_state = str(record.get("review_state") or "")
    if review_state not in allowed_review_states:
        failures.append(f"artifact_review_state_invalid:{index}:{review_state}")
    graph_patch_ref = str(record.get("graph_patch_ref") or "")
    if table == "graph_patches" and (graph_patch_ref == "N/A" or not SAFE_ID_RE.match(graph_patch_ref)):
        failures.append(f"artifact_graph_patch_ref_missing:{index}")
    if table == "reviews" and not str(record.get("reviewer") or "").strip():
        failures.append(f"artifact_reviewer_missing:{index}")
    created_at = str(record.get("created_at") or "")
    if not created_at.endswith("Z") or "T" not in created_at:
        failures.append(f"artifact_created_at_invalid:{index}")
    return failures


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if payload.get("id") != POLICY_ID:
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if str(policy.get("activation_state") or "") != "artifact_registry_table_contract":
        failures.append("policy_activation_state_invalid")
    if str(policy.get("required_pipeline_ref") or "") != "pipeline:firstboot-model-selection:0.32.2":
        failures.append("policy_required_pipeline_ref_invalid")
    if PRIMARY_TODO not in _as_string_list(policy.get("closed_todo_refs")):
        failures.append("policy_closed_todo_ref_missing")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if _as_string_list(policy.get("required_tables")) != REQUIRED_TABLES:
        failures.append("policy_required_tables_invalid")
    if _as_string_list(policy.get("required_columns")) != REQUIRED_COLUMNS:
        failures.append("policy_required_columns_invalid")
    if not _as_string_list(policy.get("allowed_artifact_types")):
        failures.append("policy_allowed_artifact_types_empty")
    if not _as_string_list(policy.get("allowed_review_states")):
        failures.append("policy_allowed_review_states_empty")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"control_{key}_not_true")
    if _as_string_list(policy.get("summary_fields")) != SUMMARY_FIELDS:
        failures.append("policy_summary_fields_invalid")
    if not _as_string_list(policy.get("required_outputs")):
        failures.append("policy_required_outputs_empty")
    if not _as_string_list(policy.get("required_refs")):
        failures.append("policy_required_refs_empty")
    return failures


def _example_failures(example: Dict[str, Any], *, policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    if example.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example.get("kind") != EXAMPLE_KIND:
        failures.append("example_kind_invalid")
    records = example.get("records") if isinstance(example.get("records"), list) else []
    if not records:
        failures.append("example_records_empty")
    allowed_artifact_types = set(_as_string_list(policy.get("allowed_artifact_types")))
    allowed_review_states = set(_as_string_list(policy.get("allowed_review_states")))
    seen_ids: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            failures.append(f"artifact_record_not_object:{index}")
            continue
        artifact_id = str(record.get("artifact_id") or "")
        if artifact_id in seen_ids:
            failures.append(f"artifact_id_duplicate:{index}:{artifact_id}")
        seen_ids.add(artifact_id)
        failures.extend(
            _record_failures(
                record,
                allowed_artifact_types=allowed_artifact_types,
                allowed_review_states=allowed_review_states,
                index=index,
            )
        )
    summary = summarize_artifact_registry_records(records)
    expected = example.get("expected_summary") if isinstance(example.get("expected_summary"), dict) else {}
    for key in SUMMARY_FIELDS:
        if summary.get(key) != expected.get(key):
            failures.append(f"example_summary_mismatch:{key}")
    for table in REQUIRED_TABLES:
        if summary["table_counts"].get(table, 0) < 1:
            failures.append(f"example_table_missing:{table}")
    return {"failures": failures, "records": records, "summary": summary}


def validate_artifact_registry_table_policy(
    policy_payload: Dict[str, Any],
    *,
    project_root: Path | str = PROJECT_ROOT,
    package_root: Path | str = PACKAGE_ROOT,
    example_path: Path | str = DEFAULT_EXAMPLE,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    failures: List[str] = []
    failures.extend(_policy_failures(policy_payload))
    policy = _policy_dict(policy_payload)

    refs = _as_string_list(policy_payload.get("refs")) + _as_string_list(policy.get("required_refs"))
    ref_report = _resolve_refs(refs, project_root=project, package_root=package, owner=POLICY_ID)
    failures.extend(ref_report["failures"])

    example_report = _example_failures(load_example(example_path), policy=policy)
    failures.extend(example_report["failures"])

    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "id": POLICY_ID,
        "failures": sorted(failures),
        "artifact_registry_table_summary": example_report["summary"],
        "artifact_registry_records": example_report["records"],
        "resolved_refs": ref_report["resolved_refs"],
        "missing_refs": ref_report["missing_refs"],
        "unsafe_refs": ref_report["unsafe_refs"],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge artifact registry table contracts.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY), help="Policy JSON path.")
    parser.add_argument("--example", default=str(DEFAULT_EXAMPLE), help="Example artifact registry table path.")
    parser.add_argument("--summary", action="store_true", help="Emit compact summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    report = validate_artifact_registry_table_policy(load_policy(args.policy), example_path=args.example)
    payload: Dict[str, Any]
    if args.summary:
        payload = {
            "apiVersion": API_VERSION,
            "kind": "ArtifactRegistryTableSummary",
            "id": POLICY_ID,
            "ok": report["ok"],
            "failures": report["failures"],
            "summary": report["artifact_registry_table_summary"],
        }
    else:
        payload = report
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
