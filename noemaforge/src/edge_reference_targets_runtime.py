#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/edge_reference_targets_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate edge reference targets remain optional post-MVP integrations, not runtime requirements.
Inputs: noemaforge/configs/edge-reference-targets.json plus local project/package roots.
Outputs: JSON-compatible EdgeReferenceTargetsReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_edge_reference_targets_runtime.py
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


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import production_ai_contracts as pac


API_VERSION = "noemaforge.edge-reference-targets/v1"
POLICY_KIND = "EdgeReferenceTargetsPolicy"
REPORT_KIND = "EdgeReferenceTargetsReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_CATEGORIES = {"orchestration", "stream_rule_engine", "ota_reference"}
VALID_TARGET_STATUSES = {"post_mvp", "preferred_future", "reference_only"}
REQUIRED_TARGETS = {"kubeedge", "ekuiper", "mender", "rauc"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
REGISTRY_REF_RE = re.compile(r"^[a-z-]+:[A-Za-z0-9_.:-]+:[A-Za-z0-9_.:-]+$")


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
            return {
                "ok": True,
                "ref": ref,
                "resolved_under": base_name,
                "path": _display_path(path),
                "checked": checked,
            }
    return {"ok": False, "ref": ref, "resolved_under": "", "path": "", "checked": checked}


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if not SAFE_ID_RE.match(str(payload.get("id") or "")):
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    for key in [
        "require_post_mvp_for_orchestration",
        "require_preferred_local_rule_engine",
        "require_ota_reference_only",
        "forbid_first_start_dependency",
        "forbid_required_runtime_dependency",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    categories = set(_as_string_list(policy.get("allowed_categories")))
    statuses = set(_as_string_list(policy.get("allowed_statuses")))
    required = set(_as_string_list(policy.get("required_targets")))
    if not categories:
        failures.append("policy_allowed_categories_empty")
    if not statuses:
        failures.append("policy_allowed_statuses_empty")
    if not required:
        failures.append("policy_required_targets_empty")
    failures.extend(f"policy_invalid_category:{item}" for item in sorted(categories - VALID_CATEGORIES))
    failures.extend(f"policy_invalid_target_status:{item}" for item in sorted(statuses - VALID_TARGET_STATUSES))
    failures.extend(f"policy_unknown_required_target:{item}" for item in sorted(required - REQUIRED_TARGETS))
    return failures


def _target_failures(target: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    target_id = str(target.get("id") or "").strip().lower()
    owner = target_id or "<missing>"
    if target_id not in REQUIRED_TARGETS:
        failures.append(f"target_id_unknown:{owner}")
    category = str(target.get("category") or "")
    status = str(target.get("status") or "")
    if category not in set(_as_string_list(policy.get("allowed_categories"))) or category not in VALID_CATEGORIES:
        failures.append(f"target_category_not_allowed:{owner}:{category}")
    if status not in set(_as_string_list(policy.get("allowed_statuses"))) or status not in VALID_TARGET_STATUSES:
        failures.append(f"target_status_not_allowed:{owner}:{status}")
    if policy.get("forbid_first_start_dependency") is True and target.get("required_for_first_start") is not False:
        failures.append(f"target_required_for_first_start:{owner}")
    if policy.get("forbid_required_runtime_dependency") is True and target.get("required_runtime_dependency") is not False:
        failures.append(f"target_required_runtime_dependency:{owner}")
    if category == "orchestration" and policy.get("require_post_mvp_for_orchestration") is True and status != "post_mvp":
        failures.append(f"target_orchestration_not_post_mvp:{owner}:{status}")
    if target_id == "ekuiper" and policy.get("require_preferred_local_rule_engine") is True:
        if category != "stream_rule_engine":
            failures.append(f"target_ekuiper_category_invalid:{owner}:{category}")
        if status != "preferred_future":
            failures.append(f"target_ekuiper_not_preferred_future:{owner}:{status}")
        if target.get("preferred") is not True:
            failures.append(f"target_ekuiper_not_preferred:{owner}")
    if category == "ota_reference" and policy.get("require_ota_reference_only") is True and status != "reference_only":
        failures.append(f"target_ota_not_reference_only:{owner}:{status}")
    alt_ref = str(target.get("local_mvp_alternative_ref") or "")
    if not REGISTRY_REF_RE.match(alt_ref):
        failures.append(f"target_local_mvp_alternative_ref_invalid:{owner}:{alt_ref}")
    return failures


def _resolve_refs(refs: Sequence[str], *, project_root: Path, package_root: Path, owner: str) -> Dict[str, Any]:
    failures: List[str] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            item = {"owner": owner, "ref": ref}
            unsafe_refs.append(item)
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


def validate_edge_reference_targets_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root)
    if not project.exists():
        raise FileNotFoundError(project)
    if not package.exists():
        raise FileNotFoundError(package)

    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    targets = payload.get("targets") if isinstance(payload.get("targets"), list) else []
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    if not targets:
        failures.append("targets_empty")

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    target_results: List[Dict[str, Any]] = []

    policy_refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(policy_refs["failures"])
    all_resolved_refs.extend(policy_refs["resolved_refs"])
    all_missing_refs.extend(policy_refs["missing_refs"])
    all_unsafe_refs.extend(policy_refs["unsafe_refs"])

    seen_targets = set()
    for target in targets:
        if not isinstance(target, dict):
            failures.append("target_not_object")
            continue
        target_id = str(target.get("id") or "<missing>").lower()
        seen_targets.add(target_id)
        target_failures = _target_failures(target, policy)
        refs_result = _resolve_refs(_as_string_list(target.get("refs")), project_root=project, package_root=package, owner=target_id)
        target_failures.extend(refs_result["failures"])
        failures.extend(target_failures)
        all_resolved_refs.extend(refs_result["resolved_refs"])
        all_missing_refs.extend(refs_result["missing_refs"])
        all_unsafe_refs.extend(refs_result["unsafe_refs"])
        target_results.append(
            {
                "id": target_id,
                "ok": not target_failures,
                "category": str(target.get("category") or ""),
                "status": str(target.get("status") or ""),
                "required_for_first_start": target.get("required_for_first_start") is True,
                "required_runtime_dependency": target.get("required_runtime_dependency") is True,
                "preferred": target.get("preferred") is True,
                "failures": sorted(set(target_failures)),
            }
        )

    required_targets = set(_as_string_list(policy.get("required_targets"))) or REQUIRED_TARGETS
    missing_required_targets = sorted(required_targets - seen_targets)
    failures.extend(f"required_target_missing:{item}" for item in missing_required_targets)
    checks = [
        {"id": "kubeedge_post_mvp", "status": "passed" if not any("kubeedge" in item for item in failures) else "failed"},
        {"id": "ekuiper_preferred_future", "status": "passed" if not any("ekuiper" in item for item in failures) else "failed"},
        {"id": "ota_references_only", "status": "passed" if not any("target_ota" in item or "mender" in item or "rauc" in item for item in failures) else "failed"},
        {"id": "no_first_start_dependency", "status": "passed" if not any("required_for_first_start" in item for item in failures) else "failed"},
        {"id": "no_runtime_dependency", "status": "passed" if not any("required_runtime_dependency" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "targets": len(target_results),
        "passing_targets": sum(1 for item in target_results if item["ok"]),
        "orchestration_targets": sum(1 for item in target_results if item["category"] == "orchestration"),
        "stream_rule_engine_targets": sum(1 for item in target_results if item["category"] == "stream_rule_engine"),
        "ota_reference_targets": sum(1 for item in target_results if item["category"] == "ota_reference"),
        "post_mvp_targets": sum(1 for item in target_results if item["status"] == "post_mvp"),
        "preferred_future_targets": sum(1 for item in target_results if item["status"] == "preferred_future"),
        "reference_only_targets": sum(1 for item in target_results if item["status"] == "reference_only"),
        "first_start_required_targets": sum(1 for item in target_results if item["required_for_first_start"]),
        "runtime_required_targets": sum(1 for item in target_results if item["required_runtime_dependency"]),
        "missing_required_targets": len(missing_required_targets),
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
        "project_root": _display_path(project),
        "package_root": _display_path(package),
        "failures": sorted(set(failures)),
        "metrics": metrics,
        "checks": checks,
        "target_results": sorted(target_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def edge_reference_targets_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("edge_reference_targets_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge edge reference target contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/edge-reference-targets.json",
        help="Policy path, absolute or relative to project root.",
    )
    parser.add_argument("--summary", action="store_true", help="Emit a compact validation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = _as_path(args.project_root)
    package_root = _as_path(args.package_root) if args.package_root else project_root / "noemaforge"
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = project_root / policy_path

    report = validate_edge_reference_targets_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "EdgeReferenceTargetsSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "policy_path": report["policy_path"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
