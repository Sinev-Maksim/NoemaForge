#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/yaml_inventory_readability_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate active YAML files are readable and pass a bounded stdlib syntax guard.
Inputs: noemaforge/configs/yaml-inventory-readability-policy.json and active YAML files.
Outputs: JSON-compatible YAML inventory readability reports.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_yaml_inventory_readability_runtime.py
Notes: This is not a full YAML semantic parser; it is a deterministic fallback gate when PyYAML is unavailable.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Sequence, Tuple


API_VERSION = "noemaforge.yaml-inventory-readability/v1"
POLICY_KIND = "YamlInventoryReadabilityPolicy"
REPORT_KIND = "YamlInventoryReadabilityReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
BLOCK_SCALAR_RE = re.compile(r":\s*[|>][-+]?\d*\s*(?:#.*)?$")
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


def _project_relative(path: Path, project_root: Path) -> str:
    return _display_path(path.resolve().relative_to(project_root.resolve()))


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
            return {
                "ok": True,
                "ref": ref,
                "resolved_under": base_name,
                "path": _display_path(path),
                "checked": checked,
            }
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
    if str(policy.get("activation_state") or "") != "yaml_inventory_readability_gate":
        failures.append("policy_activation_state_invalid")
    if str(policy.get("parse_scope") or "") != "readability_and_yaml_lite_syntax_only":
        failures.append("policy_parse_scope_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_external_yaml_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in [
        "scan_extensions",
        "scan_root_refs",
        "excluded_dir_names",
        "required_runtime_scripts",
        "required_runtime_tokens",
        "required_docs",
    ]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    for ext in _as_string_list(policy.get("scan_extensions")):
        if ext not in {".yaml", ".yml"}:
            failures.append(f"policy_scan_extension_unsupported:{ext}")
    try:
        if int(policy.get("max_file_bytes") or 0) <= 0:
            failures.append("policy_max_file_bytes_invalid")
    except Exception:
        failures.append("policy_max_file_bytes_invalid")
    for ref_key in ["scan_root_refs", "required_runtime_scripts", "required_docs"]:
        for ref in _as_string_list(policy.get(ref_key)):
            if not _is_safe_relative_ref(ref):
                failures.append(f"policy_unsafe_{ref_key}:{ref}")
    return failures


def _iter_yaml_paths(project_root: Path, policy: Dict[str, Any]) -> Tuple[List[Path], List[str]]:
    failures: List[str] = []
    extensions = {item.lower() for item in _as_string_list(policy.get("scan_extensions"))} or {".yaml", ".yml"}
    excluded_names = set(_as_string_list(policy.get("excluded_dir_names"))) or set(DEFAULT_EXCLUDED_DIR_NAMES)
    roots: List[Path] = []
    for ref in _as_string_list(policy.get("scan_root_refs")):
        if not _is_safe_relative_ref(ref):
            failures.append(f"unsafe_scan_root:{ref}")
            continue
        root = (project_root / ref).resolve()
        if not _is_relative_to(root, project_root):
            failures.append(f"unsafe_scan_root:{ref}")
            continue
        if root.exists() and root.is_dir():
            roots.append(root)
        elif root.exists():
            failures.append(f"scan_root_not_directory:{ref}")
        else:
            failures.append(f"scan_root_missing:{ref}")

    paths: List[Path] = []
    seen: set[Path] = set()
    for root in roots:
        for current_root, dirs, files in os.walk(root):
            dirs[:] = [item for item in dirs if item not in excluded_names]
            current = Path(current_root)
            for name in files:
                path = current / name
                if path.suffix.lower() in extensions:
                    resolved = path.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        paths.append(resolved)
    return sorted(paths, key=lambda item: _display_path(item)), failures


def _indent_count(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _line_has_tab_indentation(line: str) -> bool:
    prefix = line[: len(line) - len(line.lstrip(" \t"))]
    return "\t" in prefix


def _strip_comment_outside_quotes(line: str) -> str:
    out: List[str] = []
    quote = ""
    escaped = False
    for ch in line:
        if quote == '"' and escaped:
            out.append(ch)
            escaped = False
            continue
        if quote == '"' and ch == "\\":
            out.append(ch)
            escaped = True
            continue
        if ch in {"'", '"'}:
            if not quote:
                quote = ch
            elif quote == ch:
                quote = ""
            out.append(ch)
            continue
        if ch == "#" and not quote:
            break
        out.append(ch)
    return "".join(out)


def _flow_bracket_failures(text: str, *, source: str = "") -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    stack: List[Tuple[str, int, int]] = []
    pairs = {"]": "[", "}": "{"}
    in_block_scalar = False
    block_indent = -1
    quote = ""
    escaped = False

    for line_number, raw_line in enumerate(str(text or "").splitlines(), start=1):
        if _line_has_tab_indentation(raw_line):
            continue
        stripped = raw_line.strip()
        indent = _indent_count(raw_line)
        if in_block_scalar:
            if stripped and indent <= block_indent:
                in_block_scalar = False
            else:
                continue
        if BLOCK_SCALAR_RE.search(raw_line):
            in_block_scalar = True
            block_indent = indent
            continue
        line = _strip_comment_outside_quotes(raw_line)
        quote = ""
        escaped = False
        for column, ch in enumerate(line, start=1):
            if quote == '"' and escaped:
                escaped = False
                continue
            if quote == '"' and ch == "\\":
                escaped = True
                continue
            if ch in {"'", '"'}:
                if not quote:
                    quote = ch
                elif quote == ch:
                    quote = ""
                continue
            if quote:
                continue
            if ch in "[{":
                stack.append((ch, line_number, column))
            elif ch in pairs:
                if not stack or stack[-1][0] != pairs[ch]:
                    failures.append({
                        "source": source,
                        "line": line_number,
                        "column": column,
                        "reason": "unmatched_flow_closer",
                        "token": ch,
                    })
                else:
                    stack.pop()
    for token, line_number, column in stack:
        failures.append({
            "source": source,
            "line": line_number,
            "column": column,
            "reason": "unclosed_flow_opener",
            "token": token,
        })
    return failures


def lint_yaml_text(text: str, *, source: str = "", require_nonempty: bool = True) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    content_lines = 0
    for line_number, raw_line in enumerate(str(text or "").splitlines(), start=1):
        stripped = raw_line.strip()
        if _line_has_tab_indentation(raw_line):
            failures.append({
                "source": source,
                "line": line_number,
                "column": 1,
                "reason": "tab_indentation",
                "token": "\\t",
            })
        if stripped and not stripped.startswith("#") and stripped not in {"---", "..."}:
            content_lines += 1
    if require_nonempty and content_lines == 0:
        failures.append({"source": source, "line": 1, "column": 1, "reason": "empty_yaml_document", "token": ""})
    failures.extend(_flow_bracket_failures(text, source=source))
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


def scan_yaml_inventory(policy: Dict[str, Any], *, project_root: Path) -> Dict[str, Any]:
    yaml_paths, root_failures = _iter_yaml_paths(project_root, policy)
    max_file_bytes = int(policy.get("max_file_bytes") or 1048576)
    require_nonempty = policy.get("require_nonempty_yaml") is not False
    failures: List[str] = list(root_failures)
    reports: List[Dict[str, Any]] = []
    bytes_scanned = 0
    tab_indentation_failures = 0
    flow_syntax_failures = 0
    readability_failures = 0

    for path in yaml_paths:
        ref = _project_relative(path, project_root)
        local_failures: List[str] = []
        lint_failures: List[Dict[str, Any]] = []
        size_bytes = 0
        try:
            stat = path.stat()
            size_bytes = int(stat.st_size)
            if size_bytes > max_file_bytes:
                local_failures.append(f"yaml_file_too_large:{ref}:{size_bytes}")
            raw = path.read_bytes()
            bytes_scanned += len(raw)
            if b"\x00" in raw:
                local_failures.append(f"yaml_nul_byte:{ref}")
            text = raw.decode("utf-8-sig")
            lint_failures = lint_yaml_text(text, source=ref, require_nonempty=require_nonempty)
            for item in lint_failures:
                reason = str(item.get("reason") or "")
                local_failures.append(f"yaml_lint:{ref}:{item.get('line')}:{reason}")
                if reason == "tab_indentation":
                    tab_indentation_failures += 1
                elif reason in {"unclosed_flow_opener", "unmatched_flow_closer"}:
                    flow_syntax_failures += 1
        except UnicodeDecodeError as exc:
            readability_failures += 1
            local_failures.append(f"yaml_utf8_decode_failed:{ref}:{exc.start}")
        except OSError as exc:
            readability_failures += 1
            local_failures.append(f"yaml_read_failed:{ref}:{exc.__class__.__name__}")
        failures.extend(local_failures)
        reports.append({
            "ref": ref,
            "ok": not local_failures,
            "size_bytes": size_bytes,
            "failures": local_failures,
            "lint_failures": lint_failures,
        })

    return {
        "ok": not failures,
        "failures": failures,
        "yaml_files": reports,
        "metrics": {
            "yaml_files": len(yaml_paths),
            "bytes_scanned": bytes_scanned,
            "roots_scanned": len(_as_string_list(policy.get("scan_root_refs"))),
            "tab_indentation_failures": tab_indentation_failures,
            "flow_syntax_failures": flow_syntax_failures,
            "readability_failures": readability_failures,
        },
    }


def validate_yaml_inventory_readability_policy(
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
    scan_report = scan_yaml_inventory(policy, project_root=project_root)
    failures.extend(ref_report["failures"])
    failures.extend(doc_ref_report["failures"])
    failures.extend(runtime_report["failures"])
    failures.extend(scan_report["failures"])
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "id": payload.get("id"),
        "version": payload.get("version"),
        "parse_scope": policy.get("parse_scope"),
        "metrics": {
            **scan_report["metrics"],
            "refs": len(_as_string_list(payload.get("refs"))),
            "resolved_refs": len(ref_report["resolved_refs"]),
            "required_docs": len(_as_string_list(policy.get("required_docs"))),
            "runtime_scripts": len(_as_string_list(policy.get("required_runtime_scripts"))),
        },
        "failures": failures,
        "refs": ref_report,
        "docs": doc_ref_report,
        "runtime_scripts": runtime_report["reports"],
        "yaml_files": scan_report["yaml_files"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate active YAML readability with a stdlib fallback gate.")
    parser.add_argument("--policy", default="noemaforge/configs/yaml-inventory-readability-policy.json")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--package-root", default="noemaforge")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    package_root = (project_root / args.package_root).resolve() if not Path(args.package_root).is_absolute() else Path(args.package_root).resolve()
    policy_path = Path(args.policy)
    policy = load_policy(policy_path if policy_path.is_absolute() else project_root / policy_path)
    report = validate_yaml_inventory_readability_policy(policy, project_root=project_root, package_root=package_root)
    if args.summary:
        report = {
            "apiVersion": API_VERSION,
            "kind": REPORT_KIND,
            "ok": report["ok"],
            "parse_scope": report["parse_scope"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
