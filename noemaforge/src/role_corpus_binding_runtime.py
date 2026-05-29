#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/role_corpus_binding_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate role-scoped eval suites and honest corpus availability bindings.
Inputs: Role Corpus Binding policy, role-eval catalog, unified registry, docs and offline examples.
Outputs: JSON-compatible RoleCorpusBindingValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_role_corpus_binding_runtime.py
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
from typing import Any, Dict, List, Sequence

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unified_registry_runtime as urr


API_VERSION = "noemaforge.role-corpus-binding/v1"
POLICY_KIND = "RoleCorpusBindingPolicy"
SET_KIND = "RoleCorpusBindingExampleSet"
REPORT_KIND = "RoleCorpusBindingValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_CONTROLS = {
    "role_scoped_catalog_required",
    "jsonl_suite_required_for_seed_profiles",
    "real_corpus_binding_required",
    "missing_corpus_marks_na",
    "no_synthetic_coverage_for_missing_corpus",
    "firstboot_surface_uses_catalog",
    "no_live_host_required",
}
REQUIRED_REGISTRY_REFS = [
    "configs/role-corpus-binding-policy.json",
    "contracts/role_corpus_binding.schema.json",
    "configs/role-eval-datasets.yaml",
    "contracts/role_eval_datasets.schema.json",
    "datasets/role_eval_cases/administrator_smoke.jsonl",
    "datasets/role_eval_cases/dev_work_smoke.jsonl",
    "datasets/role_eval_cases/writing_story_smoke.jsonl",
    "src/role_corpus_binding_runtime.py",
    "src/firstboot_eval.py",
    "src/dataset_inventory.py",
    "src/model_scorecards.py",
    "tests/test_role_corpus_binding_runtime.py",
    "tests/test_role_corpus_binding_qa.py",
    "tests/test_role_corpus_binding_performance.py",
    "prelaunch/governance/role_corpus_binding.example.json",
]
REQUIRED_PIPELINE_REFS = [
    "configs/role-corpus-binding-policy.json",
    "contracts/role_corpus_binding.schema.json",
    "src/role_corpus_binding_runtime.py",
    "prelaunch/governance/role_corpus_binding.example.json",
]


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


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _contains(text: str, needle: str) -> bool:
    return _norm(needle) in _norm(text)


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("~"):
        return False
    if text.startswith("/") and not text.startswith("/opt/noemaforge/"):
        return False
    parts = PurePosixPath(text.lstrip("/")).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _localize_ref(ref: str) -> str:
    text = str(ref or "").strip().replace("\\", "/")
    prefix = "/opt/noemaforge/"
    if text.startswith(prefix):
        return text[len(prefix):]
    return text.lstrip("/")


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    local = _localize_ref(ref)
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


def _parse_bool_or_text(value: str) -> Any:
    text = str(value or "").strip()
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    return text.strip("\"'")


def _load_role_eval_catalog_fallback(text: str) -> Dict[str, Any]:
    doc: Dict[str, Any] = {"profiles": {}, "roles": {}}
    section = ""
    current_profile = ""
    current_role = ""
    current_check: Dict[str, Any] | None = None
    in_available_when = False
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0 and line.endswith(":"):
            section = line[:-1]
            current_profile = ""
            current_role = ""
            in_available_when = False
            continue
        if indent == 0 and ":" in line:
            key, value = line.split(":", 1)
            doc[key.strip()] = _parse_bool_or_text(value)
            continue
        if section == "profiles":
            if indent == 2 and line.endswith(":"):
                current_profile = line[:-1]
                doc["profiles"][current_profile] = {}
                in_available_when = False
                continue
            if not current_profile:
                continue
            profile = doc["profiles"][current_profile]
            if indent == 4 and line == "available_when:":
                profile["available_when"] = []
                in_available_when = True
                continue
            if in_available_when and indent == 4 and line.startswith("- "):
                current_check = {}
                profile.setdefault("available_when", []).append(current_check)
                item = line[2:].strip()
                if ":" in item:
                    key, value = item.split(":", 1)
                    current_check[key.strip()] = _parse_bool_or_text(value)
                continue
            if in_available_when and indent == 6 and current_check is not None and ":" in line:
                key, value = line.split(":", 1)
                current_check[key.strip()] = _parse_bool_or_text(value)
                continue
            if indent == 4 and ":" in line:
                key, value = line.split(":", 1)
                profile[key.strip()] = _parse_bool_or_text(value)
                in_available_when = False
                continue
        if section == "roles":
            if indent == 2 and line.endswith(":"):
                current_role = line[:-1]
                doc["roles"][current_role] = {}
                continue
            if current_role and indent == 4 and ":" in line:
                key, value = line.split(":", 1)
                doc["roles"][current_role][key.strip()] = _parse_bool_or_text(value)
                continue
    return doc


def load_role_eval_catalog(catalog_path: Path | str) -> Dict[str, Any]:
    path = Path(catalog_path)
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    text = path.read_text(encoding="utf-8")
    if yaml is None:
        return _load_role_eval_catalog_fallback(text)
    loaded = yaml.safe_load(text) or {}
    return loaded if isinstance(loaded, dict) else {}


def _path_available(check: Dict[str, Any], *, project_root: Path, package_root: Path) -> bool:
    resolved = _resolve_ref(str(check.get("path") or ""), project_root=project_root, package_root=package_root)
    if not resolved.get("ok"):
        return False
    path = Path(str(resolved["path"]))
    kind = str(check.get("kind") or "")
    if kind == "dir":
        return path.is_dir()
    if kind == "file":
        return path.is_file()
    return path.exists()


def resolve_role_corpus_bindings(
    catalog: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    profiles = catalog.get("profiles") if isinstance(catalog.get("profiles"), dict) else {}
    roles = catalog.get("roles") if isinstance(catalog.get("roles"), dict) else {}
    bindings: List[Dict[str, Any]] = []
    failures: List[str] = []
    jsonl_files = list((package / "datasets" / "role_eval_cases").glob("*.jsonl"))
    for role_key, role_cfg in sorted(roles.items()):
        if not isinstance(role_cfg, dict):
            failures.append(f"role_config_not_object:{role_key}")
            continue
        suite = str(role_cfg.get("suite") or "").strip()
        profile_name = str(role_cfg.get("dataset_profile") or "").strip()
        if not suite:
            failures.append(f"role_suite_missing:{role_key}")
        if not profile_name:
            failures.append(f"role_dataset_profile_missing:{role_key}")
        profile = profiles.get(profile_name) if isinstance(profiles.get(profile_name), dict) else {}
        if not profile:
            bindings.append({"role_key": role_key, "suite": suite, "dataset_profile": profile_name, "binding_status": "N/A", "reason": "profile_missing", "corpus_type": ""})
            continue
        corpus_type = str(profile.get("type") or "")
        checks = profile.get("available_when") if isinstance(profile.get("available_when"), list) else []
        available = any(_path_available(check, project_root=project, package_root=package) for check in checks if isinstance(check, dict))
        if corpus_type == "seed_jsonl" and profile_name == "internal_jsonl":
            available = available and bool(jsonl_files)
        status = "available" if available else "N/A"
        reason = "" if available else "dataset_missing"
        bindings.append(
            {
                "role_key": role_key,
                "suite": suite,
                "dataset_profile": profile_name,
                "corpus_type": corpus_type,
                "binding_status": status,
                "reason": reason,
                "coverage_claimed": available,
            }
        )
    return {
        "apiVersion": API_VERSION,
        "kind": "RoleCorpusBindingResolution",
        "ok": not failures,
        "generated_at": _nowz(),
        "failures": failures,
        "bindings": bindings,
        "metrics": {
            "roles": len(roles),
            "profiles": len(profiles),
            "available_roles": sum(1 for item in bindings if item.get("binding_status") == "available"),
            "na_roles": sum(1 for item in bindings if item.get("binding_status") == "N/A"),
            "jsonl_files": len(jsonl_files),
        },
    }


def _catalog_failures(catalog: Dict[str, Any], *, policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    if catalog.get("apiVersion") != "noemaforge.roleeval/v1":
        failures.append("catalog_api_version_invalid")
    if catalog.get("kind") != "RoleEvalDatasets":
        failures.append("catalog_kind_invalid")
    profiles = catalog.get("profiles") if isinstance(catalog.get("profiles"), dict) else {}
    roles = catalog.get("roles") if isinstance(catalog.get("roles"), dict) else {}
    if not profiles:
        failures.append("catalog_profiles_empty")
    if not roles:
        failures.append("catalog_roles_empty")
    required_role_fields = _as_string_list(policy.get("required_role_fields"))
    required_profile_fields = _as_string_list(policy.get("required_profile_fields"))
    corpus_types = set(_as_string_list(policy.get("required_corpus_types")))
    for profile_name, profile in profiles.items():
        if not isinstance(profile, dict):
            failures.append(f"profile_not_object:{profile_name}")
            continue
        for field in required_profile_fields:
            if field not in profile:
                failures.append(f"profile_field_missing:{profile_name}:{field}")
        if str(profile.get("type") or "") not in corpus_types:
            failures.append(f"profile_type_unknown:{profile_name}:{profile.get('type')}")
    for role_key, role_cfg in roles.items():
        if "/" not in str(role_key):
            failures.append(f"role_key_not_scoped:{role_key}")
        if not isinstance(role_cfg, dict):
            failures.append(f"role_config_not_object:{role_key}")
            continue
        for field in required_role_fields:
            if not str(role_cfg.get(field) or "").strip():
                failures.append(f"role_field_missing:{role_key}:{field}")
        profile_name = str(role_cfg.get("dataset_profile") or "")
        if profile_name and profile_name not in profiles:
            failures.append(f"role_profile_missing:{role_key}:{profile_name}")
    return failures


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
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
    if str(policy.get("activation_state") or "") != "role_eval_requires_corpus_binding":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["role_eval_catalog_ref", "role_eval_schema_ref", "seed_dataset_root_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["required_role_fields", "required_profile_fields", "required_binding_statuses", "required_corpus_types", "required_boundary_refs", "required_runtime_refs", "required_example_sets"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    if str(policy.get("required_na_reason") or "") != "dataset_missing":
        failures.append("policy_required_na_reason_invalid")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
    return failures


def _registry_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures = [f"registry_invalid:{item}" for item in report.get("failures", [])]
    entries = {_registry_ref(entry): entry for entry in report.get("normalized_registry", {}).get("entries", []) if isinstance(entry, dict)}
    raw_entries = {_registry_ref(entry): entry for entry in registry.get("entries", []) if isinstance(entry, dict)}
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    eval_entry = entries.get(eval_ref)
    if not eval_entry:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    else:
        refs = set(_as_string_list(eval_entry.get("refs")))
        for ref in REQUIRED_REGISTRY_REFS:
            if ref not in refs:
                failures.append(f"registry_eval_pack_ref_missing:{eval_ref}:{ref}")
    pipeline_ref = str(policy.get("required_pipeline_ref") or "")
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    pipeline_eval_refs: List[str] = []
    pipeline_refs: List[str] = []
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
    else:
        pipeline_eval_refs = _as_string_list(pipeline.get("eval_pack_refs"))
        pipeline_refs = _as_string_list(pipeline.get("refs"))
    if eval_ref not in pipeline_eval_refs:
        failures.append(f"registry_pipeline_eval_pack_missing:{eval_ref}")
    for ref in REQUIRED_PIPELINE_REFS:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "pipeline_eval_refs": pipeline_eval_refs, "pipeline_refs": pipeline_refs}


def _docs_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    boundary = str(policy.get("boundary_phrase") or "")
    failures: List[str] = []
    boundary_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_boundary_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        has_phrase = False
        if resolved.get("ok"):
            has_phrase = _contains(Path(resolved["path"]).read_text(encoding="utf-8"), boundary)
        else:
            failures.append(f"boundary_ref_missing:{ref}")
        if resolved.get("ok") and not has_phrase:
            failures.append(f"boundary_phrase_missing:{ref}")
        boundary_reports.append({"ref": ref, "ok": bool(resolved.get("ok")) and has_phrase, "has_phrase": has_phrase, "resolved": resolved})
    return {"failures": failures, "boundary_reports": boundary_reports}


def _example_failures(example_set: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    scenario_reports: List[Dict[str, Any]] = []
    passing_scenarios = 0
    if example_set.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example_set.get("kind") != SET_KIND:
        failures.append("example_kind_invalid")
    scenarios = example_set.get("scenarios") if isinstance(example_set.get("scenarios"), list) else []
    if not scenarios:
        failures.append("example_scenarios_empty")
    for scenario in scenarios:
        sid = str(scenario.get("id") or "scenario")
        local_failures: List[str] = []
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local_failures.append("scenario_trace_id_invalid")
        catalog = scenario.get("catalog") if isinstance(scenario.get("catalog"), dict) else {}
        resolution = resolve_role_corpus_bindings(catalog, project_root=project_root, package_root=package_root)
        bindings = {str(item.get("role_key")): item for item in resolution.get("bindings", [])}
        for role_key, expected in (scenario.get("expected") or {}).items():
            actual = bindings.get(str(role_key))
            if not actual:
                local_failures.append(f"scenario_binding_missing:{role_key}")
                continue
            for key, value in expected.items():
                if actual.get(key) != value:
                    local_failures.append(f"scenario_binding_mismatch:{role_key}:{key}:{value}:{actual.get(key)}")
        scenario_reports.append({"id": sid, "ok": not local_failures, "failures": local_failures, "resolution": resolution})
        if local_failures:
            failures.extend([f"scenario:{sid}:{item}" for item in local_failures])
        else:
            passing_scenarios += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "passing_scenarios": passing_scenarios}


def validate_role_corpus_binding_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Path | str | None = None,
    registry_path: Path | str | None = None,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    registry = Path(registry_path).resolve() if registry_path else package / "configs" / "unified-registry.json"
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(ref_report["failures"])
    for key in ["role_eval_catalog_ref", "role_eval_schema_ref", "seed_dataset_root_ref"]:
        resolved = _resolve_ref(str(policy.get(key) or ""), project_root=project, package_root=package)
        if not resolved.get("ok"):
            failures.append(f"{key}_missing:{policy.get(key)}")
    catalog_path = _resolve_ref(str(policy.get("role_eval_catalog_ref") or ""), project_root=project, package_root=package)
    catalog = load_role_eval_catalog(catalog_path["path"]) if catalog_path.get("ok") else {}
    failures.extend(_catalog_failures(catalog, policy=policy))
    resolution = resolve_role_corpus_bindings(catalog, project_root=project, package_root=package)
    failures.extend([f"catalog_resolution:{item}" for item in resolution.get("failures", [])])
    if int(resolution.get("metrics", {}).get("available_roles") or 0) <= 0:
        failures.append("no_available_role_bindings")
    if int(resolution.get("metrics", {}).get("na_roles") or 0) <= 0:
        failures.append("no_na_role_bindings_for_missing_corpora")
    for item in resolution.get("bindings", []):
        if item.get("binding_status") == "N/A" and item.get("coverage_claimed") is not False:
            failures.append(f"na_role_claims_coverage:{item.get('role_key')}")
    registry_report = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_report["failures"])
    docs_report = _docs_failures(payload, project_root=project, package_root=package)
    failures.extend(docs_report["failures"])
    runtime_refs = _resolve_refs(_as_string_list(policy.get("required_runtime_refs")), project_root=project, package_root=package, owner="runtime_refs")
    failures.extend(runtime_refs["failures"])
    example_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project, package_root=package)
        if not resolved.get("ok"):
            failures.append(f"example_ref_missing:{ref}")
            continue
        example_report = _example_failures(load_example_set(resolved["path"]), project_root=project, package_root=package)
        failures.extend(example_report["failures"])
        example_reports.append({"ref": ref, **example_report})
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "boundary_refs": len(docs_report["boundary_reports"]),
        "runtime_refs": len(runtime_refs["resolved_refs"]),
        "roles": int(resolution.get("metrics", {}).get("roles") or 0),
        "profiles": int(resolution.get("metrics", {}).get("profiles") or 0),
        "available_roles": int(resolution.get("metrics", {}).get("available_roles") or 0),
        "na_roles": int(resolution.get("metrics", {}).get("na_roles") or 0),
        "jsonl_files": int(resolution.get("metrics", {}).get("jsonl_files") or 0),
        "scenarios": sum(int(item.get("scenarios") or 0) for item in example_reports),
        "passing_scenarios": sum(int(item.get("passing_scenarios") or 0) for item in example_reports),
        "registry_entries": len(registry_report.get("registry_report", {}).get("normalized_registry", {}).get("entries", [])),
        "checked_controls": len(REQUIRED_CONTROLS),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "id": str(payload.get("id") or ""),
        "version": str(payload.get("version") or ""),
        "ok": not failures,
        "validated_at": _nowz(),
        "policy_path": _display_path(Path(policy_path).resolve()) if policy_path else "",
        "failures": failures,
        "metrics": metrics,
        "refs": ref_report,
        "catalog_resolution": resolution,
        "registry": registry_report,
        "docs": docs_report,
        "runtime_refs": runtime_refs,
        "examples": example_reports,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "RoleCorpusBindingValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge role corpus binding contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "role-corpus-binding-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_role_corpus_binding_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
        registry_path=Path(args.registry) if args.registry else None,
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
