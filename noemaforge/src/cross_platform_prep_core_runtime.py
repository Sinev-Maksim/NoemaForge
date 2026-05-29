#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/cross_platform_prep_core_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate cross-platform prep core, thin wrappers and no-Windows-required firstboot staging.
Inputs: Cross-platform prep policy, wrappers, prep core, docs and Unified Registry.
Outputs: JSON-compatible CrossPlatformPrepCoreValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_cross_platform_prep_core_runtime.py
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
PACKAGE_ROOT = SRC_DIR.parent
PROJECT_ROOT = PACKAGE_ROOT.parent
PREP_DIR = PACKAGE_ROOT / "tools" / "prep"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PREP_DIR) not in sys.path:
    sys.path.insert(0, str(PREP_DIR))

import noemaforge_prep_core as prep_core
import unified_registry_runtime as urr


API_VERSION = "noemaforge.cross-platform-prep/v1"
POLICY_KIND = "CrossPlatformPrepCorePolicy"
SET_KIND = "CrossPlatformPrepCoreExampleSet"
REPORT_KIND = "CrossPlatformPrepCoreValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_COMMANDS = ["verify-seed", "check", "lab", "firstboot", "export-vault-metadata", "export-compare-metadata"]
REQUIRED_CAPABILITIES = ["vault_scan", "inbox_processing", "metadata_export", "firstboot_staging", "windows_not_required"]
REGISTRY_REFS = [
    "configs/cross-platform-prep-core-policy.json",
    "contracts/cross_platform_prep_core.schema.json",
    "tools/prep/noemaforge_prep_core.py",
    "src/cross_platform_prep_core_runtime.py",
    "tools/prep/process_inbox.py",
    "tools/prep/scan_vault.py",
    "tools/prep/scan_library.py",
    "tools/prep/run_verify.sh",
    "tools/prep/run_check.sh",
    "tools/prep/run_lab.sh",
    "tools/prep/run_firstboot.sh",
    "tools/windows/run_verify.cmd",
    "tools/windows/run_check.cmd",
    "tools/windows/run_lab.cmd",
    "tools/windows/run_firstboot.cmd",
    "tools/windows/run_firstboot.ps1",
    "tools/windows/Export-NoemaForge-E-Vault-Metadata.ps1",
    "tools/windows/Export-NoemaForge-E-Compare-Metadata.ps1",
    "bin/noemaforge",
    "tests/test_cross_platform_prep_core_runtime.py",
    "tests/test_cross_platform_prep_core_qa.py",
    "tests/test_cross_platform_prep_core_performance.py",
    "prelaunch/governance/cross_platform_prep_core.example.json",
    "docs/README.md",
    "docs/TODO.md",
    "docs/backlog/ROADMAP_AND_TODO.md",
    "docs/history/CHANGELOG.md",
    "docs/reference/PROJECT_CONTEXT.md",
]
PIPELINE_REFS = [
    "configs/cross-platform-prep-core-policy.json",
    "contracts/cross_platform_prep_core.schema.json",
    "tools/prep/noemaforge_prep_core.py",
    "src/cross_platform_prep_core_runtime.py",
    "prelaunch/governance/cross_platform_prep_core.example.json",
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
    if str(policy.get("activation_state") or "") != "python_prep_core_source_of_truth":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    if str(policy.get("python_core_ref") or "") != "tools/prep/noemaforge_prep_core.py":
        failures.append("policy_python_core_ref_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_windows_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for cmd in REQUIRED_COMMANDS:
        if cmd not in _as_string_list(policy.get("required_core_commands")):
            failures.append(f"policy_command_missing:{cmd}")
    for capability in REQUIRED_CAPABILITIES:
        if capability not in _as_string_list(policy.get("required_capabilities")):
            failures.append(f"policy_capability_missing:{capability}")
    for key in ["required_python_surfaces", "required_windows_wrappers", "required_shell_wrappers", "required_boundary_refs", "required_example_sets"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def analyze_prep_surfaces(*, project_root: Path, package_root: Path, policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    resolved_refs: List[Dict[str, Any]] = []
    refs = (
        _as_string_list(policy.get("required_python_surfaces"))
        + _as_string_list(policy.get("required_windows_wrappers"))
        + _as_string_list(policy.get("required_shell_wrappers"))
        + ["bin/noemaforge"]
    )
    for ref in refs:
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            failures.append(f"surface_missing:{ref}")
            continue
        text = Path(resolved["path"]).read_text(encoding="utf-8")
        if ref.endswith((".cmd", ".ps1", ".sh")) and "noemaforge_prep_core.py" not in text:
            failures.append(f"wrapper_not_delegating_to_python_core:{ref}")
        if ref == "bin/noemaforge" and "prep-core|prep|cross-platform-prep" not in text:
            failures.append("cli_prep_core_dispatch_missing")
    core_text = (package_root / "tools" / "prep" / "noemaforge_prep_core.py").read_text(encoding="utf-8")
    for cmd in REQUIRED_COMMANDS:
        if f'"{cmd}"' not in core_text and f"'{cmd}'" not in core_text:
            failures.append(f"core_command_missing:{cmd}")
    for needle in ["process_inbox", "scan_vault", "scan_library", "FirstbootStagingPlan", "disk_e_metadata"]:
        if needle not in core_text:
            failures.append(f"core_capability_marker_missing:{needle}")
    return {"failures": failures, "resolved_refs": resolved_refs}


def evaluate_example_set(example_set: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    if example_set.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example_set.get("kind") != SET_KIND:
        failures.append("example_kind_invalid")
    scenarios = example_set.get("scenarios") if isinstance(example_set.get("scenarios"), list) else []
    if len(scenarios) < 2:
        failures.append("example_scenarios_missing")
    for scenario in scenarios:
        commands = _as_string_list(scenario.get("commands"))
        if not commands:
            failures.append(f"example_commands_empty:{scenario.get('id')}")
        if scenario.get("platform") == "linux_or_macos":
            for cmd in REQUIRED_COMMANDS[:4]:
                if not any(cmd in command for command in commands):
                    failures.append(f"example_linux_command_missing:{cmd}")
        if scenario.get("windows_required") is True or scenario.get("windows_required_for_core_prep") is True:
            failures.append(f"example_requires_windows:{scenario.get('id')}")
    return {"ok": not failures, "failures": failures, "scenarios": len(scenarios)}


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
            failures.append(f"registry_pipeline_eval_pack_ref_missing:{pipeline_ref}:{eval_ref}")
        for ref in PIPELINE_REFS:
            if ref not in pipeline_refs:
                failures.append(f"registry_pipeline_ref_missing:{pipeline_ref}:{ref}")
    return {
        "failures": failures,
        "registry_report": report,
        "eval_ref": eval_ref,
        "pipeline_ref": pipeline_ref,
        "pipeline_eval_refs": pipeline_eval_refs,
        "pipeline_refs": pipeline_refs,
    }


def validate_cross_platform_prep_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    package_root: Path = PACKAGE_ROOT,
    registry_path: Path | None = None,
) -> Dict[str, Any]:
    registry_path = registry_path or (package_root / "configs" / "unified-registry.json")
    policy = _policy_dict(payload)
    failures = _policy_failures(payload)
    resolved = _resolve_refs(payload.get("refs", []), project_root=project_root, package_root=package_root, owner=str(payload.get("id") or "policy"))
    failures.extend(resolved["failures"])
    surfaces = analyze_prep_surfaces(project_root=project_root, package_root=package_root, policy=policy)
    failures.extend(surfaces["failures"])
    registry = _registry_failures(payload, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures.extend(registry["failures"])

    boundary_phrase = str(policy.get("boundary_phrase") or "")
    boundary_hits: List[str] = []
    for ref in _as_string_list(policy.get("required_boundary_refs")):
        resolved_ref = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved_ref["ok"]:
            failures.append(f"boundary_ref_missing:{ref}")
            continue
        text = Path(resolved_ref["path"]).read_text(encoding="utf-8")
        if _contains(text, boundary_phrase):
            boundary_hits.append(ref)
        else:
            failures.append(f"boundary_phrase_missing:{ref}")

    example_results: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved_ref = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved_ref["ok"]:
            failures.append(f"example_ref_missing:{ref}")
            continue
        evaluated = evaluate_example_set(load_example_set(Path(resolved_ref["path"])))
        example_results.append({"ref": ref, **evaluated})
        failures.extend([f"example_invalid:{ref}:{item}" for item in evaluated["failures"]])

    seed = prep_core.verify_seed(package_root)
    if not seed.get("ok"):
        failures.append("prep_core_seed_verification_failed")

    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "failures": failures,
        "policy_id": payload.get("id"),
        "registry": {
            "eval_ref": registry["eval_ref"],
            "pipeline_ref": registry["pipeline_ref"],
            "pipeline_eval_refs": registry["pipeline_eval_refs"],
        },
        "examples": example_results,
        "seed": seed,
        "resolved_refs": resolved["resolved_refs"],
        "surface_refs": surfaces["resolved_refs"],
        "metrics": {
            "refs": len(payload.get("refs", [])) if isinstance(payload.get("refs"), list) else 0,
            "resolved_refs": len(resolved["resolved_refs"]),
            "surface_refs": len(surfaces["resolved_refs"]),
            "boundary_refs": len(boundary_hits),
            "examples": len(example_results),
            "registry_entries": len(registry["registry_report"].get("normalized_registry", {}).get("entries", [])),
        },
    }


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate NoemaForge cross-platform prep core policy")
    ap.add_argument("--policy", default=str(PACKAGE_ROOT / "configs" / "cross-platform-prep-core-policy.json"))
    ap.add_argument("--project-root", default=str(PROJECT_ROOT))
    ap.add_argument("--package-root", default=str(PACKAGE_ROOT))
    ap.add_argument("--registry", default="")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args(argv)
    project_root = Path(args.project_root).resolve()
    package_root = Path(args.package_root).resolve()
    registry_path = Path(args.registry).resolve() if args.registry else package_root / "configs" / "unified-registry.json"
    report = validate_cross_platform_prep_policy(
        load_policy(args.policy),
        project_root=project_root,
        package_root=package_root,
        registry_path=registry_path,
    )
    if args.summary:
        print(json.dumps({"ok": report["ok"], "failures": report["failures"], "metrics": report["metrics"]}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
