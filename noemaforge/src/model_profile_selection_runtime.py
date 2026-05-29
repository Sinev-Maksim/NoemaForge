#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/model_profile_selection_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate profile-driven model staging and firstboot profile selection contracts.
Inputs: Model Profile Selection policy, model profile manifests, setup/firstboot scripts and docs.
Outputs: JSON-compatible ModelProfileSelectionValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_model_profile_selection_runtime.py
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


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import model_profiles
import unified_registry_runtime as urr


API_VERSION = "noemaforge.model-profile-selection/v1"
POLICY_KIND = "ModelProfileSelectionPolicy"
SET_KIND = "ModelProfileSelectionExampleSet"
REPORT_KIND = "ModelProfileSelectionValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_PROFILES = ["minimal", "balanced", "writer", "research", "gpu-heavy"]
REQUIRED_PROFILE_FIELDS = ["description", "max_active_llms", "default_runtime", "ram_gib_min", "vram_gib_min", "model_hints", "roles"]
REGISTRY_REFS = [
    "configs/model-profile-selection-policy.json",
    "contracts/model_profile_selection.schema.json",
    "configs/model-profiles.json",
    "configs/model-profiles.yaml",
    "src/model_profiles.py",
    "src/model_profile_selection_runtime.py",
    "src/firstboot_orchestrator.py",
    "tools/prep/noemaforge-first-launch.sh",
    "tools/prep/noemaforge-firstboot-from-share.sh",
    "setup.sh",
    "bin/noemaforge",
    "tests/test_model_profile_selection_runtime.py",
    "tests/test_model_profile_selection_qa.py",
    "tests/test_model_profile_selection_performance.py",
    "prelaunch/governance/model_profile_selection.example.json",
]
PIPELINE_REFS = [
    "configs/model-profile-selection-policy.json",
    "contracts/model_profile_selection.schema.json",
    "configs/model-profiles.json",
    "src/model_profiles.py",
    "src/model_profile_selection_runtime.py",
    "prelaunch/governance/model_profile_selection.example.json",
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
    if str(policy.get("activation_state") or "") != "profile_driven_model_staging":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["profile_manifest_ref", "runtime_ref", "firstboot_ref", "setup_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if _as_string_list(policy.get("required_profiles")) != REQUIRED_PROFILES:
        failures.append("policy_required_profiles_invalid")
    if not set(REQUIRED_PROFILE_FIELDS).issubset(set(_as_string_list(policy.get("required_profile_fields")))):
        failures.append("policy_required_profile_fields_missing")
    if not _as_string_list(policy.get("required_cli_surfaces")):
        failures.append("policy_required_cli_surfaces_empty")
    if not _as_string_list(policy.get("required_boundary_refs")):
        failures.append("policy_required_boundary_refs_empty")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _profile_failures(*, package_root: Path) -> Dict[str, Any]:
    profiles = model_profiles.load_profiles(package_root)
    report = model_profiles.validate_profiles(profiles)
    failures = [f"profile_invalid:{item}" for item in report.get("failures", [])]
    manifests: Dict[str, Dict[str, Any]] = {}
    for name in REQUIRED_PROFILES:
        manifest = model_profiles.build_profile_manifest(profiles, name)
        manifests[name] = manifest
        if manifest.get("runtime", {}).get("max_active_llms") != 1:
            failures.append(f"manifest_max_active_llms_not_one:{name}")
        if any(item.get("auto_download") is not False for item in manifest.get("fetch_candidates", [])):
            failures.append(f"manifest_auto_download_not_false:{name}")
        if not manifest.get("stage_roles"):
            failures.append(f"manifest_stage_roles_empty:{name}")
    return {"failures": failures, "report": report, "manifests": manifests}


def _surface_failures(*, project_root: Path, package_root: Path) -> Dict[str, Any]:
    refs = {
        "setup": "setup.sh",
        "first_launch": "tools/prep/noemaforge-first-launch.sh",
        "firstboot_from_share": "tools/prep/noemaforge-firstboot-from-share.sh",
        "orchestrator": "src/firstboot_orchestrator.py",
        "cli": "bin/noemaforge",
        "runtime": "src/model_profiles.py",
    }
    failures: List[str] = []
    texts: Dict[str, str] = {}
    resolved: Dict[str, Any] = {}
    for name, ref in refs.items():
        res = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        resolved[name] = res
        texts[name] = Path(res["path"]).read_text(encoding="utf-8") if res.get("ok") else ""
        if not res.get("ok"):
            failures.append(f"surface_missing:{name}:{ref}")
    for name in ["setup", "first_launch", "firstboot_from_share", "orchestrator"]:
        if "--model-profile" not in texts.get(name, ""):
            failures.append(f"surface_model_profile_flag_missing:{name}")
        for profile in REQUIRED_PROFILES:
            if profile not in texts.get(name, ""):
                failures.append(f"surface_profile_name_missing:{name}:{profile}")
    if "profiles|model-profiles|profile" not in texts.get("cli", ""):
        failures.append("cli_profiles_dispatch_missing")
    for command in ["list", "show", "recommend", "plan"]:
        if command not in texts.get("runtime", ""):
            failures.append(f"runtime_command_missing:{command}")
    if "model-profile-manifest.json" not in texts.get("orchestrator", ""):
        failures.append("orchestrator_manifest_output_missing")
    return {"failures": failures, "resolved": resolved}


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
        for ref in REGISTRY_REFS:
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
    for ref in PIPELINE_REFS:
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


def _example_failures(example_set: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    if example_set.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example_set.get("kind") != SET_KIND:
        failures.append("example_kind_invalid")
    scenarios = example_set.get("scenarios") if isinstance(example_set.get("scenarios"), list) else []
    if not scenarios:
        failures.append("example_scenarios_empty")
    profiles = model_profiles.load_profiles(package_root)
    scenario_reports: List[Dict[str, Any]] = []
    for scenario in scenarios:
        sid = str(scenario.get("id") or "scenario")
        expected = scenario.get("expected") if isinstance(scenario.get("expected"), dict) else {}
        local: List[str] = []
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local.append("trace_id_invalid")
        manifest = model_profiles.build_profile_manifest(profiles, str(scenario.get("profile") or "minimal"))
        if expected.get("ok") is not True:
            local.append("expected_ok_not_true")
        if expected.get("auto_download") is False and any(item.get("auto_download") is not False for item in manifest.get("fetch_candidates", [])):
            local.append("auto_download_not_false")
        if expected.get("max_active_llms") == 1 and manifest.get("runtime", {}).get("max_active_llms") != 1:
            local.append("max_active_llms_not_one")
        required_role_hint = str(expected.get("required_role_hint") or "")
        if required_role_hint and not any(required_role_hint in role for role in manifest.get("stage_roles", [])):
            local.append(f"required_role_hint_missing:{required_role_hint}")
        for field in _as_string_list(expected.get("required_manifest_fields")):
            if field not in manifest:
                local.append(f"manifest_field_missing:{field}")
        scenario_reports.append({"id": sid, "ok": not local, "failures": local, "manifest": manifest})
        failures.extend([f"scenario:{sid}:{item}" for item in local])
    return {"failures": failures, "scenario_reports": scenario_reports}


def validate_model_profile_selection_policy(
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
    profile_report = _profile_failures(package_root=package)
    failures.extend(profile_report["failures"])
    surface_report = _surface_failures(project_root=project, package_root=package)
    failures.extend(surface_report["failures"])
    registry_report = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_report["failures"])
    docs_report = _docs_failures(payload, project_root=project, package_root=package)
    failures.extend(docs_report["failures"])
    example_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project, package_root=package)
        if not resolved.get("ok"):
            failures.append(f"example_ref_missing:{ref}")
            continue
        example_report = _example_failures(load_example_set(resolved["path"]), package_root=package)
        failures.extend(example_report["failures"])
        example_reports.append({"ref": ref, **example_report})
    metrics = {
        "profiles": len(profile_report.get("manifests", {})),
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "boundary_refs": len(docs_report["boundary_reports"]),
        "examples": len(example_reports),
        "registry_entries": len(registry_report.get("registry_report", {}).get("normalized_registry", {}).get("entries", [])),
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
        "profiles": profile_report,
        "surfaces": surface_report,
        "registry": registry_report,
        "docs": docs_report,
        "examples": example_reports,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "ModelProfileSelectionValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge model profile selection contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "model-profile-selection-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_model_profile_selection_policy(
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
