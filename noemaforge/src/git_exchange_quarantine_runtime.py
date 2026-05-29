#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/git_exchange_quarantine_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate quarantine-first git_exchange import/export contracts.
Inputs: noemaforge/configs/git-exchange-quarantine-policy.json and git_exchange examples.
Outputs: JSON-compatible GitExchangeValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_git_exchange_quarantine_runtime.py
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


API_VERSION = "noemaforge.git-exchange/v1"
POLICY_KIND = "GitExchangePolicy"
SET_KIND = "GitExchangeImportSet"
IMPORT_KIND = "GitExchangeImport"
REPORT_KIND = "GitExchangeValidationReport"

VALID_POLICY_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_PACK_KINDS = {"RolePack", "RoleFlow", "EvalPack", "KnowledgeGraphPack", "ArtifactPack", "ModelDeltaPack"}
REQUIRED_STAGES = {
    "fetch",
    "manifest_scan",
    "quarantine_record",
    "scary_verdict",
    "surgeon_recommendation",
    "admin_approval",
    "promotion_record",
}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,180}$")
SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


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
    if str(policy.get("activation_state") or "") != "quarantine_first":
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
    for key in ["role_kernel_policy_ref", "roleflow_policy_ref", "quarantine_root"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    if not REQUIRED_PACK_KINDS.issubset(set(_as_string_list(policy.get("allowed_pack_kinds")))):
        failures.append("policy_allowed_pack_kinds_missing")
    if not REQUIRED_STAGES.issubset(set(_as_string_list(policy.get("mandatory_stages")))):
        failures.append("policy_mandatory_stages_missing")
    if not {"active", "installed", "promoted"}.issubset(set(_as_string_list(policy.get("blocked_activation_states")))):
        failures.append("policy_blocked_activation_states_missing")

    requirements = policy.get("promotion_requirements") if isinstance(policy.get("promotion_requirements"), dict) else {}
    for key in [
        "signed_manifest",
        "sha256_manifest",
        "provenance_required",
        "scary_verdict_required",
        "surgeon_recommendation_required",
        "admin_approval_required",
        "quarantine_evidence_retained",
        "model_delta_lab_only",
    ]:
        if requirements.get(key) is not True:
            failures.append(f"policy_promotion_{key}_not_true")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _dependency_failures(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> List[str]:
    failures: List[str] = []
    for key, api_version, kind in [
        ("role_kernel_policy_ref", "noemaforge.role-kernel/v1", "RoleKernelPolicy"),
        ("roleflow_policy_ref", "noemaforge.roleflow/v1", "RoleFlowPolicy"),
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
        for ref in ["configs/git-exchange-quarantine-policy.json", "contracts/git_exchange_quarantine.schema.json", "src/git_exchange_quarantine_runtime.py"]:
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
    for ref in ["configs/git-exchange-quarantine-policy.json", "src/git_exchange_quarantine_runtime.py", "prelaunch/governance/git_exchange_quarantine.example.json"]:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "entries": entries, "pipeline_eval_refs": pipeline_eval_refs}


def _provenance_failures(import_id: str, provenance: Any) -> List[str]:
    failures: List[str] = []
    if not isinstance(provenance, dict):
        return [f"import_provenance_missing:{import_id}"]
    for key in ["commit", "author", "license", "source_uri"]:
        if not str(provenance.get(key) or "").strip():
            failures.append(f"import_provenance_{key}_missing:{import_id}")
    return failures


def _import_failures(item: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    failures: List[str] = []
    import_id = str(item.get("id") or "<missing>")
    pack_kind = str(item.get("pack_kind") or "")
    allowed_kinds = set(_as_string_list(policy.get("allowed_pack_kinds")))
    required_stages = set(_as_string_list(policy.get("mandatory_stages")))
    blocked_states = set(_as_string_list(policy.get("blocked_activation_states")))
    requirements = policy.get("promotion_requirements") if isinstance(policy.get("promotion_requirements"), dict) else {}

    if item.get("apiVersion") != API_VERSION:
        failures.append(f"import_api_version_invalid:{import_id}")
    if item.get("kind") != IMPORT_KIND:
        failures.append(f"import_kind_invalid:{import_id}")
    if not SAFE_ID_RE.match(import_id):
        failures.append(f"import_id_invalid:{import_id}")
    if policy.get("require_trace_id") is True and not SAFE_ID_RE.match(str(item.get("trace_id") or "")):
        failures.append(f"import_trace_id_invalid:{import_id}")
    if pack_kind not in allowed_kinds:
        failures.append(f"import_pack_kind_invalid:{import_id}:{pack_kind}")
    if not SAFE_ID_RE.match(str(item.get("pack_id") or "")):
        failures.append(f"import_pack_id_invalid:{import_id}:{item.get('pack_id')}")
    if not str(item.get("source_ref") or "").startswith("git:"):
        failures.append(f"import_source_ref_invalid:{import_id}:{item.get('source_ref')}")
    if requirements.get("sha256_manifest") is True and not SHA256_RE.match(str(item.get("manifest_sha256") or "")):
        failures.append(f"import_manifest_sha256_invalid:{import_id}")
    if requirements.get("signed_manifest") is True and item.get("signed_manifest") is not True:
        failures.append(f"import_signed_manifest_missing:{import_id}")
    if requirements.get("provenance_required") is True:
        failures.extend(_provenance_failures(import_id, item.get("provenance")))

    stages = set(_as_string_list(item.get("stages")))
    if not required_stages.issubset(stages):
        failures.append(f"import_mandatory_stages_missing:{import_id}")

    quarantine = item.get("quarantine") if isinstance(item.get("quarantine"), dict) else {}
    if str(quarantine.get("state") or "") != "quarantined":
        failures.append(f"import_not_quarantined:{import_id}:{quarantine.get('state')}")
    if str(quarantine.get("activation_state") or "") in blocked_states:
        failures.append(f"import_activation_blocked_state:{import_id}:{quarantine.get('activation_state')}")
    if requirements.get("quarantine_evidence_retained") is True and quarantine.get("evidence_retained") is not True:
        failures.append(f"import_quarantine_evidence_not_retained:{import_id}")
    if not _is_safe_relative_ref(str(quarantine.get("path") or "")):
        failures.append(f"import_quarantine_path_invalid:{import_id}:{quarantine.get('path')}")

    review = item.get("review") if isinstance(item.get("review"), dict) else {}
    if requirements.get("scary_verdict_required") is True and str(review.get("scary_verdict") or "") != "quarantine":
        failures.append(f"import_scary_verdict_invalid:{import_id}:{review.get('scary_verdict')}")
    if requirements.get("surgeon_recommendation_required") is True and str(review.get("surgeon_recommendation") or "") not in {"hold", "review", "quarantine"}:
        failures.append(f"import_surgeon_recommendation_invalid:{import_id}:{review.get('surgeon_recommendation')}")
    if requirements.get("admin_approval_required") is True and str(review.get("admin_approval") or "") not in {"pending", "rejected", "not_requested"}:
        failures.append(f"import_admin_approval_invalid:{import_id}:{review.get('admin_approval')}")

    model_delta = item.get("model_delta") if isinstance(item.get("model_delta"), dict) else {}
    if pack_kind == "ModelDeltaPack":
        if requirements.get("model_delta_lab_only") is True and model_delta.get("lab_only") is not True:
            failures.append(f"import_model_delta_not_lab_only:{import_id}")
        if model_delta.get("production_activation_allowed") is not False:
            failures.append(f"import_model_delta_production_activation_allowed:{import_id}")
    elif model_delta.get("production_activation_allowed") is not False:
        failures.append(f"import_non_model_delta_production_activation_allowed:{import_id}")
    return failures


def validate_git_exchange_policy(
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
    import_results: List[Dict[str, Any]] = []

    refs_to_resolve = _as_string_list(payload.get("refs"))
    refs_to_resolve.extend([str(policy.get("role_kernel_policy_ref") or ""), str(policy.get("roleflow_policy_ref") or "")])
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

    seen_pack_kinds: Set[str] = set()
    for ref_item in example_ref_results["resolved_refs"]:
        example_set = load_example_set(Path(ref_item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{ref_item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{ref_item['ref']}")
        imports = example_set.get("imports") if isinstance(example_set.get("imports"), list) else []
        if not imports:
            failures.append(f"example_set_imports_empty:{ref_item['ref']}")
        for item in imports:
            if not isinstance(item, dict):
                failures.append(f"import_not_object:{ref_item['ref']}")
                continue
            import_id = str(item.get("id") or "<missing>")
            pack_kind = str(item.get("pack_kind") or "")
            seen_pack_kinds.add(pack_kind)
            import_failures = _import_failures(item, payload)
            import_ref_result = _resolve_refs(_as_string_list(item.get("refs")), project_root=project, package_root=package, owner=import_id)
            import_failures.extend(import_ref_result["failures"])
            failures.extend(import_failures)
            all_resolved_refs.extend(import_ref_result["resolved_refs"])
            all_missing_refs.extend(import_ref_result["missing_refs"])
            all_unsafe_refs.extend(import_ref_result["unsafe_refs"])
            import_results.append(
                {
                    "id": import_id,
                    "pack_kind": pack_kind,
                    "ok": not import_failures,
                    "failures": sorted(set(import_failures)),
                }
            )
    if not REQUIRED_PACK_KINDS.issubset(seen_pack_kinds):
        failures.append("examples_required_pack_kinds_missing")

    checks = [
        {"id": "quarantine_first", "status": "passed" if not any("quarantined" in item or "activation_blocked" in item for item in failures) else "failed"},
        {"id": "signed_manifest", "status": "passed" if not any("signed_manifest" in item or "manifest_sha256" in item for item in failures) else "failed"},
        {"id": "provenance", "status": "passed" if not any("provenance" in item for item in failures) else "failed"},
        {"id": "scary_surgeon_admin_review", "status": "passed" if not any("scary" in item or "surgeon" in item or "admin_approval" in item for item in failures) else "failed"},
        {"id": "model_delta_lab_only", "status": "passed" if not any("model_delta" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "imports": len(import_results),
        "passing_imports": sum(1 for item in import_results if item["ok"]),
        "pack_kinds": len(seen_pack_kinds),
        "model_delta_imports": sum(1 for item in import_results if item["pack_kind"] == "ModelDeltaPack"),
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
        "import_results": sorted(import_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def git_exchange_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("git_exchange_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge quarantine-first git_exchange contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/git-exchange-quarantine-policy.json",
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

    report = validate_git_exchange_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "GitExchangeValidationSummary",
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
