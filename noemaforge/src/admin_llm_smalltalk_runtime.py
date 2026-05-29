#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/admin_llm_smalltalk_runtime.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the Admin GUI optional LLM smalltalk path and deterministic fallback contract.
Inputs: Admin LLM smalltalk policy, Admin GUI server source and canonical documentation.
Outputs: JSON-compatible AdminLLMSmalltalkValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_admin_llm_smalltalk_runtime.py
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


API_VERSION = "noemaforge.admin-llm-smalltalk/v1"
POLICY_KIND = "AdminLLMSmalltalkPolicy"
REPORT_KIND = "AdminLLMSmalltalkValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
CONTROL_TOKENS = (
    "run",
    "start",
    "launch",
    "pipeline",
    "public_mwp",
    "model selection",
    "evolution",
    "запусти",
    "старт",
    "pipeline",
)


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
    if str(policy.get("activation_state") or "") != "optional_llm_chat_with_deterministic_fallback":
        failures.append("policy_activation_state_invalid")
    for key in [
        "require_registry_attachment",
        "require_docs_and_changelog_refs",
        "require_no_live_llm_dependency",
        "require_control_plane_preserved",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in [
        "required_backends",
        "required_gui_tokens",
        "required_runtime_scripts",
        "required_runtime_tokens",
        "required_docs",
        "smalltalk_examples",
        "explicit_control_examples",
    ]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    backends = set(_as_string_list(policy.get("required_backends")))
    if {"llm_chat", "deterministic_fallback"} - backends:
        failures.append("policy_required_backends_incomplete")
    return failures


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


def _explicit_control_from_text(message: str) -> bool:
    low = str(message or "").lower()
    return any(token in low for token in CONTROL_TOKENS)


def build_smalltalk_backend_decision(message: str, *, llm_available: bool = False, explicit_control: bool = False) -> Dict[str, Any]:
    control = bool(explicit_control or _explicit_control_from_text(message))
    if control:
        return {
            "message": message,
            "mode": "control",
            "conversation_backend": "",
            "explicit_control": True,
            "control_plane_preserved": True,
        }
    backend = "llm_chat" if llm_available else "deterministic_fallback"
    return {
        "message": message,
        "mode": "conversation",
        "conversation_backend": backend,
        "explicit_control": False,
        "control_plane_preserved": True,
    }


def _example_reports(policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    fallback_reports = [
        build_smalltalk_backend_decision(message, llm_available=False)
        for message in _as_string_list(policy.get("smalltalk_examples"))
    ]
    llm_reports = [
        build_smalltalk_backend_decision(message, llm_available=True)
        for message in _as_string_list(policy.get("smalltalk_examples"))
    ]
    explicit_reports = [
        build_smalltalk_backend_decision(message)
        for message in _as_string_list(policy.get("explicit_control_examples"))
    ]
    for item in fallback_reports:
        if item["mode"] != "conversation" or item["conversation_backend"] != "deterministic_fallback":
            failures.append(f"fallback_smalltalk_invalid:{item['message']}")
    for item in llm_reports:
        if item["mode"] != "conversation" or item["conversation_backend"] != "llm_chat":
            failures.append(f"llm_smalltalk_invalid:{item['message']}")
    for item in explicit_reports:
        if item["mode"] != "control" or not item["explicit_control"]:
            failures.append(f"explicit_control_not_preserved:{item['message']}")
        if item["conversation_backend"]:
            failures.append(f"explicit_control_uses_chat_backend:{item['message']}")
    return {
        "failures": failures,
        "fallback": fallback_reports,
        "llm": llm_reports,
        "explicit_control": explicit_reports,
    }


def validate_admin_llm_smalltalk_policy(
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
    gui_report = _token_report("noemaforge/src/admin_gui_server.py", _as_string_list(policy.get("required_gui_tokens")), project_root=project, package_root=package, owner="admin_gui")
    runtime_reports = [
        _token_report(script, _as_string_list(policy.get("required_runtime_tokens")), project_root=project, package_root=package, owner="runtime")
        for script in _as_string_list(policy.get("required_runtime_scripts"))
    ]
    examples = _example_reports(policy)
    failures.extend(ref_report["failures"])
    failures.extend(doc_report["failures"])
    failures.extend(gui_report["failures"])
    for report in runtime_reports:
        failures.extend(report["failures"])
    failures.extend(examples["failures"])
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "required_docs": len(_as_string_list(policy.get("required_docs"))),
        "runtime_reports": len(runtime_reports),
        "valid_runtime_reports": sum(1 for item in runtime_reports if item.get("ok")),
        "smalltalk_examples": len(_as_string_list(policy.get("smalltalk_examples"))),
        "explicit_control_examples": len(_as_string_list(policy.get("explicit_control_examples"))),
        "synthetic_backends": sorted({
            item["conversation_backend"]
            for group in [examples["fallback"], examples["llm"]]
            for item in group
            if item.get("conversation_backend")
        }),
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
        "admin_gui": gui_report,
        "runtime": runtime_reports,
        "examples": examples,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "AdminLLMSmalltalkValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Admin LLM smalltalk fallback contract.")
    parser.add_argument("--policy", default="noemaforge/configs/admin-llm-smalltalk-policy.json")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--package-root", default="noemaforge")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    package_root = (project_root / args.package_root).resolve() if not Path(args.package_root).is_absolute() else Path(args.package_root).resolve()
    policy_path = Path(args.policy)
    policy = load_policy(policy_path if policy_path.is_absolute() else project_root / policy_path)
    report = validate_admin_llm_smalltalk_policy(policy, project_root=project_root, package_root=package_root, policy_path=policy_path)
    print(json.dumps(build_summary(report) if args.summary else report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
