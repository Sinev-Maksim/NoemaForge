#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/backlog_status_legend_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Keep backlog status legends from masquerading as open Markdown task items.
Inputs: Backlog status legend policy and canonical backlog documentation.
Outputs: JSON-compatible validation reports.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_backlog_status_legend_runtime.py
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


API_VERSION = "noemaforge.backlog-status-legend/v1"
POLICY_KIND = "BacklogStatusLegendPolicy"
REPORT_KIND = "BacklogStatusLegendValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
LEGEND_HEADING_RE = re.compile(r"^\s*Status legend:\s*$", re.IGNORECASE)


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _normalize_line(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


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


def load_json(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return load_json(policy_path)


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
    if str(policy.get("activation_state") or "") != "status_legend_not_task_list":
        failures.append("policy_activation_state_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_host_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in [
        "legend_docs",
        "forbidden_legend_markers",
        "required_legend_markers",
        "required_runtime_scripts",
        "required_runtime_tokens",
        "required_docs",
    ]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    try:
        if int(policy.get("legend_window_lines") or 0) <= 0:
            failures.append("policy_legend_window_lines_invalid")
    except Exception:
        failures.append("policy_legend_window_lines_invalid")
    return failures


def _runtime_script_reports(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    tokens = _as_string_list(policy.get("required_runtime_tokens"))
    for ref in _as_string_list(policy.get("required_runtime_scripts")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        text = Path(resolved["path"]).read_text(encoding="utf-8", errors="replace") if resolved.get("ok") else ""
        local_failures: List[str] = []
        if not resolved.get("ok"):
            local_failures.append(f"runtime_script_missing:{ref}")
        for token in tokens:
            if text and token not in text:
                local_failures.append(f"runtime_token_missing:{ref}:{token}")
        failures.extend(local_failures)
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved})
    return {"failures": failures, "reports": reports}


def find_status_legend_violations(
    markdown_text: str,
    *,
    source: str = "",
    forbidden_markers: Sequence[str] | None = None,
    window_lines: int = 8,
) -> List[Dict[str, Any]]:
    forbidden = {_normalize_line(item) for item in (forbidden_markers or []) if _normalize_line(item)}
    if not forbidden:
        forbidden = {"- [ ] planned"}
    lines = str(markdown_text or "").splitlines()
    violations: List[Dict[str, Any]] = []
    for index, line in enumerate(lines):
        if not LEGEND_HEADING_RE.match(line):
            continue
        for offset, candidate in enumerate(lines[index + 1:index + 1 + max(1, int(window_lines))], start=1):
            normalized = _normalize_line(candidate)
            if normalized in forbidden:
                violations.append({
                    "source": source,
                    "line": index + offset + 1,
                    "marker": normalized,
                    "activation_state": "status_legend_not_task_list",
                })
    return violations


def _doc_reports(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    forbidden = _as_string_list(policy.get("forbidden_legend_markers"))
    required = _as_string_list(policy.get("required_legend_markers"))
    window_lines = int(policy.get("legend_window_lines") or 8)
    for ref in _as_string_list(policy.get("legend_docs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        text = Path(resolved["path"]).read_text(encoding="utf-8", errors="replace") if resolved.get("ok") else ""
        local_failures: List[str] = []
        violations = find_status_legend_violations(text, source=ref, forbidden_markers=forbidden, window_lines=window_lines)
        if not resolved.get("ok"):
            local_failures.append(f"legend_doc_missing:{ref}")
        for violation in violations:
            local_failures.append(f"forbidden_status_legend_marker:{ref}:{violation['line']}:{violation['marker']}")
        for marker in required:
            if marker not in text:
                local_failures.append(f"required_status_legend_marker_missing:{ref}:{marker}")
        failures.extend(local_failures)
        reports.append({
            "ref": ref,
            "ok": not local_failures,
            "failures": local_failures,
            "violations": violations,
            "resolved": resolved,
        })
    return {"failures": failures, "reports": reports}


def validate_backlog_status_legend_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path,
    package_root: Path,
) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    failures = _policy_failures(payload)
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project_root, package_root=package_root, owner="policy.refs")
    doc_ref_report = _resolve_refs(_as_string_list(policy.get("required_docs")), project_root=project_root, package_root=package_root, owner="policy.required_docs")
    runtime_report = _runtime_script_reports(policy, project_root=project_root, package_root=package_root)
    doc_report = _doc_reports(policy, project_root=project_root, package_root=package_root)
    failures.extend(ref_report["failures"])
    failures.extend(doc_ref_report["failures"])
    failures.extend(runtime_report["failures"])
    failures.extend(doc_report["failures"])
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "id": payload.get("id"),
        "version": payload.get("version"),
        "metrics": {
            "refs": len(_as_string_list(payload.get("refs"))),
            "resolved_refs": len(ref_report["resolved_refs"]),
            "required_docs": len(_as_string_list(policy.get("required_docs"))),
            "legend_docs": len(_as_string_list(policy.get("legend_docs"))),
            "forbidden_markers": len(_as_string_list(policy.get("forbidden_legend_markers"))),
            "required_markers": len(_as_string_list(policy.get("required_legend_markers"))),
        },
        "failures": failures,
        "refs": ref_report,
        "docs": doc_ref_report,
        "legend_docs": doc_report["reports"],
        "runtime_scripts": runtime_report["reports"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate backlog status legends are not Markdown task lists.")
    parser.add_argument("--policy", default="noemaforge/configs/backlog-status-legend-policy.json")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--package-root", default="noemaforge")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    package_root = (project_root / args.package_root).resolve() if not Path(args.package_root).is_absolute() else Path(args.package_root).resolve()
    policy_path = Path(args.policy)
    policy = load_policy(policy_path if policy_path.is_absolute() else project_root / policy_path)
    report = validate_backlog_status_legend_policy(policy, project_root=project_root, package_root=package_root)
    if args.summary:
        report = {
            "apiVersion": API_VERSION,
            "kind": REPORT_KIND,
            "ok": report["ok"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
