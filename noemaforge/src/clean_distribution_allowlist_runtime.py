#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/clean_distribution_allowlist_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate allowlist-built public distributions and core/optional split rules.
Inputs: noemaforge/configs/clean-distribution-allowlist.json and distribution plan examples.
Outputs: JSON-compatible CleanDistributionAllowlistValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_clean_distribution_allowlist_runtime.py
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


API_VERSION = "noemaforge.clean-distribution/v1"
POLICY_KIND = "CleanDistributionAllowlistPolicy"
SET_KIND = "CleanDistributionPlanSet"
PLAN_KIND = "CleanDistributionPlan"
REPORT_KIND = "CleanDistributionAllowlistValidationReport"

VALID_POLICY_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_CATEGORIES = {"hf", "community", "history", "quarantine"}
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


def _normalize_ref(ref: str) -> str:
    return str(ref or "").strip().replace("\\", "/")


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


def _category_rules(policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    rules = policy.get("category_rules") if isinstance(policy.get("category_rules"), list) else []
    return [rule for rule in rules if isinstance(rule, dict)]


def _excluded_prefixes(policy: Dict[str, Any]) -> Dict[str, List[str]]:
    raw = policy.get("excluded_prefixes") if isinstance(policy.get("excluded_prefixes"), dict) else {}
    return {str(key): _as_string_list(value) for key, value in raw.items()}


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
    if str(policy.get("activation_state") or "") != "allowlist_public_seed":
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
    if str(policy.get("core_seed_channel") or "") != "public_core_seed":
        failures.append("policy_core_seed_channel_invalid")

    build_policy = policy.get("build_policy") if isinstance(policy.get("build_policy"), dict) else {}
    for key in [
        "allowlist_only",
        "deny_by_default",
        "split_optional_material",
        "split_hf_material",
        "split_community_material",
        "split_history_material",
        "split_quarantine_material",
    ]:
        if build_policy.get(key) is not True:
            failures.append(f"policy_build_{key}_not_true")
    for key in ["include_dev_tests_in_core", "include_transient_artifacts", "delete_during_plan"]:
        if build_policy.get(key) is not False:
            failures.append(f"policy_build_{key}_not_false")

    if not _as_string_list(policy.get("required_core_refs")):
        failures.append("policy_required_core_refs_empty")
    rules = _category_rules(policy)
    seen_categories = {str(rule.get("category") or "") for rule in rules}
    if not REQUIRED_CATEGORIES.issubset(seen_categories):
        failures.append("policy_required_categories_missing")
    for rule in rules:
        category = str(rule.get("category") or "")
        if category not in REQUIRED_CATEGORIES:
            failures.append(f"policy_category_invalid:{category}")
        if str(rule.get("destination_lane") or "") == "core_seed":
            failures.append(f"policy_category_destination_core:{category}")
        if rule.get("included_in_core") is not False:
            failures.append(f"policy_category_included_in_core:{category}")
        if not str(rule.get("reason") or "").strip():
            failures.append(f"policy_category_reason_empty:{category}")
    prefixes = _excluded_prefixes(policy)
    for category in REQUIRED_CATEGORIES:
        if not prefixes.get(category):
            failures.append(f"policy_excluded_prefixes_missing:{category}")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
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
        for ref in [
            "configs/clean-distribution-allowlist.json",
            "contracts/clean_distribution_allowlist.schema.json",
            "src/clean_distribution_allowlist_runtime.py",
            "tests/test_clean_distribution_allowlist_runtime.py",
        ]:
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
    for ref in [
        "configs/clean-distribution-allowlist.json",
        "src/clean_distribution_allowlist_runtime.py",
        "prelaunch/governance/clean_distribution_allowlist.example.json",
    ]:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "entries": entries, "pipeline_eval_refs": pipeline_eval_refs}


def _plan_failures(plan: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    prefixes = _excluded_prefixes(policy)
    failures: List[str] = []
    plan_id = str(plan.get("id") or "<missing>")
    if plan.get("apiVersion") != API_VERSION:
        failures.append(f"plan_api_version_invalid:{plan_id}")
    if plan.get("kind") != PLAN_KIND:
        failures.append(f"plan_kind_invalid:{plan_id}")
    if not SAFE_ID_RE.match(plan_id):
        failures.append(f"plan_id_invalid:{plan_id}")
    if policy.get("require_trace_id") is True and not SAFE_ID_RE.match(str(plan.get("trace_id") or "")):
        failures.append(f"plan_trace_id_invalid:{plan_id}")
    expected = {
        "build_type": "public_distribution",
        "target_lane": "core_seed",
    }
    for key, expected_value in expected.items():
        if str(plan.get(key) or "") != expected_value:
            failures.append(f"plan_{key}_invalid:{plan_id}")
    for key in ["allowlist_only", "deny_by_default", "dry_run"]:
        if plan.get(key) is not True:
            failures.append(f"plan_{key}_not_true:{plan_id}")
    if plan.get("deletes_files") is not False:
        failures.append(f"plan_deletes_files_not_false:{plan_id}")

    included_refs = _as_string_list(plan.get("included_refs"))
    included_set = set(included_refs)
    required_core = set(_as_string_list(policy.get("required_core_refs")))
    if not included_refs:
        failures.append(f"plan_included_refs_empty:{plan_id}")
    missing_required = sorted(required_core - included_set)
    for ref in missing_required:
        failures.append(f"plan_required_core_ref_missing:{plan_id}:{ref}")
    for ref in included_refs:
        normalized = _normalize_ref(ref)
        for category, category_prefixes in prefixes.items():
            if any(normalized.startswith(prefix) for prefix in category_prefixes):
                failures.append(f"plan_core_ref_matches_excluded_prefix:{plan_id}:{category}:{ref}")

    excluded = plan.get("excluded_material") if isinstance(plan.get("excluded_material"), list) else []
    categories_seen: Set[str] = {str(item.get("category") or "") for item in excluded if isinstance(item, dict)}
    if not REQUIRED_CATEGORIES.issubset(categories_seen):
        failures.append(f"plan_excluded_categories_missing:{plan_id}")
    for item in excluded:
        if not isinstance(item, dict):
            failures.append(f"plan_excluded_item_not_object:{plan_id}")
            continue
        category = str(item.get("category") or "")
        if category not in REQUIRED_CATEGORIES:
            failures.append(f"plan_excluded_category_invalid:{plan_id}:{category}")
        if str(item.get("destination_lane") or "") == "core_seed":
            failures.append(f"plan_excluded_destination_core:{plan_id}:{category}")
        if item.get("included_in_core") is not False:
            failures.append(f"plan_excluded_included_in_core:{plan_id}:{category}")
        if not str(item.get("reason") or "").strip():
            failures.append(f"plan_excluded_reason_empty:{plan_id}:{category}")
        refs = _as_string_list(item.get("refs"))
        if not refs:
            failures.append(f"plan_excluded_refs_empty:{plan_id}:{category}")
        for ref in refs:
            if ref in included_set:
                failures.append(f"plan_excluded_ref_also_included:{plan_id}:{category}:{ref}")

    audit = plan.get("audit") if isinstance(plan.get("audit"), dict) else {}
    for key in ["manifest_required", "release_evidence_required", "summary_required", "operator_review_required"]:
        if audit.get(key) is not True:
            failures.append(f"plan_audit_{key}_not_true:{plan_id}")
    return failures


def validate_clean_distribution_policy(
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
    registry_result = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_result["failures"])

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    plan_results: List[Dict[str, Any]] = []

    refs_to_resolve = sorted(set(_as_string_list(payload.get("refs")) + _as_string_list(policy.get("required_core_refs"))))
    refs_result = _resolve_refs(refs_to_resolve, project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
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
        plans = example_set.get("plans") if isinstance(example_set.get("plans"), list) else []
        if not plans:
            failures.append(f"example_set_plans_empty:{ref_item['ref']}")
        for plan in plans:
            if not isinstance(plan, dict):
                failures.append(f"plan_not_object:{ref_item['ref']}")
                continue
            plan_id = str(plan.get("id") or "<missing>")
            plan_failures = _plan_failures(plan, payload)
            plan_refs = _as_string_list(plan.get("refs")) + _as_string_list(plan.get("included_refs"))
            for excluded in plan.get("excluded_material") if isinstance(plan.get("excluded_material"), list) else []:
                if isinstance(excluded, dict):
                    plan_refs.extend(_as_string_list(excluded.get("refs")))
            plan_ref_result = _resolve_refs(sorted(set(plan_refs)), project_root=project, package_root=package, owner=plan_id)
            plan_failures.extend(plan_ref_result["failures"])
            failures.extend(plan_failures)
            all_resolved_refs.extend(plan_ref_result["resolved_refs"])
            all_missing_refs.extend(plan_ref_result["missing_refs"])
            all_unsafe_refs.extend(plan_ref_result["unsafe_refs"])
            plan_results.append(
                {
                    "id": plan_id,
                    "ok": not plan_failures,
                    "included_refs": len(_as_string_list(plan.get("included_refs"))),
                    "excluded_categories": sorted(
                        {
                            str(item.get("category") or "")
                            for item in plan.get("excluded_material") or []
                            if isinstance(item, dict)
                        }
                    ),
                    "failures": sorted(set(plan_failures)),
                }
            )

    checks = [
        {"id": "allowlist_only", "status": "passed" if not any("allowlist" in item for item in failures) else "failed"},
        {"id": "deny_by_default", "status": "passed" if not any("deny_by_default" in item for item in failures) else "failed"},
        {"id": "optional_split", "status": "passed" if not any("optional" in item or "included_in_core" in item for item in failures) else "failed"},
        {"id": "history_split", "status": "passed" if not any(":history" in item for item in failures) else "failed"},
        {"id": "quarantine_split", "status": "passed" if not any(":quarantine" in item for item in failures) else "failed"},
        {"id": "no_delete", "status": "passed" if not any("delete" in item or "deletes_files" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "plans": len(plan_results),
        "passing_plans": sum(1 for item in plan_results if item["ok"]),
        "category_rules": len(_category_rules(policy)),
        "required_core_refs": len(_as_string_list(policy.get("required_core_refs"))),
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
        "plan_results": sorted(plan_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def clean_distribution_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("clean_distribution_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge clean public distribution allowlists.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/clean-distribution-allowlist.json",
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

    report = validate_clean_distribution_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "CleanDistributionAllowlistValidationSummary",
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
