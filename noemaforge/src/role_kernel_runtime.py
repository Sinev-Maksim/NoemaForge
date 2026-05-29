#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/role_kernel_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the protected base role kernel and one-heavy-worker ActiveNN invariant.
Inputs: noemaforge/configs/role-kernel-policy.json, persona catalog, role catalog and role-kernel examples.
Outputs: JSON-compatible RoleKernelValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_role_kernel_runtime.py
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


API_VERSION = "noemaforge.role-kernel/v1"
POLICY_KIND = "RoleKernelPolicy"
SET_KIND = "RoleKernelSet"
KERNEL_KIND = "RoleKernel"
REPORT_KIND = "RoleKernelValidationReport"

VALID_POLICY_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_KERNEL_STATUSES = {"draft", "ready", "blocked", "retired"}
REQUIRED_DEFAULT_ROLE_IDS = ["admin", "surgeon", "scary", "evolver_darwin"]
REQUIRED_PROMOTION_PATH = [
    "system.guard/scary",
    "system.guard/surgeon",
    "operator.admin/administrator",
]
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


def _default_roles(policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    roles = policy.get("default_roles") if isinstance(policy.get("default_roles"), list) else []
    return [item for item in roles if isinstance(item, dict)]


def _optional_rolepacks(policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    rolepacks = policy.get("optional_rolepacks") if isinstance(policy.get("optional_rolepacks"), list) else []
    return [item for item in rolepacks if isinstance(item, dict)]


def _default_role_keys(policy: Dict[str, Any]) -> List[str]:
    return [str(item.get("role_key") or "") for item in _default_roles(policy) if str(item.get("role_key") or "")]


def _heavy_role_keys(policy: Dict[str, Any]) -> Set[str]:
    return {str(item.get("role_key") or "") for item in _default_roles(policy) if item.get("heavy_worker") is True}


def _supervisor_role_keys(policy: Dict[str, Any]) -> Set[str]:
    return {
        str(item.get("role_key") or "")
        for item in _default_roles(policy)
        if item.get("always_present") is True and str(item.get("role_class") or "") == "lightweight_supervisor"
    }


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
    if str(policy.get("activation_state") or "") != "protected_kernel":
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

    default_roles = _default_roles(policy)
    if [str(item.get("id") or "") for item in default_roles] != REQUIRED_DEFAULT_ROLE_IDS:
        failures.append("policy_default_role_ids_invalid")
    if len(default_roles) != 4:
        failures.append("policy_default_roles_count_invalid")
    if _supervisor_role_keys(policy) != {"operator.admin/administrator", "system.guard/scary"}:
        failures.append("policy_lightweight_supervisors_invalid")
    for item in default_roles:
        role_key = str(item.get("role_key") or "")
        if not SAFE_ID_RE.match(role_key):
            failures.append(f"policy_default_role_key_invalid:{role_key}")
        if item.get("installed_by_default") is not True:
            failures.append(f"policy_default_role_not_installed:{role_key}")
    for item in _optional_rolepacks(policy):
        role_key = str(item.get("role_key") or "")
        if not SAFE_ID_RE.match(role_key):
            failures.append(f"policy_optional_role_key_invalid:{role_key}")
        if str(item.get("activation") or "") != "inactive":
            failures.append(f"policy_optional_rolepack_active:{role_key}")
        if not str(item.get("pack_id") or "").startswith("rolepack."):
            failures.append(f"policy_optional_rolepack_id_invalid:{role_key}")
    manager = policy.get("active_nn_manager") if isinstance(policy.get("active_nn_manager"), dict) else {}
    if manager.get("max_active_heavy_workers") != 1:
        failures.append("policy_active_nn_max_heavy_invalid")
    if manager.get("allow_parallel_heavy_workers") is not False:
        failures.append("policy_parallel_heavy_workers_allowed")
    if manager.get("durable_baton_required") is not True:
        failures.append("policy_durable_baton_not_required")
    if manager.get("sleep_wake_baton_required") is not True:
        failures.append("policy_sleep_wake_baton_not_required")
    boundary = policy.get("evolve_boundary") if isinstance(policy.get("evolve_boundary"), dict) else {}
    if str(boundary.get("mutation_scope") or "") != "lab_only":
        failures.append("policy_evolve_not_lab_only")
    if boundary.get("production_weight_mutation") is not False:
        failures.append("policy_evolve_production_weight_mutation_allowed")
    if _as_string_list(boundary.get("promotion_path")) != REQUIRED_PROMOTION_PATH:
        failures.append("policy_evolve_promotion_path_invalid")
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
        for ref in ["configs/role-kernel-policy.json", "contracts/role_kernel.schema.json", "src/role_kernel_runtime.py"]:
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
    for ref in ["configs/role-kernel-policy.json", "src/role_kernel_runtime.py", "prelaunch/governance/role_kernel.example.json"]:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "entries": entries, "pipeline_eval_refs": pipeline_eval_refs}


def _catalog_failures(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> List[str]:
    failures: List[str] = []
    persona_ref = str(policy.get("persona_catalog_ref") or "")
    role_ref = str(policy.get("role_catalog_ref") or "")
    persona_resolved = _resolve_ref(persona_ref, project_root=project_root, package_root=package_root)
    role_resolved = _resolve_ref(role_ref, project_root=project_root, package_root=package_root)
    if not persona_resolved["ok"]:
        return [f"persona_catalog_missing:{persona_ref}"]
    if not role_resolved["ok"]:
        return [f"role_catalog_missing:{role_ref}"]

    persona_catalog = json.loads(Path(persona_resolved["path"]).read_text(encoding="utf-8"))
    personas = persona_catalog.get("personas") if isinstance(persona_catalog.get("personas"), dict) else {}
    persona_keys = set(personas)
    default_keys = set(_default_role_keys(policy))
    optional_keys = {str(item.get("role_key") or "") for item in _optional_rolepacks(policy)}
    for role_key in sorted(default_keys):
        if role_key not in persona_keys:
            failures.append(f"persona_default_role_missing:{role_key}")
    if persona_keys - default_keys - optional_keys:
        for role_key in sorted(persona_keys - default_keys - optional_keys):
            failures.append(f"persona_role_not_classified:{role_key}")
    if optional_keys - persona_keys:
        for role_key in sorted(optional_keys - persona_keys):
            failures.append(f"persona_optional_role_missing:{role_key}")

    role_text = Path(role_resolved["path"]).read_text(encoding="utf-8")
    for role_key in sorted(default_keys | optional_keys):
        if f"{role_key}:" not in role_text:
            failures.append(f"role_catalog_role_missing:{role_key}")
    return failures


def _kernel_failures(kernel: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    failures: List[str] = []
    kernel_id = str(kernel.get("id") or "<missing>")
    default_keys = set(_default_role_keys(policy))
    heavy_keys = _heavy_role_keys(policy)
    supervisor_keys = _supervisor_role_keys(policy)
    manager = policy.get("active_nn_manager") if isinstance(policy.get("active_nn_manager"), dict) else {}
    if kernel.get("apiVersion") != API_VERSION:
        failures.append(f"kernel_api_version_invalid:{kernel_id}")
    if kernel.get("kind") != KERNEL_KIND:
        failures.append(f"kernel_kind_invalid:{kernel_id}")
    if not SAFE_ID_RE.match(kernel_id):
        failures.append(f"kernel_id_invalid:{kernel_id}")
    if policy.get("require_trace_id") is True and not SAFE_ID_RE.match(str(kernel.get("trace_id") or "")):
        failures.append(f"kernel_trace_id_invalid:{kernel_id}")
    if str(kernel.get("status") or "") not in VALID_KERNEL_STATUSES:
        failures.append(f"kernel_status_invalid:{kernel_id}:{kernel.get('status')}")
    if set(_as_string_list(kernel.get("default_role_keys"))) != default_keys:
        failures.append(f"kernel_default_roles_mismatch:{kernel_id}")
    if set(_as_string_list(kernel.get("always_present_supervisors"))) != supervisor_keys:
        failures.append(f"kernel_supervisors_mismatch:{kernel_id}")
    active_heavy = _as_string_list(kernel.get("active_heavy_workers"))
    if len(active_heavy) > int(manager.get("max_active_heavy_workers") or 0):
        failures.append(f"kernel_too_many_active_heavy_workers:{kernel_id}:{len(active_heavy)}")
    for role_key in active_heavy:
        if role_key not in heavy_keys:
            failures.append(f"kernel_active_heavy_role_not_allowed:{kernel_id}:{role_key}")
    if _as_string_list(kernel.get("optional_rolepacks_active")):
        failures.append(f"kernel_optional_rolepacks_active:{kernel_id}")

    batons = kernel.get("batons") if isinstance(kernel.get("batons"), list) else []
    baton_roles = {str(item.get("role_key") or "") for item in batons if isinstance(item, dict)}
    if manager.get("durable_baton_required") is True or manager.get("sleep_wake_baton_required") is True:
        if not heavy_keys.issubset(baton_roles):
            failures.append(f"kernel_heavy_worker_baton_missing:{kernel_id}")
    for item in batons:
        if not isinstance(item, dict):
            failures.append(f"kernel_baton_not_object:{kernel_id}")
            continue
        baton_id = str(item.get("id") or "")
        role_key = str(item.get("role_key") or "")
        if not SAFE_ID_RE.match(baton_id):
            failures.append(f"kernel_baton_id_invalid:{kernel_id}:{baton_id}")
        if role_key not in default_keys:
            failures.append(f"kernel_baton_role_not_default:{kernel_id}:{role_key}")
        if manager.get("durable_baton_required") is True and item.get("durable") is not True:
            failures.append(f"kernel_baton_not_durable:{kernel_id}:{role_key}")
        if manager.get("sleep_wake_baton_required") is True and item.get("sleep_wake") is not True:
            failures.append(f"kernel_baton_not_sleep_wake:{kernel_id}:{role_key}")
    boundary = kernel.get("evolve_boundary") if isinstance(kernel.get("evolve_boundary"), dict) else {}
    if str(boundary.get("mutation_scope") or "") != "lab_only":
        failures.append(f"kernel_evolve_not_lab_only:{kernel_id}")
    if boundary.get("production_weight_mutation") is not False:
        failures.append(f"kernel_evolve_production_weight_mutation_allowed:{kernel_id}")
    if _as_string_list(boundary.get("promotion_path")) != REQUIRED_PROMOTION_PATH:
        failures.append(f"kernel_evolve_promotion_path_invalid:{kernel_id}")
    return failures


def validate_role_kernel_policy(
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
    failures.extend(_catalog_failures(policy, project_root=project, package_root=package))
    registry_result = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_result["failures"])

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    kernel_results: List[Dict[str, Any]] = []

    refs_to_resolve = _as_string_list(payload.get("refs"))
    refs_to_resolve.extend([str(policy.get("persona_catalog_ref") or ""), str(policy.get("role_catalog_ref") or "")])
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

    for item in example_ref_results["resolved_refs"]:
        example_set = load_example_set(Path(item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{item['ref']}")
        kernels = example_set.get("kernels") if isinstance(example_set.get("kernels"), list) else []
        if not kernels:
            failures.append(f"example_set_kernels_empty:{item['ref']}")
        for kernel in kernels:
            if not isinstance(kernel, dict):
                failures.append(f"kernel_not_object:{item['ref']}")
                continue
            kernel_id = str(kernel.get("id") or "<missing>")
            kernel_failures = _kernel_failures(kernel, payload)
            kernel_ref_result = _resolve_refs(_as_string_list(kernel.get("refs")), project_root=project, package_root=package, owner=kernel_id)
            kernel_failures.extend(kernel_ref_result["failures"])
            failures.extend(kernel_failures)
            all_resolved_refs.extend(kernel_ref_result["resolved_refs"])
            all_missing_refs.extend(kernel_ref_result["missing_refs"])
            all_unsafe_refs.extend(kernel_ref_result["unsafe_refs"])
            kernel_results.append(
                {
                    "id": kernel_id,
                    "ok": not kernel_failures,
                    "default_roles": len(_as_string_list(kernel.get("default_role_keys"))),
                    "active_heavy_workers": len(_as_string_list(kernel.get("active_heavy_workers"))),
                    "failures": sorted(set(kernel_failures)),
                }
            )

    checks = [
        {"id": "base_roles", "status": "passed" if not any("default_role" in item or "persona_default" in item for item in failures) else "failed"},
        {"id": "optional_rolepacks_inactive", "status": "passed" if not any("optional_rolepack" in item for item in failures) else "failed"},
        {"id": "one_heavy_worker", "status": "passed" if not any("heavy_worker" in item or "parallel_heavy" in item for item in failures) else "failed"},
        {"id": "evolve_lab_boundary", "status": "passed" if not any("evolve" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "kernels": len(kernel_results),
        "passing_kernels": sum(1 for item in kernel_results if item["ok"]),
        "default_roles": len(_default_roles(policy)),
        "optional_rolepacks": len(_optional_rolepacks(policy)),
        "heavy_default_roles": len(_heavy_role_keys(policy)),
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
        "kernel_results": sorted(kernel_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def role_kernel_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("role_kernel_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge protected role kernel contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/role-kernel-policy.json",
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

    report = validate_role_kernel_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "RoleKernelValidationSummary",
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
