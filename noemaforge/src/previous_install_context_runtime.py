#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/previous_install_context_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate that previous install, backup and migration context is archive-only, not active runtime.
Inputs: Previous install context policy and optional runtime context JSON.
Outputs: JSON-compatible validation reports.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_previous_install_context_runtime.py
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


API_VERSION = "noemaforge.previous-install-context/v1"
POLICY_KIND = "PreviousInstallContextPolicy"
REPORT_KIND = "PreviousInstallContextValidationReport"
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


def _norm_path(path: Any) -> str:
    text = str(path or "").strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    return text.rstrip("/") if text != "/" else text


def _path_starts_with(path: str, root: str) -> bool:
    p = _norm_path(path).lower()
    r = _norm_path(root).lower()
    return bool(p and r and (p == r or p.startswith(r + "/")))


def _path_has_fragment(path: str, fragments: Sequence[str]) -> str:
    lowered = _norm_path(path).lower()
    parts = [part for part in PurePosixPath(lowered.lstrip("/")).parts if part]
    for fragment in fragments:
        needle = str(fragment or "").strip().lower()
        if not needle:
            continue
        if needle in parts or any(needle in part for part in parts):
            return needle
    return ""


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
    if str(policy.get("activation_state") or "") != "previous_install_context_is_archive_only":
        failures.append("policy_activation_state_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_host_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    roots = policy.get("canonical_runtime_roots") if isinstance(policy.get("canonical_runtime_roots"), dict) else {}
    for key in ["install_root", "state_root", "share_root"]:
        if not _norm_path(roots.get(key)):
            failures.append(f"policy_canonical_root_missing:{key}")
    for key in [
        "active_runtime_path_keys",
        "archive_only_context_keys",
        "allowed_archive_modes",
        "forbidden_active_path_fragments",
        "required_runtime_scripts",
        "required_runtime_tokens",
        "required_docs",
    ]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
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
        elif not any(token in text for token in tokens):
            local_failures.append(f"runtime_script_missing_required_token:{ref}")
        failures.extend(local_failures)
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved})
    return {"failures": failures, "reports": reports}


def validate_previous_install_context_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path,
    package_root: Path,
) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    failures = _policy_failures(payload)
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project_root, package_root=package_root, owner="policy.refs")
    doc_report = _resolve_refs(_as_string_list(policy.get("required_docs")), project_root=project_root, package_root=package_root, owner="policy.required_docs")
    runtime_report = _runtime_script_reports(policy, project_root=project_root, package_root=package_root)
    failures.extend(ref_report["failures"])
    failures.extend(doc_report["failures"])
    failures.extend(runtime_report["failures"])
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
            "runtime_scripts": len(_as_string_list(policy.get("required_runtime_scripts"))),
        },
        "failures": failures,
        "refs": ref_report,
        "docs": doc_report,
        "runtime_scripts": runtime_report["reports"],
    }


def validate_previous_install_context(context: Dict[str, Any], *, policy: Dict[str, Any] | None = None) -> Dict[str, Any]:
    body = _policy_dict(policy or {})
    failures: List[str] = []
    warnings: List[str] = []
    active = context.get("active_runtime") if isinstance(context.get("active_runtime"), dict) else context
    active_keys = _as_string_list(body.get("active_runtime_path_keys")) or ["install_root", "state_root", "share_root"]
    context_keys = _as_string_list(body.get("archive_only_context_keys")) or ["previous_install", "backup", "migration"]
    allowed_modes = set(_as_string_list(body.get("allowed_archive_modes")) or ["archive_only", "readonly_evidence"])
    forbidden_fragments = _as_string_list(body.get("forbidden_active_path_fragments")) or ["backup", "migration", "previous_install", "previous-install"]
    legacy_prefixes = _as_string_list(body.get("legacy_runtime_prefixes"))
    roots = body.get("canonical_runtime_roots") if isinstance(body.get("canonical_runtime_roots"), dict) else {}

    archive_roots: List[str] = []
    archive_entries = 0
    for key in context_keys:
        entry = context.get(key)
        if not isinstance(entry, dict):
            continue
        archive_entries += 1
        path = _norm_path(entry.get("path"))
        mode = str(entry.get("mode") or "").strip()
        if path:
            archive_roots.append(path)
        if entry.get("active") is True:
            failures.append(f"archive_context_marked_active:{key}")
        if mode not in allowed_modes:
            failures.append(f"archive_context_mode_invalid:{key}:{mode or 'missing'}")

    active_paths: Dict[str, str] = {}
    for key in active_keys:
        path = _norm_path(active.get(key))
        if not path:
            warnings.append(f"active_path_missing:{key}")
            continue
        active_paths[key] = path
        fragment = _path_has_fragment(path, forbidden_fragments)
        if fragment:
            failures.append(f"active_path_uses_archive_fragment:{key}:{fragment}")
        for prefix in legacy_prefixes:
            if _path_starts_with(path, prefix):
                failures.append(f"active_path_uses_legacy_prefix:{key}:{prefix}")
        for archive_root in archive_roots:
            if _path_starts_with(path, archive_root):
                failures.append(f"active_path_overlaps_archive_context:{key}")

    for key, expected in roots.items():
        if key not in active_paths:
            continue
        if not _path_starts_with(active_paths[key], str(expected)):
            failures.append(f"active_path_not_under_canonical_root:{key}:{expected}")

    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "metrics": {
            "active_path_count": len(active_paths),
            "archive_context_count": archive_entries,
            "archive_root_count": len(archive_roots),
        },
        "active_paths": active_paths,
        "archive_roots": archive_roots,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate previous install context boundary.")
    parser.add_argument("--policy", default="noemaforge/configs/previous-install-context-policy.json")
    parser.add_argument("--context")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--package-root", default="noemaforge")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    package_root = (project_root / args.package_root).resolve() if not Path(args.package_root).is_absolute() else Path(args.package_root).resolve()
    policy = load_policy(project_root / args.policy if not Path(args.policy).is_absolute() else args.policy)
    policy_report = validate_previous_install_context_policy(policy, project_root=project_root, package_root=package_root)
    if args.context:
        context = load_json(project_root / args.context if not Path(args.context).is_absolute() else args.context)
        context_report = validate_previous_install_context(context, policy=policy)
        report = {
            "apiVersion": API_VERSION,
            "kind": REPORT_KIND,
            "created_at": _nowz(),
            "ok": policy_report["ok"] and context_report["ok"],
            "policy": policy_report,
            "context": context_report,
        }
    else:
        report = policy_report
    if args.summary:
        report = {
            "apiVersion": API_VERSION,
            "kind": REPORT_KIND,
            "ok": report["ok"],
            "metrics": report.get("metrics") or report.get("context", {}).get("metrics") or {},
            "failures": report.get("failures") or report.get("context", {}).get("failures") or [],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
