#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/hfbridge_metadata_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate HFBridge metadata-first/read-mostly MVP contracts.
Inputs: noemaforge/configs/hfbridge-metadata-policy.json and HFBridge metadata examples.
Outputs: JSON-compatible HFBridgeMetadataValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_hfbridge_metadata_runtime.py
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
from typing import Any, Dict, List, Optional, Sequence, Set


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unified_registry_runtime as urr


API_VERSION = "noemaforge.hfbridge/v1"
POLICY_KIND = "HFBridgeMetadataPolicy"
SET_KIND = "HFBridgeMetadataSet"
QUERY_KIND = "HFBridgeMetadataQuery"
REPORT_KIND = "HFBridgeMetadataValidationReport"

VALID_POLICY_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_ALLOWED_OPS = {"metadata_query", "model_card_summary", "license_scan", "eval_metadata_snapshot", "repository_listing"}
REQUIRED_BLOCKED_OPS = {
    "weight_download",
    "dataset_download",
    "runtime_import",
    "auto_install",
    "auto_prompt_activation",
    "production_model_delta_import",
}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,180}$")


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_path(value: Path | str) -> Path:
    return Path(value).resolve()


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    candidates = [
        ("package", package_root / ref),
        ("project", project_root / ref),
    ]
    if not str(ref).startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / ref))

    checked: List[str] = []
    for base_name, path in candidates:
        checked.append(_display_path(path))
        if path.exists():
            return {"ok": True, "ref": ref, "resolved_under": base_name, "path": _display_path(path), "checked": checked}
    return {"ok": False, "ref": ref, "resolved_under": "", "path": "", "checked": checked}


def _resolve_refs(refs: Sequence[str], *, project_root: Path, package_root: Path, owner: str) -> Dict[str, Any]:
    failures: List[str] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            unsafe_refs.append({"owner": owner, "ref": ref})
            failures.append(f"unsafe_ref:{owner}:{ref}")
            continue
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        resolved["owner"] = owner
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            missing_refs.append(resolved)
            failures.append(f"missing_ref:{owner}:{ref}")
    return {"failures": failures, "resolved_refs": resolved_refs, "missing_refs": missing_refs, "unsafe_refs": unsafe_refs}


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def load_example_set(example_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(example_path).read_text(encoding="utf-8"))


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if not SAFE_ID_RE.match(str(payload.get("id") or "")):
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_POLICY_STATUSES:
        failures.append("policy_status_invalid")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if str(policy.get("activation_state") or "") != "metadata_first_read_mostly":
        failures.append("policy_activation_state_invalid")
    for key in [
        "require_trace_id",
        "require_registry_attachment",
        "require_policy_schema_runtime_tests",
        "require_docs_and_changelog_refs",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["git_exchange_policy_ref", "peft_lora_policy_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    if not REQUIRED_ALLOWED_OPS.issubset(set(_as_string_list(policy.get("allowed_operations")))):
        failures.append("policy_allowed_operations_missing")
    if not REQUIRED_BLOCKED_OPS.issubset(set(_as_string_list(policy.get("blocked_operations")))):
        failures.append("policy_blocked_operations_missing")

    read_policy = policy.get("read_policy") if isinstance(policy.get("read_policy"), dict) else {}
    for key in ["metadata_only", "read_mostly", "network_optional", "offline_cache_allowed"]:
        if read_policy.get(key) is not True:
            failures.append(f"policy_read_{key}_not_true")
    for key in ["runtime_write_allowed", "external_artifact_import_allowed"]:
        if read_policy.get(key) is not False:
            failures.append(f"policy_read_{key}_not_false")

    promotion = policy.get("promotion_requirements") if isinstance(policy.get("promotion_requirements"), dict) else {}
    for key in [
        "quarantine_first",
        "signed_manifest_required",
        "evaluation_gate_required",
        "admin_approval_required",
        "model_delta_lab_only",
    ]:
        if promotion.get(key) is not True:
            failures.append(f"policy_promotion_{key}_not_true")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _dependency_failures(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> List[str]:
    failures: List[str] = []
    for key, api_version, kind in [
        ("git_exchange_policy_ref", "noemaforge.git-exchange/v1", "GitExchangePolicy"),
        ("peft_lora_policy_ref", "noemaforge.peft-lora-lab/v1", "PEFTLoRALabPolicy"),
    ]:
        ref = str(policy.get(key) or "")
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved["ok"]:
            failures.append(f"{key}_missing:{ref}")
            continue
        payload = json.loads(Path(resolved["path"]).read_text(encoding="utf-8"))
        if payload.get("apiVersion") != api_version:
            failures.append(f"{key}_api_version_invalid:{ref}")
        if payload.get("kind") != kind:
            failures.append(f"{key}_kind_invalid:{ref}")
    return failures


def _registry_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures = [f"registry_invalid:{item}" for item in report.get("failures", [])]
    entries = {
        _registry_ref(entry): entry
        for entry in report.get("normalized_registry", {}).get("entries", [])
        if isinstance(entry, dict)
    }
    raw_entries = {
        _registry_ref(entry): entry
        for entry in registry.get("entries", [])
        if isinstance(entry, dict)
    }
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    eval_entry = entries.get(eval_ref)
    if not eval_entry:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    else:
        entry_refs = set(_as_string_list(eval_entry.get("refs")))
        for ref in ["configs/hfbridge-metadata-policy.json", "contracts/hfbridge_metadata.schema.json", "src/hfbridge_metadata_runtime.py"]:
            if ref not in entry_refs:
                failures.append(f"registry_eval_pack_ref_missing:{eval_ref}:{ref}")

    pipeline_ref = str(policy.get("required_pipeline_ref") or "")
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
        pipeline_eval_refs: List[str] = []
        pipeline_refs: List[str] = []
    else:
        pipeline_eval_refs = _as_string_list(pipeline.get("eval_pack_refs"))
        pipeline_refs = _as_string_list(pipeline.get("refs"))
    if eval_ref not in pipeline_eval_refs:
        failures.append(f"registry_pipeline_eval_pack_missing:{eval_ref}")
    for ref in ["configs/hfbridge-metadata-policy.json", "src/hfbridge_metadata_runtime.py", "prelaunch/governance/hfbridge_metadata.example.json"]:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "entries": entries, "pipeline_eval_refs": pipeline_eval_refs}


def _query_failures(query: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    failures: List[str] = []
    query_id = str(query.get("id") or "<missing>")
    operation = str(query.get("operation") or "")
    allowed_ops = set(_as_string_list(policy.get("allowed_operations")))
    blocked_ops = set(_as_string_list(policy.get("blocked_operations")))

    if query.get("apiVersion") != API_VERSION:
        failures.append(f"query_api_version_invalid:{query_id}")
    if query.get("kind") != QUERY_KIND:
        failures.append(f"query_kind_invalid:{query_id}")
    if not SAFE_ID_RE.match(query_id):
        failures.append(f"query_id_invalid:{query_id}")
    if policy.get("require_trace_id") is True and not SAFE_ID_RE.match(str(query.get("trace_id") or "")):
        failures.append(f"query_trace_id_invalid:{query_id}")
    if operation not in allowed_ops:
        failures.append(f"query_operation_not_allowed:{query_id}:{operation}")
    if operation in blocked_ops:
        failures.append(f"query_operation_blocked:{query_id}:{operation}")
    if not str(query.get("target_ref") or "").startswith("hf://"):
        failures.append(f"query_target_ref_invalid:{query_id}:{query.get('target_ref')}")
    if str(query.get("network_mode") or "") not in {"offline_cache", "metadata_only", "disabled"}:
        failures.append(f"query_network_mode_invalid:{query_id}:{query.get('network_mode')}")
    if str(query.get("read_scope") or "") != "metadata_only":
        failures.append(f"query_read_scope_not_metadata_only:{query_id}")
    for key in ["writes_runtime", "downloads_artifacts", "activates_runtime", "imports_weights", "imports_datasets"]:
        if query.get(key) is not False:
            failures.append(f"query_{key}_not_false:{query_id}")
    if not _as_string_list(query.get("metadata_fields")):
        failures.append(f"query_metadata_fields_empty:{query_id}")

    promotion = query.get("promotion") if isinstance(query.get("promotion"), dict) else {}
    if promotion.get("requested") is not False:
        failures.append(f"query_promotion_requested:{query_id}")
    for key in ["quarantine_first", "signed_manifest_required", "evaluation_gate_required", "admin_approval_required"]:
        if promotion.get(key) is not True:
            failures.append(f"query_promotion_{key}_not_true:{query_id}")
    return failures


def validate_hfbridge_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Optional[Path | str] = None,
    registry_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root)
    if not project.exists():
        raise FileNotFoundError(project)
    if not package.exists():
        raise FileNotFoundError(package)
    registry = _as_path(registry_path) if registry_path else package / "configs" / "unified-registry.json"

    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    failures.extend(_dependency_failures(policy, project_root=project, package_root=package))
    registry_result = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_result["failures"])

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    query_results: List[Dict[str, Any]] = []

    refs_to_resolve = _as_string_list(payload.get("refs"))
    refs_to_resolve.extend([str(policy.get("git_exchange_policy_ref") or ""), str(policy.get("peft_lora_policy_ref") or "")])
    refs_result = _resolve_refs(sorted(set(refs_to_resolve)), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(refs_result["failures"])
    all_resolved_refs.extend(refs_result["resolved_refs"])
    all_missing_refs.extend(refs_result["missing_refs"])
    all_unsafe_refs.extend(refs_result["unsafe_refs"])

    example_ref_results = _resolve_refs(_as_string_list(policy.get("required_example_sets")), project_root=project, package_root=package, owner="required_example_sets")
    failures.extend(example_ref_results["failures"])
    all_resolved_refs.extend(example_ref_results["resolved_refs"])
    all_missing_refs.extend(example_ref_results["missing_refs"])
    all_unsafe_refs.extend(example_ref_results["unsafe_refs"])

    for ref_item in example_ref_results["resolved_refs"]:
        example_set = load_example_set(Path(ref_item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{ref_item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{ref_item['ref']}")
        queries = example_set.get("queries") if isinstance(example_set.get("queries"), list) else []
        if not queries:
            failures.append(f"example_set_queries_empty:{ref_item['ref']}")
        for query in queries:
            if not isinstance(query, dict):
                failures.append(f"query_not_object:{ref_item['ref']}")
                continue
            query_id = str(query.get("id") or "<missing>")
            query_failures = _query_failures(query, payload)
            query_ref_result = _resolve_refs(_as_string_list(query.get("refs")), project_root=project, package_root=package, owner=query_id)
            query_failures.extend(query_ref_result["failures"])
            failures.extend(query_failures)
            all_resolved_refs.extend(query_ref_result["resolved_refs"])
            all_missing_refs.extend(query_ref_result["missing_refs"])
            all_unsafe_refs.extend(query_ref_result["unsafe_refs"])
            query_results.append(
                {
                    "id": query_id,
                    "operation": str(query.get("operation") or ""),
                    "ok": not query_failures,
                    "metadata_fields": len(_as_string_list(query.get("metadata_fields"))),
                    "failures": sorted(set(query_failures)),
                }
            )

    checks = [
        {"id": "metadata_only", "status": "passed" if not any("metadata" in item and "missing" not in item for item in failures) else "failed"},
        {"id": "read_mostly", "status": "passed" if not any("read_" in item or "writes_runtime" in item for item in failures) else "failed"},
        {"id": "no_weight_or_dataset_import", "status": "passed" if not any("imports_weights" in item or "imports_datasets" in item or "downloads_artifacts" in item for item in failures) else "failed"},
        {"id": "no_runtime_activation", "status": "passed" if not any("activates_runtime" in item or "runtime_import" in item for item in failures) else "failed"},
        {"id": "promotion_guarded", "status": "passed" if not any("promotion" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "queries": len(query_results),
        "passing_queries": sum(1 for item in query_results if item["ok"]),
        "allowed_operations": len(set(_as_string_list(policy.get("allowed_operations")))),
        "blocked_operations": len(set(_as_string_list(policy.get("blocked_operations")))),
        "registry_entries": len(registry_result["entries"]),
        "refs": len(all_resolved_refs) + len(all_missing_refs) + len(all_unsafe_refs),
        "resolved_refs": len(all_resolved_refs),
        "missing_refs": len(all_missing_refs),
        "unsafe_refs": len(all_unsafe_refs),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "policy_path": str(policy_path or ""),
        "registry_path": _display_path(registry),
        "project_root": _display_path(project),
        "package_root": _display_path(package),
        "failures": sorted(set(failures)),
        "metrics": metrics,
        "checks": checks,
        "query_results": sorted(query_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def hfbridge_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("hfbridge_report_required")
    status = "passed" if report.get("ok") else "failed"
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": [
            {"id": "pipeline_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "rollback_plan", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "safety_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
        ],
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge HFBridge metadata-first/read-mostly contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/hfbridge-metadata-policy.json",
        help="Policy path, absolute or relative to project root.",
    )
    parser.add_argument("--registry", default="", help="Optional Unified Registry path.")
    parser.add_argument("--summary", action="store_true", help="Emit a compact validation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = _as_path(args.project_root)
    package_root = _as_path(args.package_root) if args.package_root else project_root / "noemaforge"
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = project_root / policy_path
    registry_path = Path(args.registry) if args.registry else package_root / "configs" / "unified-registry.json"
    if not registry_path.is_absolute():
        registry_path = project_root / registry_path

    report = validate_hfbridge_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "HFBridgeMetadataValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "policy_path": report["policy_path"],
            "registry_path": report["registry_path"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
