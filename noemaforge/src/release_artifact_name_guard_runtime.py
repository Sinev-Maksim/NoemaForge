#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/release_artifact_name_guard_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate canonical release-history naming and block parallel release-note or raw-report artifacts.
Inputs: release artifact name guard policy plus local project/package roots.
Outputs: JSON-compatible release artifact name guard reports.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_release_artifact_name_guard_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Sequence, Set


API_VERSION = "noemaforge.release-artifact-name-guard/v1"
POLICY_KIND = "ReleaseArtifactNameGuardPolicy"
REPORT_KIND = "ReleaseArtifactNameGuardReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/\\* -]{1,220}$")
DEFAULT_EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "trash",
}


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _normalize_ref(value: str) -> str:
    return str(value or "").strip().replace("\\", "/")


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [_normalize_ref(str(item)) for item in value if _normalize_ref(str(item))]


def _is_safe_relative_ref(ref: str) -> bool:
    text = _normalize_ref(ref)
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    candidates = [
        ("project", project_root / ref),
        ("package", package_root / ref),
    ]
    if not _normalize_ref(ref).startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / ref))

    checked: List[str] = []
    for base_name, path in candidates:
        checked.append(_display_path(path))
        if path.exists():
            return {"ok": True, "ref": ref, "resolved_under": base_name, "path": _display_path(path), "checked": checked}
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
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return load_json(policy_path)


def _active_files(base: Path, excluded_names: Iterable[str]) -> List[Path]:
    excluded = set(excluded_names) or set(DEFAULT_EXCLUDED_DIR_NAMES)
    files: List[Path] = []
    for root, dirs, names in os.walk(base):
        dirs[:] = [item for item in dirs if item not in excluded]
        root_path = Path(root)
        for name in names:
            files.append(root_path / name)
    return sorted(files, key=lambda item: _display_path(item))


def _filename_matches_any(name: str, patterns: Iterable[str]) -> str:
    lowered_name = name.lower()
    for pattern in patterns:
        lowered_pattern = _normalize_ref(pattern).lower()
        if fnmatch.fnmatchcase(lowered_name, lowered_pattern):
            return pattern
    return ""


def _scan_forbidden_file_names(
    *,
    project_root: Path,
    excluded_names: Iterable[str],
    forbidden_patterns: Iterable[str],
    allowed_refs: Iterable[str],
) -> Dict[str, Any]:
    allowed = {_normalize_ref(ref) for ref in allowed_refs}
    files = _active_files(project_root, excluded_names)
    hits: List[Dict[str, str]] = []
    for path in files:
        rel = _normalize_ref(str(path.resolve().relative_to(project_root.resolve())))
        if rel in allowed:
            continue
        matched = _filename_matches_any(path.name, forbidden_patterns)
        if matched:
            hits.append({"path": rel, "pattern": matched, "name": path.name})
    return {"files": files, "hits": hits}


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
    if str(policy.get("activation_state") or "") != "canonical_release_history_only":
        failures.append("policy_activation_state_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_host_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in [
        "canonical_changelog_ref",
        "forbidden_filename_patterns",
        "excluded_dir_names",
        "required_runtime_scripts",
        "required_runtime_tokens",
        "required_docs",
        "required_doc_tokens",
    ]:
        value = policy.get(key)
        if key == "canonical_changelog_ref":
            if not _is_safe_relative_ref(str(value or "")):
                failures.append(f"policy_unsafe_{key}:{value}")
        elif not _as_string_list(value):
            failures.append(f"policy_{key}_empty")
    for key in ["allowed_exact_refs", "required_runtime_scripts", "required_docs"]:
        for ref in _as_string_list(policy.get(key)):
            if not _is_safe_relative_ref(ref):
                failures.append(f"policy_unsafe_{key}:{ref}")
    for key in ["forbidden_filename_patterns", "excluded_dir_names", "required_runtime_tokens", "required_doc_tokens"]:
        for value in _as_string_list(policy.get(key)):
            if not SAFE_ID_RE.match(value):
                failures.append(f"policy_unsafe_{key}:{value}")
    return failures


def _runtime_script_reports(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    tokens = _as_string_list(policy.get("required_runtime_tokens"))
    for ref in _as_string_list(policy.get("required_runtime_scripts")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        text = Path(resolved["path"]).read_text(encoding="utf-8", errors="replace") if resolved.get("ok") else ""
        missing = [token for token in tokens if token not in text]
        if not resolved.get("ok"):
            failures.append(f"runtime_script_missing:{ref}")
        for token in missing:
            failures.append(f"runtime_script_token_missing:{ref}:{token}")
        reports.append({"ref": ref, "ok": bool(resolved.get("ok")) and not missing, "missing_tokens": missing})
    return {"failures": failures, "reports": reports}


def _required_doc_reports(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    docs = _as_string_list(policy.get("required_docs"))
    tokens = _as_string_list(policy.get("required_doc_tokens"))
    combined_docs_text = ""
    for ref in docs:
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        text = Path(resolved["path"]).read_text(encoding="utf-8", errors="replace") if resolved.get("ok") else ""
        combined_docs_text += "\n" + text
        if not resolved.get("ok"):
            failures.append(f"required_doc_missing:{ref}")
        reports.append({"ref": ref, "ok": bool(resolved.get("ok"))})
    missing_tokens = [token for token in tokens if token not in combined_docs_text]
    for token in missing_tokens:
        failures.append(f"required_doc_token_missing:{token}")
    return {"failures": failures, "reports": reports, "missing_tokens": missing_tokens}


def validate_release_artifact_name_guard_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
) -> Dict[str, Any]:
    project_root = Path(project_root).resolve()
    package_root = Path(package_root).resolve()
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))

    refs_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project_root, package_root=package_root, owner="policy_refs")
    failures.extend(refs_report["failures"])

    changelog_ref = _normalize_ref(str(policy.get("canonical_changelog_ref") or ""))
    changelog_report = _resolve_refs([changelog_ref] if changelog_ref else [], project_root=project_root, package_root=package_root, owner="canonical_changelog")
    failures.extend(changelog_report["failures"])

    runtime_report = _runtime_script_reports(policy, project_root=project_root, package_root=package_root)
    failures.extend(runtime_report["failures"])

    docs_report = _required_doc_reports(policy, project_root=project_root, package_root=package_root)
    failures.extend(docs_report["failures"])

    scan = _scan_forbidden_file_names(
        project_root=project_root,
        excluded_names=_as_string_list(policy.get("excluded_dir_names")) or DEFAULT_EXCLUDED_DIR_NAMES,
        forbidden_patterns=_as_string_list(policy.get("forbidden_filename_patterns")),
        allowed_refs=_as_string_list(policy.get("allowed_exact_refs")),
    )
    for hit in scan["hits"]:
        failures.append(f"forbidden_release_artifact_file:{hit['pattern']}:{hit['path']}")

    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "generated_at": _nowz(),
        "id": payload.get("id"),
        "version": payload.get("version"),
        "ok": not failures,
        "failures": failures,
        "metrics": {
            "active_files": len(scan["files"]),
            "forbidden_filename_hits": len(scan["hits"]),
            "forbidden_patterns": len(_as_string_list(policy.get("forbidden_filename_patterns"))),
            "resolved_policy_refs": len(refs_report["resolved_refs"]),
            "resolved_docs": sum(1 for item in docs_report["reports"] if item.get("ok")),
        },
        "canonical_changelog_ref": changelog_ref,
        "forbidden_filename_hits": scan["hits"],
        "refs": refs_report,
        "canonical_changelog": changelog_report,
        "runtime_scripts": runtime_report["reports"],
        "required_docs": docs_report["reports"],
        "missing_doc_tokens": docs_report["missing_tokens"],
    }


def release_artifact_name_guard_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str) -> Dict[str, Any]:
    return {
        "apiVersion": "noemaforge.release-evidence/v1",
        "kind": "ReleaseEvidence",
        "artifact_uri": artifact_uri,
        "gate": "release_artifact_name_guard",
        "status": "passed" if report.get("ok") else "failed",
        "checks": [
            {"id": "canonical_release_history_exists", "status": "passed" if not report.get("canonical_changelog", {}).get("failures") else "failed"},
            {"id": "parallel_release_artifact_names_absent", "status": "passed" if report.get("metrics", {}).get("forbidden_filename_hits") == 0 else "failed"},
            {"id": "docs_and_registry_refs_resolve", "status": "passed" if not report.get("refs", {}).get("failures") else "failed"},
        ],
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def _default_policy_path() -> Path:
    return Path(__file__).resolve().parents[1] / "configs" / "release-artifact-name-guard-policy.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge release artifact naming policy.")
    parser.add_argument("--policy", default=str(_default_policy_path()))
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--package-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    policy = load_policy(args.policy)
    report = validate_release_artifact_name_guard_policy(
        policy,
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
    )
    if args.summary:
        summary = {
            "ok": report["ok"],
            "failures": report["failures"],
            "metrics": report["metrics"],
            "forbidden_filename_hits": report["forbidden_filename_hits"][:10],
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
