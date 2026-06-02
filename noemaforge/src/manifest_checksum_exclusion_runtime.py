#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/manifest_checksum_exclusion_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate release manifests and checksum lists exclude trash and generated cache paths.
Inputs: manifest-checksum exclusion policy, active manifests and checksum files.
Outputs: JSON-compatible manifest checksum exclusion reports.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_manifest_checksum_exclusion_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple


API_VERSION = "noemaforge.manifest-checksum-exclusion/v1"
POLICY_KIND = "ManifestChecksumExclusionPolicy"
REPORT_KIND = "ManifestChecksumExclusionReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
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


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [_normalize_ref(str(item)) for item in value if _normalize_ref(str(item))]


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


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
    if str(policy.get("activation_state") or "") != "trash_and_cache_excluded_from_release_evidence":
        failures.append("policy_activation_state_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_host_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    required_lists = [
        "project_manifest_sha_refs",
        "project_checksum_refs",
        "package_manifest_sha_refs",
        "excluded_dir_names",
        "required_runtime_scripts",
        "required_runtime_tokens",
        "required_docs",
    ]
    for key in required_lists:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    ref_keys = [
        "project_manifest_ref",
        "package_root_ref",
        "package_manifest_ref",
        "package_checksum_ref",
    ]
    for key in ref_keys:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_unsafe_{key}:{policy.get(key)}")
    list_ref_keys = [
        "project_manifest_sha_refs",
        "project_checksum_refs",
        "package_manifest_sha_refs",
        "project_checksum_self_exclusions",
        "package_checksum_self_exclusions",
        "project_excluded_file_refs",
        "required_runtime_scripts",
        "required_docs",
    ]
    for key in list_ref_keys:
        for ref in _as_string_list(policy.get(key)):
            if not _is_safe_relative_ref(ref):
                failures.append(f"policy_unsafe_{key}:{ref}")
    return failures


def _active_files(
    base: Path,
    excluded_names: Iterable[str],
    *,
    root_only_excluded_dir_names: Iterable[str] = (),
    excluded_file_refs: Iterable[str] = (),
) -> List[Path]:
    excluded = set(excluded_names) or set(DEFAULT_EXCLUDED_DIR_NAMES)
    root_only_excluded = set(root_only_excluded_dir_names)
    excluded_files = {_normalize_ref(item) for item in excluded_file_refs}
    files: List[Path] = []
    for root, dirs, names in os.walk(base):
        root_path = Path(root)
        skip_dirs = set(excluded)
        if root_path == base:
            skip_dirs.update(root_only_excluded)
        dirs[:] = [item for item in dirs if item not in skip_dirs]
        for name in names:
            if name in excluded:
                continue
            path = root_path / name
            rel = _normalize_ref(str(path.resolve().relative_to(base.resolve())))
            if rel in excluded_files:
                continue
            files.append(path)
    return sorted(files, key=lambda item: _display_path(item))


def _relative_set(base: Path, paths: Iterable[Path]) -> Set[str]:
    return {_normalize_ref(str(path.resolve().relative_to(base.resolve()))) for path in paths}


def _has_excluded_part(rel: str, excluded_names: Iterable[str]) -> bool:
    normalized = _normalize_ref(rel)
    if normalized.startswith("./"):
        normalized = normalized[2:]
    parts = PurePosixPath(normalized).parts
    return any(part in set(excluded_names) for part in parts)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_sha256sums(path: Path) -> Tuple[List[Tuple[str, str]], List[str]]:
    failures: List[str] = []
    entries: List[Tuple[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 2:
            failures.append(f"checksum_line_invalid:{path.name}:{line_number}")
            continue
        digest = parts[0].lower()
        rel = _normalize_ref(parts[1])
        if rel.startswith("./"):
            rel = rel[2:]
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            failures.append(f"checksum_digest_invalid:{path.name}:{line_number}:{rel}")
            continue
        entries.append((digest, rel))
    return entries, failures


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


def _manifest_report(ref: str, *, root: Path, active_count: int, excluded_names: Iterable[str]) -> Dict[str, Any]:
    failures: List[str] = []
    path = root / ref
    payload: Dict[str, Any] = {}
    files: List[str] = []
    if not path.exists():
        failures.append(f"manifest_missing:{ref}")
    else:
        try:
            payload = load_json(path)
            if int(payload.get("file_count") or -1) != active_count:
                failures.append(f"manifest_file_count_mismatch:{ref}:{payload.get('file_count')}:{active_count}")
            raw_files = payload.get("files")
            if isinstance(raw_files, list):
                files = [_normalize_ref(str(item)) for item in raw_files if _normalize_ref(str(item))]
                for item in files:
                    if _has_excluded_part(item, excluded_names):
                        failures.append(f"manifest_excluded_path:{ref}:{item}")
        except Exception as exc:
            failures.append(f"manifest_parse_failed:{ref}:{exc.__class__.__name__}")
    return {"ref": ref, "ok": not failures, "file_count": payload.get("file_count"), "listed_files": len(files), "failures": failures}


def _manifest_sha_reports(refs: Sequence[str], *, manifest_path: Path, root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    expected = _sha256_file(manifest_path) + "  MANIFEST.json" if manifest_path.exists() else ""
    for ref in refs:
        path = root / ref
        local_failures: List[str] = []
        if not path.exists():
            local_failures.append(f"manifest_sha_missing:{ref}")
        elif path.read_text(encoding="utf-8").strip() != expected:
            local_failures.append(f"manifest_sha_mismatch:{ref}")
        failures.extend(local_failures)
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures})
    return {"failures": failures, "reports": reports}


def _checksum_report(
    ref: str,
    *,
    root: Path,
    active_rel_paths: Set[str],
    self_exclusions: Set[str],
    excluded_names: Iterable[str],
    check_hashes: bool = True,
) -> Dict[str, Any]:
    failures: List[str] = []
    path = root / ref
    entries: List[Tuple[str, str]] = []
    hash_mismatches = 0
    excluded_path_hits = 0
    if not path.exists():
        failures.append(f"checksum_missing:{ref}")
    else:
        entries, parse_failures = _parse_sha256sums(path)
        failures.extend(parse_failures)
        expected = sorted(item for item in active_rel_paths if item not in self_exclusions)
        got = sorted(rel for _, rel in entries)
        if got != expected:
            failures.append(f"checksum_entry_set_mismatch:{ref}:expected={len(expected)}:got={len(got)}")
        for digest, rel in entries:
            if _has_excluded_part(rel, excluded_names):
                excluded_path_hits += 1
                failures.append(f"checksum_excluded_path:{ref}:{rel}")
            file_path = root / rel
            if not file_path.exists():
                failures.append(f"checksum_file_missing:{ref}:{rel}")
                continue
            if check_hashes and _sha256_file(file_path) != digest:
                hash_mismatches += 1
                failures.append(f"hash_mismatch:{ref}:{rel}")
    return {
        "ref": ref,
        "ok": not failures,
        "entries": len(entries),
        "hash_mismatches": hash_mismatches,
        "excluded_path_hits": excluded_path_hits,
        "failures": failures,
    }


def validate_manifest_checksum_exclusion_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path,
    package_root: Path,
    check_hashes: bool = True,
) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    excluded_names = _as_string_list(policy.get("excluded_dir_names")) or sorted(DEFAULT_EXCLUDED_DIR_NAMES)
    project_only_excluded_names = _as_string_list(policy.get("project_only_excluded_dir_names"))
    project_excluded_files = _as_string_list(policy.get("project_excluded_file_refs"))
    failures = _policy_failures(payload)

    refs = list(_as_string_list(payload.get("refs")))
    refs.extend([
        str(policy.get("project_manifest_ref") or ""),
        str(policy.get("package_root_ref") or ""),
        str(policy.get("package_manifest_ref") or ""),
        str(policy.get("package_checksum_ref") or ""),
    ])
    refs.extend(_as_string_list(policy.get("project_manifest_sha_refs")))
    refs.extend(_as_string_list(policy.get("project_checksum_refs")))
    refs.extend(_as_string_list(policy.get("package_manifest_sha_refs")))
    ref_report = _resolve_refs(refs, project_root=project_root, package_root=package_root, owner="policy.refs")
    doc_ref_report = _resolve_refs(_as_string_list(policy.get("required_docs")), project_root=project_root, package_root=package_root, owner="policy.required_docs")
    runtime_report = _runtime_script_reports(policy, project_root=project_root, package_root=package_root)
    failures.extend(ref_report["failures"])
    failures.extend(doc_ref_report["failures"])
    failures.extend(runtime_report["failures"])

    package_root_ref = str(policy.get("package_root_ref") or "noemaforge")
    resolved_package_root = (project_root / package_root_ref).resolve()
    if not _is_relative_to(resolved_package_root, project_root) or not resolved_package_root.exists():
        failures.append(f"package_root_invalid:{package_root_ref}")
        resolved_package_root = package_root

    project_active = _active_files(
        project_root,
        excluded_names,
        root_only_excluded_dir_names=project_only_excluded_names,
        excluded_file_refs=project_excluded_files,
    )
    package_active = _active_files(resolved_package_root, excluded_names)
    project_rel = _relative_set(project_root, project_active)
    package_rel = _relative_set(resolved_package_root, package_active)

    project_manifest_ref = str(policy.get("project_manifest_ref") or "MANIFEST.json")
    package_manifest_ref = str(policy.get("package_manifest_ref") or "noemaforge/docs/MANIFEST.json")
    project_manifest = _manifest_report(project_manifest_ref, root=project_root, active_count=len(project_active), excluded_names=excluded_names)
    package_manifest = _manifest_report(package_manifest_ref, root=project_root, active_count=len(package_active), excluded_names=excluded_names)
    failures.extend(project_manifest["failures"])
    failures.extend(package_manifest["failures"])

    project_manifest_sha = _manifest_sha_reports(_as_string_list(policy.get("project_manifest_sha_refs")), manifest_path=project_root / project_manifest_ref, root=project_root)
    package_manifest_sha = _manifest_sha_reports(
        _as_string_list(policy.get("package_manifest_sha_refs")),
        manifest_path=project_root / package_manifest_ref,
        root=project_root,
    )
    failures.extend(project_manifest_sha["failures"])
    failures.extend(package_manifest_sha["failures"])

    checksum_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("project_checksum_refs")):
        report = _checksum_report(
            ref,
            root=project_root,
            active_rel_paths=project_rel,
            self_exclusions=set(_as_string_list(policy.get("project_checksum_self_exclusions"))),
            excluded_names=excluded_names,
            check_hashes=check_hashes,
        )
        checksum_reports.append(report)
        failures.extend(report["failures"])

    package_checksum = _checksum_report(
        str(policy.get("package_checksum_ref") or "noemaforge/checksums/SHA256SUMS"),
        root=resolved_package_root,
        active_rel_paths=package_rel,
        self_exclusions=set(_as_string_list(policy.get("package_checksum_self_exclusions"))),
        excluded_names=excluded_names,
        check_hashes=check_hashes,
    )
    checksum_reports.append(package_checksum)
    failures.extend(package_checksum["failures"])

    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "id": payload.get("id"),
        "version": payload.get("version"),
        "metrics": {
            "project_active_files": len(project_active),
            "package_active_files": len(package_active),
            "project_checksum_entries": sum(item["entries"] for item in checksum_reports if str(item["ref"]).startswith("SHA256SUMS")),
            "package_checksum_entries": package_checksum["entries"],
            "excluded_path_hits": sum(item["excluded_path_hits"] for item in checksum_reports),
            "hash_mismatches": sum(item["hash_mismatches"] for item in checksum_reports),
            "manifest_sha_files": len(project_manifest_sha["reports"]) + len(package_manifest_sha["reports"]),
            "refs": len(refs),
            "resolved_refs": len(ref_report["resolved_refs"]),
        },
        "failures": failures,
        "refs": ref_report,
        "docs": doc_ref_report,
        "runtime_scripts": runtime_report["reports"],
        "manifests": [project_manifest, package_manifest],
        "manifest_sha": project_manifest_sha["reports"] + package_manifest_sha["reports"],
        "checksums": checksum_reports,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate manifests and checksums exclude trash/cache paths.")
    parser.add_argument("--policy", default="noemaforge/configs/manifest-checksum-exclusion-policy.json")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--package-root", default="noemaforge")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--skip-hashes", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    package_root = (project_root / args.package_root).resolve() if not Path(args.package_root).is_absolute() else Path(args.package_root).resolve()
    policy_path = Path(args.policy)
    policy = load_policy(policy_path if policy_path.is_absolute() else project_root / policy_path)
    report = validate_manifest_checksum_exclusion_policy(
        policy,
        project_root=project_root,
        package_root=package_root,
        check_hashes=not args.skip_hashes,
    )
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
