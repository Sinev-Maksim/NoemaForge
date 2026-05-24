#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/public_showcase_guided_scenario_runtime.py
Zone: gui/control-plane
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the local-first Admin GUI public showcase guided scenario.
Inputs: Public showcase policy, example scenario, Admin GUI server source and dashboard assets.
Outputs: JSON-compatible PublicShowcaseGuidedScenarioValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_public_showcase_guided_scenario_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


API_VERSION = "noemaforge.public-showcase-guided-scenario/v1"
POLICY_KIND = "PublicShowcaseGuidedScenarioPolicy"
REPORT_KIND = "PublicShowcaseGuidedScenarioValidationReport"
POLICY_ID = "public-showcase-guided-scenario-core"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")


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


def _token_report(ref: str, tokens: Sequence[str], *, project_root: Path, package_root: Path, owner: str) -> Dict[str, Any]:
    resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
    text = Path(resolved["path"]).read_text(encoding="utf-8", errors="replace") if resolved.get("ok") else ""
    failures: List[str] = []
    if not resolved.get("ok"):
        failures.append(f"{owner}_missing:{ref}")
    for token in tokens:
        if text and token not in text:
            failures.append(f"{owner}_token_missing:{ref}:{token}")
    return {"ref": ref, "ok": not failures, "failures": failures, "resolved": resolved}


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if str(payload.get("id") or "") != POLICY_ID:
        failures.append("policy_id_invalid")
    if not SAFE_ID_RE.match(str(payload.get("id") or "")):
        failures.append("policy_id_unsafe")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if str(policy.get("selected_showcase") or "") != "polished_admin_gui_guided_scenario":
        failures.append("policy_selected_showcase_invalid")
    if str(policy.get("scenario_id") or "") != "admin_gui_guided_scenario":
        failures.append("policy_scenario_id_invalid")
    if str(policy.get("scenario_endpoint") or "") != "/api/public-showcase/scenario":
        failures.append("policy_scenario_endpoint_invalid")
    for key in ["live_backend_demo_enabled", "requires_live_target", "requires_packaging"]:
        if policy.get(key) is not False:
            failures.append(f"policy_{key}_not_false")
    for key in ["no_hidden_backend_start", "no_auto_apply", "final_target_replay_required"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in [
        "required_step_ids",
        "required_server_tokens",
        "required_frontend_tokens",
        "required_style_tokens",
        "required_runtime_scripts",
        "required_runtime_tokens",
        "required_docs",
    ]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def _validate_example(example: Dict[str, Any], required_steps: Sequence[str]) -> Dict[str, Any]:
    failures: List[str] = []
    if example.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if str(example.get("scenario_id") or "") != "admin_gui_guided_scenario":
        failures.append("example_scenario_id_invalid")
    if str(example.get("selected_showcase") or "") != "polished_admin_gui_guided_scenario":
        failures.append("example_selected_showcase_invalid")
    for key in ["live_backend_demo_enabled", "requires_live_target", "requires_packaging"]:
        if example.get(key) is not False:
            failures.append(f"example_{key}_not_false")
    steps = example.get("steps") if isinstance(example.get("steps"), list) else []
    step_ids = {str(step.get("id") or "") for step in steps if isinstance(step, dict)}
    for step in required_steps:
        if step not in step_ids:
            failures.append(f"example_step_missing:{step}")
    for step in steps:
        if not isinstance(step, dict):
            failures.append("example_step_not_object")
            continue
        sid = str(step.get("id") or "")
        if not SAFE_ID_RE.match(sid):
            failures.append(f"example_step_id_invalid:{sid}")
        if not str(step.get("endpoint") or "").startswith("/api/"):
            failures.append(f"example_step_endpoint_invalid:{sid}")
        if not str(step.get("request") or "").strip():
            failures.append(f"example_step_request_missing:{sid}")
    outputs = set(_as_string_list(example.get("expected_outputs")))
    for output in ["public_showcase_plan", "dev_team_plan", "model_evolution_review_context"]:
        if output not in outputs:
            failures.append(f"example_expected_output_missing:{output}")
    return {"ok": not failures, "failures": failures, "steps": len(steps), "step_ids": sorted(step_ids)}


def validate_public_showcase_guided_scenario_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Path | str | None = None,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    doc_report = _resolve_refs(_as_string_list(policy.get("required_docs")), project_root=project, package_root=package, owner="policy.required_docs")
    server_report = _token_report("noemaforge/src/admin_gui_server.py", _as_string_list(policy.get("required_server_tokens")), project_root=project, package_root=package, owner="server")
    frontend_report = _token_report("noemaforge/templates/pipeline-dashboard/app.js", _as_string_list(policy.get("required_frontend_tokens")), project_root=project, package_root=package, owner="frontend")
    index_report = _token_report("noemaforge/templates/pipeline-dashboard/index.html", ["public-showcase", "Public scenario"], project_root=project, package_root=package, owner="index")
    style_report = _token_report("noemaforge/templates/pipeline-dashboard/pipeline-editor.css", _as_string_list(policy.get("required_style_tokens")), project_root=project, package_root=package, owner="style")
    runtime_reports = [
        _token_report(script, _as_string_list(policy.get("required_runtime_tokens")), project_root=project, package_root=package, owner="runtime")
        for script in _as_string_list(policy.get("required_runtime_scripts"))
    ]
    example_path = project / "prelaunch" / "governance" / "public_showcase_guided_scenario.example.json"
    example = json.loads(example_path.read_text(encoding="utf-8"))
    example_report = _validate_example(example, _as_string_list(policy.get("required_step_ids")))
    failures.extend(ref_report["failures"])
    failures.extend(doc_report["failures"])
    failures.extend(server_report["failures"])
    failures.extend(frontend_report["failures"])
    failures.extend(index_report["failures"])
    failures.extend(style_report["failures"])
    failures.extend(example_report["failures"])
    for report in runtime_reports:
        failures.extend(report["failures"])
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "required_docs": len(_as_string_list(policy.get("required_docs"))),
        "required_steps": len(_as_string_list(policy.get("required_step_ids"))),
        "example_steps": example_report["steps"],
        "runtime_reports": len(runtime_reports),
        "valid_runtime_reports": sum(1 for item in runtime_reports if item.get("ok")),
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
        "docs": doc_report,
        "server": server_report,
        "frontend": frontend_report,
        "index": index_report,
        "style": style_report,
        "runtime": runtime_reports,
        "example": example_report,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "PublicShowcaseGuidedScenarioValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge public showcase guided scenario contract.")
    parser.add_argument("--policy", default="noemaforge/configs/public-showcase-guided-scenario-policy.json")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--package-root", default="noemaforge")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    package_root = (project_root / args.package_root).resolve() if not Path(args.package_root).is_absolute() else Path(args.package_root).resolve()
    policy_path = Path(args.policy)
    policy = load_policy(policy_path if policy_path.is_absolute() else project_root / policy_path)
    report = validate_public_showcase_guided_scenario_policy(policy, project_root=project_root, package_root=package_root, policy_path=policy_path)
    print(json.dumps(build_summary(report) if args.summary else report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
