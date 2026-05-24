#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/admin_smalltalk_route_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Admin smalltalk conversation routing and no-pipeline regression behavior.
Inputs: admin-smalltalk-route policy, Admin CLI runtime and Admin GUI server source.
Outputs: JSON-compatible AdminSmalltalkRouteValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_admin_smalltalk_route_runtime.py
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
API_VERSION = "noemaforge.admin-smalltalk-route/v1"
POLICY_KIND = "AdminSmalltalkRoutePolicy"
REPORT_KIND = "AdminSmalltalkRouteValidationReport"
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


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


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
    if str(policy.get("activation_state") or "") != "admin_smalltalk_conversation_no_pipeline_regression":
        failures.append("policy_activation_state_invalid")
    for key in ["require_docs_and_changelog_refs", "require_no_live_gui_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in [
        "required_runtime_scripts",
        "required_admin_runtime_tokens",
        "required_gui_tokens",
        "forbidden_smalltalk_tokens",
        "smalltalk_examples",
        "explicit_control_examples",
    ]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def _slice_between(text: str, start_marker: str, end_markers: Sequence[str]) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    ends = [text.find(marker, start + len(start_marker)) for marker in end_markers]
    ends = [pos for pos in ends if pos > start]
    end = min(ends) if ends else len(text)
    return text[start:end]


def _script_reports(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_runtime_scripts")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        text = load_text(resolved["path"]) if resolved.get("ok") else ""
        local_failures: List[str] = []
        if not resolved.get("ok"):
            local_failures.append(f"script_missing:{ref}")
        if ref.endswith("admin_runtime.py"):
            for token in _as_string_list(policy.get("required_admin_runtime_tokens")):
                if text and token not in text:
                    local_failures.append(f"admin_runtime_token_missing:{token}")
            block = _slice_between(
                text,
                'if rid in {"general", "greeting"} and is_conversational_smalltalk(message):',
                ['if rid == "code"', 'if rid == "model_selection"'],
            )
            if not block:
                local_failures.append("admin_runtime_smalltalk_block_missing")
            for token in _as_string_list(policy.get("forbidden_smalltalk_tokens")):
                if block and token in block:
                    local_failures.append(f"admin_runtime_smalltalk_forbidden_token:{token}")
            if block and "create_pipeline_run" in block:
                local_failures.append("admin_runtime_smalltalk_can_create_pipeline_run")
            if block and 'result["route"] = {"id": "conversation"' not in block:
                local_failures.append("admin_runtime_smalltalk_route_not_rewritten")
        elif ref.endswith("admin_gui_server.py"):
            for token in _as_string_list(policy.get("required_gui_tokens")):
                if text and token not in text:
                    local_failures.append(f"admin_gui_token_missing:{token}")
            conv_block = _slice_between(text, "def _conversational", ["def try_llm_admin_reply"])
            admin_message_block = _slice_between(text, "def admin_message", ["def _handle_task_intent"])
            if conv_block and "self._explicit_control_request(low)" not in conv_block:
                local_failures.append("admin_gui_conversation_lacks_explicit_control_guard")
            if admin_message_block and admin_message_block.find("if self._explicit_control_request(low):") > admin_message_block.find("if self._conversational(low):"):
                local_failures.append("admin_gui_conversation_checked_before_explicit_control")
            if admin_message_block and "_run_explicit_pipeline_from_chat" in admin_message_block:
                explicit_pos = admin_message_block.find("_run_explicit_pipeline_from_chat")
                conv_pos = admin_message_block.find('mode": "conversation"')
                if conv_pos >= 0 and explicit_pos > conv_pos:
                    local_failures.append("admin_gui_pipeline_run_after_conversation")
        failures.extend(local_failures)
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved})
    return {"failures": failures, "reports": reports}


def build_admin_smalltalk_decision(message: str) -> Dict[str, Any]:
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    import admin_runtime  # type: ignore

    route = admin_runtime.route_request(message)
    route_id = str(route.get("id") or "")
    smalltalk = bool(admin_runtime.is_conversational_smalltalk(message))
    conversation = route_id in {"general", "greeting"} and smalltalk
    pipeline_id = "" if conversation else str(route.get("pipeline_id") or "")
    return {
        "message": message,
        "route_id": "conversation" if conversation else route_id,
        "original_route_id": route_id,
        "mode": "conversation" if conversation else "control",
        "execute_mode": "conversation" if conversation else str(route.get("execute_mode") or ""),
        "pipeline_id": pipeline_id,
        "launches_pipeline": False if conversation else bool(pipeline_id),
        "explicit_control": bool(admin_runtime.has_explicit_control_request(message)),
        "conversational_smalltalk": smalltalk,
    }


def _example_reports(policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    smalltalk_reports = [build_admin_smalltalk_decision(item) for item in _as_string_list(policy.get("smalltalk_examples"))]
    explicit_reports = [build_admin_smalltalk_decision(item) for item in _as_string_list(policy.get("explicit_control_examples"))]
    for item in smalltalk_reports:
        if item["mode"] != "conversation":
            failures.append(f"smalltalk_not_conversation:{item['message']}")
        if item["pipeline_id"] or item["launches_pipeline"]:
            failures.append(f"smalltalk_launches_pipeline:{item['message']}")
        if item["original_route_id"] == "general" and item["pipeline_id"] == "public_mwp":
            failures.append(f"smalltalk_retains_public_mwp:{item['message']}")
    for item in explicit_reports:
        if item["mode"] == "conversation":
            failures.append(f"explicit_control_misrouted_to_conversation:{item['message']}")
        if not item["explicit_control"]:
            failures.append(f"explicit_control_not_detected:{item['message']}")
    return {"failures": failures, "smalltalk": smalltalk_reports, "explicit_control": explicit_reports}


def validate_admin_smalltalk_route_policy(
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
    failures.extend(ref_report["failures"])
    scripts = _script_reports(policy, project_root=project, package_root=package)
    failures.extend(scripts["failures"])
    examples = _example_reports(policy)
    failures.extend(examples["failures"])
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "script_reports": len(scripts["reports"]),
        "valid_script_reports": sum(1 for item in scripts["reports"] if item.get("ok")),
        "smalltalk_examples": len(examples["smalltalk"]),
        "explicit_control_examples": len(examples["explicit_control"]),
        "conversation_examples": sum(1 for item in examples["smalltalk"] if item.get("mode") == "conversation"),
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
        "scripts": scripts,
        "examples": examples,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "AdminSmalltalkRouteValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Admin smalltalk route regression contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "admin-smalltalk-route-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_admin_smalltalk_route_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
