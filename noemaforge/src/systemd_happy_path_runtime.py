#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/systemd_happy_path_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate that happy-path systemd setup is owned by NoemaForge CLI wrappers, not manual unit editing.
Inputs: systemd-happy-path policy, boot-mode helper, CLI help surface, public docs and examples.
Outputs: JSON-compatible SystemdHappyPathValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_systemd_happy_path_runtime.py
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

import unified_registry_runtime as urr


API_VERSION = "noemaforge.systemd-happy-path/v1"
POLICY_KIND = "SystemdHappyPathPolicy"
SET_KIND = "SystemdHappyPathExampleSet"
REPORT_KIND = "SystemdHappyPathValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_CONTROLS = {
    "no_manual_systemd_unit_editing",
    "boot_mode_cli_wrapper",
    "install_units_wrapper",
    "dry_run_before_apply",
    "daemon_reload_owned_by_wrapper",
    "operator_docs_boundary",
    "no_live_host_required",
}
REQUIRED_OUTPUTS = {
    "operator_cli_boot_mode",
    "install_units_wrapper",
    "dry_run_available",
    "daemon_reload_owned_by_wrapper",
    "no_manual_unit_editor_happy_path",
}
REQUIRED_REGISTRY_REFS = [
    "configs/systemd-happy-path-policy.json",
    "contracts/systemd_happy_path.schema.json",
    "src/systemd_happy_path_runtime.py",
    "tools/prep/noemaforge-boot-mode.sh",
    "bin/noemaforge",
    "tests/test_systemd_happy_path_runtime.py",
    "tests/test_systemd_happy_path_qa.py",
    "tests/test_systemd_happy_path_performance.py",
]
REQUIRED_PIPELINE_REFS = [
    "configs/systemd-happy-path-policy.json",
    "contracts/systemd_happy_path.schema.json",
    "src/systemd_happy_path_runtime.py",
    "prelaunch/governance/systemd_happy_path.example.json",
]
_REGISTRY_VALIDATION_CACHE: Dict[tuple[str, int, int, str, str], Dict[str, Any]] = {}


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
    candidates = [("project", project_root / ref), ("package", package_root / ref)]
    if not ref.startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / ref))
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


def _cached_registry_validation(*, registry_path: Path, project_root: Path, package_root: Path) -> Dict[str, Any]:
    stat = registry_path.stat()
    key = (
        str(registry_path.resolve()),
        stat.st_mtime_ns,
        stat.st_size,
        str(project_root.resolve()),
        str(package_root.resolve()),
    )
    cached = _REGISTRY_VALIDATION_CACHE.get(key)
    if cached is not None:
        return cached
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    payload = {"registry": registry, "report": report}
    _REGISTRY_VALIDATION_CACHE.clear()
    _REGISTRY_VALIDATION_CACHE[key] = payload
    return payload


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
    if str(policy.get("activation_state") or "") != "operator_cli_owned_systemd_happy_path":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
    outputs = set(_as_string_list(policy.get("required_outputs")))
    for output in REQUIRED_OUTPUTS:
        if output not in outputs:
            failures.append(f"policy_required_output_missing:{output}")
    static_tokens = policy.get("required_static_tokens") if isinstance(policy.get("required_static_tokens"), dict) else {}
    for key in ["cli", "boot_mode_script"]:
        if not _as_string_list(static_tokens.get(key)):
            failures.append(f"policy_static_tokens_missing:{key}")
    for key in ["blocked_happy_path_tokens", "required_boundary_refs", "scan_refs", "required_example_sets"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def _registry_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    registry_payload = _cached_registry_validation(registry_path=registry_path, project_root=project_root, package_root=package_root)
    registry = registry_payload["registry"]
    report = registry_payload["report"]
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


def _static_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    refs = {
        "cli": "bin/noemaforge",
        "boot_mode_script": "tools/prep/noemaforge-boot-mode.sh",
    }
    resolved = {key: _resolve_ref(ref, project_root=project_root, package_root=package_root) for key, ref in refs.items()}
    failures: List[str] = []
    for key, item in resolved.items():
        if not item.get("ok"):
            failures.append(f"static_ref_unresolved:{key}:{refs[key]}")
    static_tokens = policy.get("required_static_tokens") if isinstance(policy.get("required_static_tokens"), dict) else {}
    for key, tokens in static_tokens.items():
        text = Path(resolved[key]["path"]).read_text(encoding="utf-8") if resolved.get(key, {}).get("ok") else ""
        for token in _as_string_list(tokens):
            if token not in text:
                failures.append(f"static_token_missing:{key}:{token}")
    boot_text = Path(resolved["boot_mode_script"]["path"]).read_text(encoding="utf-8") if resolved.get("boot_mode_script", {}).get("ok") else ""
    if "install-units)" not in boot_text:
        failures.append("boot_mode_install_units_action_missing")
    if "apply_systemd()" not in boot_text:
        failures.append("boot_mode_apply_systemd_function_missing")
    return {"failures": failures, "resolved_required_refs": resolved}


def _docs_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    phrase = str(policy.get("boundary_phrase") or "")
    blocked_tokens = _as_string_list(policy.get("blocked_happy_path_tokens"))
    failures: List[str] = []
    boundary_reports: List[Dict[str, Any]] = []
    scan_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_boundary_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        item_failures: List[str] = []
        text = Path(resolved["path"]).read_text(encoding="utf-8") if resolved.get("ok") else ""
        if not resolved.get("ok"):
            item_failures.append("missing_boundary_ref")
        if text and not _contains(text, phrase):
            item_failures.append("boundary_phrase_missing")
        if item_failures:
            failures.extend([f"doc_boundary:{ref}:{failure}" for failure in item_failures])
        boundary_reports.append({"ref": ref, "ok": not item_failures, "failures": item_failures})
    for ref in _as_string_list(policy.get("scan_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        item_failures: List[str] = []
        text = Path(resolved["path"]).read_text(encoding="utf-8") if resolved.get("ok") else ""
        if not resolved.get("ok"):
            item_failures.append("missing_scan_ref")
        for token in blocked_tokens:
            if text and _contains(text, token):
                item_failures.append(f"blocked_happy_path_token:{token}")
        if item_failures:
            failures.extend([f"doc_scan:{ref}:{failure}" for failure in item_failures])
        scan_reports.append({"ref": ref, "ok": not item_failures, "failures": item_failures})
    return {"failures": failures, "boundary_reports": boundary_reports, "scan_reports": scan_reports}


def _example_failures(example: Dict[str, Any], *, blocked_tokens: Sequence[str]) -> Dict[str, Any]:
    failures: List[str] = []
    scenario_reports: List[Dict[str, Any]] = []
    passing_scenarios = 0
    if example.get("apiVersion") != API_VERSION:
        failures.append("examples_api_version_invalid")
    if example.get("kind") != SET_KIND:
        failures.append("examples_kind_invalid")
    scenarios = example.get("scenarios") if isinstance(example.get("scenarios"), list) else []
    if not scenarios:
        failures.append("examples_scenarios_empty")
    for scenario in scenarios:
        sid = str(scenario.get("id") or "")
        local_failures: List[str] = []
        if not SAFE_ID_RE.match(sid):
            local_failures.append("scenario_id_invalid")
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local_failures.append("scenario_trace_id_missing")
        commands = "\n".join(_as_string_list(scenario.get("happy_path_commands")))
        for required in ["noemaforge boot-mode set", "--apply-systemd", "install-units --dry-run"]:
            if required not in commands:
                local_failures.append(f"scenario_happy_path_command_missing:{required}")
        for manual in _as_string_list(scenario.get("rejected_manual_steps")):
            if not any(_contains(manual, token) for token in blocked_tokens):
                local_failures.append(f"scenario_manual_step_not_blocked:{manual}")
        outputs = set(_as_string_list(scenario.get("expected_outputs")))
        for output in REQUIRED_OUTPUTS:
            if output not in outputs:
                local_failures.append(f"scenario_expected_output_missing:{output}")
        scenario_reports.append({"id": sid, "ok": not local_failures, "failures": local_failures})
        if local_failures:
            failures.extend([f"scenario:{sid}:{item}" for item in local_failures])
        else:
            passing_scenarios += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "passing_scenarios": passing_scenarios}


def validate_systemd_happy_path_policy(
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
    registry_report = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_report["failures"])
    static_report = _static_failures(payload, project_root=project, package_root=package)
    failures.extend(static_report["failures"])
    docs_report = _docs_failures(payload, project_root=project, package_root=package)
    failures.extend(docs_report["failures"])
    example_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project, package_root=package)
        if not resolved.get("ok"):
            failures.append(f"example_ref_missing:{ref}")
            continue
        example_report = _example_failures(load_example_set(resolved["path"]), blocked_tokens=_as_string_list(policy.get("blocked_happy_path_tokens")))
        failures.extend(example_report["failures"])
        example_reports.append({"ref": ref, **example_report})
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "boundary_refs": len(docs_report["boundary_reports"]),
        "scan_refs": len(docs_report["scan_reports"]),
        "blocked_tokens": len(_as_string_list(policy.get("blocked_happy_path_tokens"))),
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
        "registry": registry_report,
        "static": static_report,
        "docs": docs_report,
        "examples": example_reports,
    }


def systemd_happy_path_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    status = "pass" if report.get("ok") else "fail"
    return {
        "artifact_uri": artifact_uri,
        "run_at": report.get("validated_at") or _nowz(),
        "checks": [
            {"id": "pipeline_eval", "status": status, "score": 1.0 if status == "pass" else 0.0, "threshold": 1.0},
            {"id": "rollback_plan", "status": "pass", "score": 1.0, "threshold": 1.0},
        ],
        "details": {"id": report.get("id"), "version": report.get("version"), "metrics": report.get("metrics", {}), "failures": report.get("failures", [])},
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "SystemdHappyPathValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge systemd happy-path contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "systemd-happy-path-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_systemd_happy_path_policy(
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
