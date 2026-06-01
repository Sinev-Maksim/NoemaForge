#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/docs_hygiene_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-21
Purpose: Validate canonical Markdown placement, changelog hygiene and active-file readability for prelaunch docs.
Inputs: noemaforge/configs/docs-hygiene-policy.json plus local project/package roots.
Outputs: JSON-compatible DocsHygieneReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_docs_hygiene_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import production_ai_contracts as pac


API_VERSION = "noemaforge.docs-hygiene/v1"
POLICY_KIND = "DocsHygienePolicy"
REPORT_KIND = "DocsHygieneReport"

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
TODO_CHECK_RE_TEMPLATE = r"^\s*-\s*\[[xX]\]\s+{label}\s*$"
SKIPPED_DIR_NAMES = {
    ".codex",
    ".cursor",
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
    "pytest",
    "PyYAML",
    "trash",
}


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_path(value: Path | str) -> Path:
    return Path(value).resolve()


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _normalize_ref(value: str) -> str:
    return str(value or "").strip().replace("\\", "/")


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


def _project_relative(path: Path, project_root: Path) -> str:
    try:
        return _display_path(path.relative_to(project_root))
    except ValueError:
        return _display_path(path.resolve().relative_to(project_root.resolve()))


def _starts_with_any(path: str, prefixes: Iterable[str]) -> bool:
    normalized = _normalize_ref(path)
    return any(normalized.startswith(_normalize_ref(prefix)) for prefix in prefixes)


def _matches_any(name: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    candidates = [
        ("package", package_root / ref),
        ("project", project_root / ref),
    ]
    if not _normalize_ref(ref).startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / ref))

    checked: List[str] = []
    for base_name, path in candidates:
        checked.append(_display_path(path))
        if path.exists():
            return {
                "ok": True,
                "ref": ref,
                "resolved_under": base_name,
                "path": _display_path(path),
                "checked": checked,
            }
    return {"ok": False, "ref": ref, "resolved_under": "", "path": "", "checked": checked}


def _iter_markdown_files(project_root: Path) -> List[Path]:
    markdown_files: List[Path] = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [item for item in dirs if item not in SKIPPED_DIR_NAMES]
        root_path = Path(root)
        for name in files:
            if name.lower().endswith(".md"):
                markdown_files.append(root_path / name)
    return sorted(markdown_files, key=lambda item: _display_path(item))


def _iter_active_files(project_root: Path) -> List[Path]:
    active_files: List[Path] = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [item for item in dirs if item not in SKIPPED_DIR_NAMES]
        root_path = Path(root)
        for name in files:
            active_files.append(root_path / name)
    return sorted(active_files, key=lambda item: _display_path(item))


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    path = Path(policy_path)
    return json.loads(path.read_text(encoding="utf-8"))


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if not SAFE_ID_RE.match(str(payload.get("id") or "")):
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in {"draft", "shadow", "stable", "retired"}:
        failures.append("policy_status_invalid")

    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    required_arrays = [
        "approved_markdown_prefixes",
        "allowed_docs_root_markdown",
        "canonical_changelog_refs",
        "forbidden_markdown_prefixes",
        "required_canonical_files",
        "required_checked_todo_items",
    ]
    for key in required_arrays:
        if not isinstance(policy.get(key), list) or not policy.get(key):
            failures.append(f"policy_{key}_empty")

    for key in [
        "approved_markdown_prefixes",
        "allowed_root_markdown",
        "allowed_docs_root_markdown",
        "allowed_package_root_markdown",
        "legacy_root_markdown_patterns",
        "canonical_changelog_refs",
        "allowed_parallel_changelog_prefixes",
        "forbidden_markdown_prefixes",
        "required_canonical_files",
    ]:
        for ref in _as_string_list(policy.get(key)):
            if key.endswith("prefixes"):
                candidate = ref.rstrip("/") + "/"
                if not _is_safe_relative_ref(candidate + "sentinel.md"):
                    failures.append(f"policy_unsafe_{key}:{ref}")
            elif "*" not in ref and not _is_safe_relative_ref(ref):
                failures.append(f"policy_unsafe_{key}:{ref}")

    for item in policy.get("required_checked_todo_items", []):
        if not isinstance(item, dict):
            failures.append("policy_todo_item_not_object")
            continue
        if not _is_safe_relative_ref(str(item.get("file") or "")):
            failures.append(f"policy_todo_item_file_unsafe:{item.get('file')}")
        if not str(item.get("label") or "").strip():
            failures.append(f"policy_todo_item_label_empty:{item.get('file')}")
    return failures


def _validate_refs(
    refs: Sequence[str],
    *,
    project_root: Path,
    package_root: Path,
    owner: str,
) -> Dict[str, List[Dict[str, Any]] | List[str]]:
    failures: List[str] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            item = {"owner": owner, "ref": ref}
            unsafe_refs.append(item)
            failures.append(f"unsafe_ref:{owner}:{ref}")
            continue
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        resolved["owner"] = owner
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            missing_refs.append(resolved)
            failures.append(f"missing_ref:{owner}:{ref}")
    return {
        "failures": failures,
        "resolved_refs": resolved_refs,
        "missing_refs": missing_refs,
        "unsafe_refs": unsafe_refs,
    }


def _validate_required_files(required_files: Sequence[str], *, project_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    resolved: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    unsafe: List[Dict[str, Any]] = []
    for ref in required_files:
        if not _is_safe_relative_ref(ref):
            item = {"ref": ref}
            unsafe.append(item)
            failures.append(f"unsafe_required_canonical_file:{ref}")
            continue
        path = (project_root / ref).resolve()
        if not _is_relative_to(path, project_root):
            item = {"ref": ref, "path": _display_path(path)}
            unsafe.append(item)
            failures.append(f"unsafe_required_canonical_file:{ref}")
        elif path.exists():
            resolved.append({"ref": ref, "path": _display_path(path)})
        else:
            missing.append({"ref": ref, "path": _display_path(path)})
            failures.append(f"missing_required_canonical_file:{ref}")
    return {"failures": failures, "resolved": resolved, "missing": missing, "unsafe": unsafe}


def _validate_markdown_layout(markdown_files: Sequence[Path], *, project_root: Path, policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    warnings: List[str] = []
    approved: List[str] = []
    root_allowed: List[str] = []
    docs_root_allowed: List[str] = []
    forbidden: List[str] = []
    package_root_allowed: List[str] = []
    legacy_root: List[str] = []
    outside_policy: List[str] = []

    approved_prefixes = _as_string_list(policy.get("approved_markdown_prefixes"))
    allowed_root = set(_as_string_list(policy.get("allowed_root_markdown")))
    allowed_docs_root = set(_as_string_list(policy.get("allowed_docs_root_markdown")))
    allowed_package_root = set(_as_string_list(policy.get("allowed_package_root_markdown")))
    legacy_patterns = _as_string_list(policy.get("legacy_root_markdown_patterns"))
    forbidden_prefixes = _as_string_list(policy.get("forbidden_markdown_prefixes"))

    for path in markdown_files:
        rel = _project_relative(path, project_root)
        parts = PurePosixPath(rel).parts
        if _starts_with_any(rel, forbidden_prefixes):
            forbidden.append(rel)
            failures.append(f"forbidden_markdown_prefix:{rel}")
        elif len(parts) == 1:
            if rel in allowed_root:
                root_allowed.append(rel)
            elif _matches_any(rel, legacy_patterns):
                legacy_root.append(rel)
                warnings.append(f"legacy_root_markdown:{rel}")
            else:
                outside_policy.append(rel)
                failures.append(f"root_markdown_not_allowed:{rel}")
        elif len(parts) == 3 and parts[0] == "noemaforge" and parts[1] == "docs":
            if rel in allowed_docs_root:
                docs_root_allowed.append(rel)
            else:
                outside_policy.append(rel)
                failures.append(f"docs_root_markdown_not_allowed:{rel}")
        elif rel in allowed_package_root:
            package_root_allowed.append(rel)
        elif _starts_with_any(rel, approved_prefixes):
            approved.append(rel)
        else:
            outside_policy.append(rel)
            failures.append(f"markdown_outside_approved_prefix:{rel}")

    return {
        "failures": failures,
        "warnings": warnings,
        "approved": sorted(approved),
        "root_allowed": sorted(root_allowed),
        "docs_root_allowed": sorted(docs_root_allowed),
        "forbidden": sorted(forbidden),
        "package_root_allowed": sorted(package_root_allowed),
        "legacy_root": sorted(legacy_root),
        "outside_policy": sorted(outside_policy),
    }


def _validate_changelog_layout(markdown_files: Sequence[Path], *, project_root: Path, policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    canonical = set(_as_string_list(policy.get("canonical_changelog_refs")))
    allowed_prefixes = _as_string_list(policy.get("allowed_parallel_changelog_prefixes"))
    legacy_patterns = _as_string_list(policy.get("legacy_root_markdown_patterns"))
    allowed_parallel: List[str] = []
    canonical_found: List[str] = []
    legacy_root: List[str] = []
    parallel: List[str] = []

    for path in markdown_files:
        rel = _project_relative(path, project_root)
        name = path.name
        if not (fnmatch.fnmatchcase(name, "CHANGELOG*.md") or fnmatch.fnmatchcase(name, "RELEASE_NOTES*.md")):
            continue
        if rel in canonical:
            canonical_found.append(rel)
        elif len(PurePosixPath(rel).parts) == 1 and _matches_any(rel, legacy_patterns):
            legacy_root.append(rel)
        elif _starts_with_any(rel, allowed_prefixes):
            allowed_parallel.append(rel)
        else:
            parallel.append(rel)
            failures.append(f"parallel_changelog_file:{rel}")

    for ref in canonical:
        if ref not in canonical_found:
            failures.append(f"missing_canonical_changelog_ref:{ref}")

    return {
        "failures": failures,
        "canonical_found": sorted(canonical_found),
        "allowed_parallel": sorted(allowed_parallel),
        "legacy_root": sorted(legacy_root),
        "parallel": sorted(parallel),
    }


def _validate_active_file_readability(active_files: Sequence[Path], *, project_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    readable: List[str] = []
    unreadable: List[Dict[str, str]] = []

    for path in active_files:
        rel = _project_relative(path, project_root)
        try:
            path.stat()
        except OSError as exc:
            unreadable.append({"path": rel, "error": exc.__class__.__name__})
            failures.append(f"unreadable_active_file:{rel}:{exc.__class__.__name__}")
            continue

        try:
            with path.open("rb") as handle:
                handle.read(1)
        except OSError as exc:
            unreadable.append({"path": rel, "error": exc.__class__.__name__})
            failures.append(f"unreadable_active_file:{rel}:{exc.__class__.__name__}")
        else:
            readable.append(rel)

    return {
        "failures": failures,
        "readable": sorted(readable),
        "unreadable": sorted(unreadable, key=lambda item: item["path"]),
    }


def _validate_forbidden_active_text(
    active_files: Sequence[Path],
    *,
    project_root: Path,
    forbidden_tokens: Sequence[str],
) -> Dict[str, Any]:
    failures: List[str] = []
    hits: List[Dict[str, Any]] = []
    tokens = [token for token in _as_string_list(list(forbidden_tokens)) if token]
    if not tokens:
        return {"failures": failures, "hits": hits, "tokens": []}

    for path in active_files:
        rel = _project_relative(path, project_root)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not any(token in text for token in tokens):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for token in tokens:
                if token in line:
                    hits.append({"path": rel, "line": line_no, "token": token})
                    failures.append(f"forbidden_active_text:{rel}:{line_no}:{token}")

    return {
        "failures": failures,
        "hits": sorted(hits, key=lambda item: (item["path"], item["line"], item["token"])),
        "tokens": sorted(tokens),
    }


def _todo_item_checked(todo_text: str, label: str) -> bool:
    pattern = TODO_CHECK_RE_TEMPLATE.format(label=re.escape(label.strip()))
    return re.search(pattern, todo_text, flags=re.MULTILINE) is not None


def _validate_todo_items(items: Sequence[Dict[str, Any]], *, project_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    checked: List[Dict[str, str]] = []
    missing: List[Dict[str, str]] = []
    unsafe: List[Dict[str, str]] = []
    cache: Dict[str, str] = {}

    for item in items:
        file_ref = _normalize_ref(str(item.get("file") or ""))
        label = str(item.get("label") or "").strip()
        if not _is_safe_relative_ref(file_ref):
            unsafe.append({"file": file_ref, "label": label})
            failures.append(f"todo_file_unsafe:{file_ref}")
            continue
        path = (project_root / file_ref).resolve()
        if not _is_relative_to(path, project_root):
            unsafe.append({"file": file_ref, "label": label})
            failures.append(f"todo_file_unsafe:{file_ref}")
            continue
        if file_ref not in cache:
            if not path.exists():
                cache[file_ref] = ""
                failures.append(f"todo_file_missing:{file_ref}")
            else:
                cache[file_ref] = path.read_text(encoding="utf-8")
        if cache[file_ref] and _todo_item_checked(cache[file_ref], label):
            checked.append({"file": file_ref, "label": label})
        else:
            missing.append({"file": file_ref, "label": label})
            failures.append(f"todo_item_not_checked:{file_ref}:{label}")

    return {"failures": failures, "checked": checked, "missing": missing, "unsafe": unsafe}


def validate_docs_hygiene_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root)
    if not project.exists():
        raise FileNotFoundError(project)
    if not package.exists():
        raise FileNotFoundError(package)

    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    active_files = _iter_active_files(project)
    markdown_files = _iter_markdown_files(project)

    failures: List[str] = []
    warnings: List[str] = []
    failures.extend(_policy_failures(payload))

    readability_result = _validate_active_file_readability(active_files, project_root=project)
    failures.extend(readability_result["failures"])

    forbidden_text_result = _validate_forbidden_active_text(
        active_files,
        project_root=project,
        forbidden_tokens=_as_string_list(policy.get("forbidden_active_text")),
    )
    failures.extend(forbidden_text_result["failures"])

    required_result = _validate_required_files(_as_string_list(policy.get("required_canonical_files")), project_root=project)
    failures.extend(required_result["failures"])

    layout_result = _validate_markdown_layout(markdown_files, project_root=project, policy=policy)
    failures.extend(layout_result["failures"])
    warnings.extend(layout_result["warnings"])

    changelog_result = _validate_changelog_layout(markdown_files, project_root=project, policy=policy)
    failures.extend(changelog_result["failures"])

    todo_result = _validate_todo_items(
        payload.get("policy", {}).get("required_checked_todo_items", [])
        if isinstance(payload.get("policy"), dict)
        else [],
        project_root=project,
    )
    failures.extend(todo_result["failures"])

    refs_result = _validate_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(refs_result["failures"])

    gate_evidence = docs_hygiene_report_to_gate_evidence(
        {
            "kind": REPORT_KIND,
            "ok": not failures,
            "created_at": _nowz(),
            "failures": sorted(set(failures)),
            "warnings": sorted(set(warnings)),
        },
        artifact_uri="memory://docs-hygiene-report",
    )
    gate = pac.evaluate_gate({"change_id": "docs-hygiene", "domain": "pipeline"}, gate_evidence)
    if not gate.get("ok"):
        failures.append("evaluation_gate_failed:docs-hygiene")

    metrics = {
        "active_files": len(active_files),
        "active_file_readability_failures": len(readability_result["unreadable"]),
        "forbidden_active_text_hits": len(forbidden_text_result["hits"]),
        "markdown_files": len(markdown_files),
        "approved_markdown_files": len(layout_result["approved"]),
        "allowed_root_markdown_files": len(layout_result["root_allowed"]),
        "allowed_docs_root_markdown_files": len(layout_result["docs_root_allowed"]),
        "allowed_package_root_markdown_files": len(layout_result["package_root_allowed"]),
        "forbidden_markdown_files": len(layout_result["forbidden"]),
        "legacy_root_markdown_files": len(layout_result["legacy_root"]),
        "outside_policy_markdown_files": len(layout_result["outside_policy"]),
        "canonical_changelog_files": len(changelog_result["canonical_found"]),
        "allowed_parallel_changelog_files": len(changelog_result["allowed_parallel"]),
        "legacy_root_changelog_files": len(changelog_result["legacy_root"]),
        "parallel_changelog_files": len(changelog_result["parallel"]),
        "required_canonical_files": len(required_result["resolved"]),
        "missing_required_canonical_files": len(required_result["missing"]),
        "todo_items_checked": len(todo_result["checked"]),
        "todo_items_missing": len(todo_result["missing"]),
        "refs": len(refs_result["resolved_refs"]) + len(refs_result["missing_refs"]) + len(refs_result["unsafe_refs"]),
        "resolved_refs": len(refs_result["resolved_refs"]),
        "missing_refs": len(refs_result["missing_refs"]),
        "unsafe_refs": len(refs_result["unsafe_refs"]),
    }

    checks = [
        {"id": "active_file_readability", "status": "passed" if not readability_result["unreadable"] else "failed"},
        {"id": "forbidden_active_text", "status": "passed" if not forbidden_text_result["hits"] else "failed"},
        {"id": "required_canonical_files", "status": "passed" if not required_result["missing"] else "failed"},
        {"id": "markdown_layout", "status": "passed" if not layout_result["outside_policy"] and not layout_result["forbidden"] else "failed"},
        {"id": "canonical_changelog", "status": "passed" if not changelog_result["parallel"] else "failed"},
        {"id": "todo_items_checked", "status": "passed" if not todo_result["missing"] else "failed"},
        {"id": "refs_resolved", "status": "passed" if not refs_result["missing_refs"] and not refs_result["unsafe_refs"] else "failed"},
        {"id": "evaluation_gate", "status": "passed" if gate.get("ok") else "failed"},
    ]

    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "policy_path": str(policy_path or ""),
        "project_root": _display_path(project),
        "package_root": _display_path(package),
        "failures": sorted(set(failures)),
        "warnings": sorted(set(warnings)),
        "metrics": metrics,
        "checks": checks,
        "active_file_readability": readability_result,
        "forbidden_active_text": forbidden_text_result,
        "required_files": required_result,
        "markdown_layout": layout_result,
        "changelog_layout": changelog_result,
        "todo_items": todo_result,
        "resolved_refs": sorted(refs_result["resolved_refs"], key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(refs_result["missing_refs"], key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(refs_result["unsafe_refs"], key=lambda item: (item["owner"], item["ref"])),
    }


def docs_hygiene_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("docs_hygiene_report_required")
    failures = report.get("failures") if isinstance(report.get("failures"), list) else []
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    status = "passed" if report.get("ok") and not failures else "failed"
    warning_score = 1.0 if len(warnings) <= 128 else 0.0
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": [
            {"id": "pipeline_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "rollback_plan", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "safety_eval", "status": status, "score": 1.0 if not failures else 0.0, "threshold": 1.0},
            {"id": "warning_budget", "status": "passed" if warning_score == 1.0 else "failed", "score": warning_score, "threshold": 1.0},
        ],
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Markdown documentation hygiene.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/docs-hygiene-policy.json",
        help="Policy path, absolute or relative to project root.",
    )
    parser.add_argument("--summary", action="store_true", help="Emit a compact validation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = _as_path(args.project_root)
    package_root = _as_path(args.package_root) if args.package_root else project_root / "noemaforge"
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = project_root / policy_path

    report = validate_docs_hygiene_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "DocsHygieneSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "policy_path": report["policy_path"],
            "metrics": report["metrics"],
            "failures": report["failures"],
            "warnings": report["warnings"][:10],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
