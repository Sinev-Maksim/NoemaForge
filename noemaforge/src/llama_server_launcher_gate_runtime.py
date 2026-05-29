#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/llama_server_launcher_gate_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate launcher-side llama-server binary and shared-library gates.
Inputs: llama-server-launcher-gate policy and prep scripts.
Outputs: JSON-compatible LlamaServerLauncherGateValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_llama_server_launcher_gate_runtime.py
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


SRC_DIR = Path(__file__).resolve().parent
API_VERSION = "noemaforge.llama-server-launcher-gate/v1"
POLICY_KIND = "LlamaServerLauncherGatePolicy"
REPORT_KIND = "LlamaServerLauncherGateValidationReport"
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


def classify_ldd_output(text: str, rc: int = 0) -> Dict[str, Any]:
    output = str(text or "")
    missing = [line.strip() for line in output.splitlines() if "not found" in line]
    static_like = bool(re.search(r"not a dynamic executable|statically linked", output, re.IGNORECASE))
    ok = not missing and (rc == 0 or static_like)
    if missing:
        status = "unresolved_libraries"
    elif static_like:
        status = "static_or_non_dynamic"
    elif rc == 0:
        status = "dynamic_libraries_resolved"
    else:
        status = "inspection_failed"
    return {"ok": ok, "status": status, "missing": missing, "rc": rc}


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
    if str(policy.get("activation_state") or "") != "llama_server_binary_shared_library_launcher_gate":
        failures.append("policy_activation_state_invalid")
    for key in ["require_docs_and_changelog_refs", "require_no_live_host_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["required_scripts", "required_gate_tokens", "required_preflight_checks", "required_failure_modes"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    if not str(policy.get("required_gate_function") or "").strip():
        failures.append("policy_required_gate_function_empty")
    return failures


def _script_reports(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    gate_function = str(policy.get("required_gate_function") or "")
    for ref in _as_string_list(policy.get("required_scripts")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        text = load_text(resolved["path"]) if resolved.get("ok") else ""
        local_failures: List[str] = []
        if not resolved.get("ok"):
            local_failures.append(f"script_missing:{ref}")
        if ref.endswith("noemaforge-trixie-preflight.sh"):
            for token in ["llama_start", "llama_server", "llama_libs", "ldd \"$LLAMA_BIN\"", "not found"]:
                if text and token not in text:
                    local_failures.append(f"preflight_check_missing:{token}")
        else:
            if text and f"{gate_function}()" not in text:
                local_failures.append(f"launcher_gate_function_missing:{ref}:{gate_function}")
            for token in _as_string_list(policy.get("required_gate_tokens")):
                if text and token not in text:
                    local_failures.append(f"launcher_gate_token_missing:{ref}:{token}")
            if text and text.find(gate_function) > text.find("safe_model_discovery()"):
                local_failures.append(f"launcher_gate_after_model_discovery:{ref}")
        failures.extend(local_failures)
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved})
    return {"failures": failures, "reports": reports}


def validate_llama_server_launcher_gate_policy(
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
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "script_reports": len(scripts["reports"]),
        "valid_script_reports": sum(1 for item in scripts["reports"] if item.get("ok")),
        "gate_tokens": len(_as_string_list(policy.get("required_gate_tokens"))),
        "preflight_checks": len(_as_string_list(policy.get("required_preflight_checks"))),
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
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "LlamaServerLauncherGateValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge llama-server launcher gate contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "llama-server-launcher-gate-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_llama_server_launcher_gate_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
