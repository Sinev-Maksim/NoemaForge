#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/pytest_suite_partition_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Replace monolithic pytest execution with bounded shard plans for local release validation.
Inputs: Pytest suite partition policy and test file lists.
Outputs: JSON-compatible validation and shard-plan reports.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_pytest_suite_partition_runtime.py
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
from typing import Any, Dict, Iterable, List, Sequence


API_VERSION = "noemaforge.pytest-suite-partition/v1"
POLICY_KIND = "PytestSuitePartitionPolicy"
REPORT_KIND = "PytestSuitePartitionValidationReport"
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
    if str(policy.get("activation_state") or "") != "monolithic_pytest_replaced_by_bounded_shards":
        failures.append("policy_activation_state_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_host_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["max_tests_per_shard", "max_shard_seconds", "required_timeout_seconds"]:
        try:
            if int(policy.get(key) or 0) <= 0:
                failures.append(f"policy_{key}_invalid")
        except Exception:
            failures.append(f"policy_{key}_invalid")
    for key in [
        "pipeline_runtime_patterns",
        "forbidden_monolithic_commands",
        "required_shard_labels",
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
        for token in tokens:
            if text and token not in text:
                local_failures.append(f"runtime_token_missing:{ref}:{token}")
        failures.extend(local_failures)
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved})
    return {"failures": failures, "reports": reports}


def validate_pytest_suite_partition_policy(
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


def normalize_command(command: str) -> str:
    return " ".join(str(command or "").strip().replace("\\", "/").split()).lower()


def validate_pytest_command(command: str, *, policy: Dict[str, Any]) -> Dict[str, Any]:
    body = _policy_dict(policy)
    normalized = normalize_command(command)
    failures: List[str] = []
    forbidden = {normalize_command(item) for item in _as_string_list(body.get("forbidden_monolithic_commands"))}
    if normalized in forbidden:
        failures.append("forbidden_monolithic_pytest_command")
    if normalized.startswith("pytest") and "--maxfail" not in normalized:
        failures.append("pytest_command_missing_maxfail")
    if normalized.startswith("pytest") and "--timeout" not in normalized:
        failures.append("pytest_command_missing_timeout")
    return {
        "apiVersion": API_VERSION,
        "kind": "PytestCommandValidation",
        "ok": not failures,
        "command": command,
        "normalized_command": normalized,
        "failures": failures,
    }


def discover_test_files(tests_root: Path) -> List[str]:
    if not tests_root.exists():
        return []
    files = [
        path.as_posix()
        for path in sorted(tests_root.rglob("test_*.py"))
        if "__pycache__" not in path.parts and ".pytest_cache" not in path.parts
    ]
    return files


def _module_name_from_path(path: str) -> str:
    text = str(path or "").replace("\\", "/").strip()
    if text.endswith(".py"):
        text = text[:-3]
    parts = [part for part in text.split("/") if part]
    if "noemaforge" in parts:
        parts = parts[parts.index("noemaforge"):]
    return ".".join(parts)


def _label_for_test(path: str, patterns: Sequence[str]) -> str:
    name = PurePosixPath(str(path).replace("\\", "/")).name
    for pattern in patterns:
        if fnmatch.fnmatch(name, pattern):
            return "pipeline_runtime"
    return "general"


def _chunks(items: Sequence[str], size: int) -> Iterable[List[str]]:
    for index in range(0, len(items), size):
        yield list(items[index:index + size])


def partition_tests(test_files: Sequence[str], *, policy: Dict[str, Any]) -> Dict[str, Any]:
    body = _policy_dict(policy)
    max_tests = int(body.get("max_tests_per_shard") or 12)
    timeout = int(body.get("required_timeout_seconds") or body.get("max_shard_seconds") or 120)
    patterns = _as_string_list(body.get("pipeline_runtime_patterns")) or ["test_pipeline_*.py", "test_*pipeline*.py"]
    grouped: Dict[str, List[str]] = {"pipeline_runtime": [], "general": []}
    for raw in sorted({str(path).replace("\\", "/") for path in test_files if str(path or "").strip()}):
        grouped.setdefault(_label_for_test(raw, patterns), []).append(raw)

    shards: List[Dict[str, Any]] = []
    for label in sorted(grouped):
        for index, chunk in enumerate(_chunks(grouped[label], max_tests), start=1):
            if not chunk:
                continue
            modules = [_module_name_from_path(path) for path in chunk]
            shards.append({
                "label": label,
                "index": index,
                "timeout_seconds": timeout,
                "test_count": len(chunk),
                "tests": chunk,
                "modules": modules,
                "command": "python -B -m unittest " + " ".join(modules),
            })
    return {
        "apiVersion": API_VERSION,
        "kind": "PytestSuiteShardPlan",
        "activation_state": "monolithic_pytest_replaced_by_bounded_shards",
        "ok": True,
        "metrics": {
            "test_count": sum(shard["test_count"] for shard in shards),
            "shard_count": len(shards),
            "pipeline_runtime_shards": sum(1 for shard in shards if shard["label"] == "pipeline_runtime"),
        },
        "shards": shards,
    }


def validate_partition_plan(plan: Dict[str, Any], *, policy: Dict[str, Any]) -> Dict[str, Any]:
    body = _policy_dict(policy)
    max_tests = int(body.get("max_tests_per_shard") or 12)
    timeout = int(body.get("required_timeout_seconds") or body.get("max_shard_seconds") or 120)
    required_labels = set(_as_string_list(body.get("required_shard_labels")))
    failures: List[str] = []
    labels = {str(shard.get("label") or "") for shard in plan.get("shards") or [] if isinstance(shard, dict)}
    if required_labels and not required_labels.issubset(labels):
        failures.append("required_shard_label_missing")
    for shard in plan.get("shards") or []:
        if not isinstance(shard, dict):
            failures.append("shard_invalid")
            continue
        if int(shard.get("test_count") or 0) > max_tests:
            failures.append(f"shard_too_large:{shard.get('label')}:{shard.get('index')}")
        if int(shard.get("timeout_seconds") or 0) > timeout:
            failures.append(f"shard_timeout_too_high:{shard.get('label')}:{shard.get('index')}")
        if str(shard.get("label") or "") == "general":
            pipeline_named = [path for path in shard.get("tests") or [] if "pipeline" in PurePosixPath(str(path)).name]
            if pipeline_named:
                failures.append("pipeline_test_in_general_shard")
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "failures": failures,
        "metrics": plan.get("metrics") or {},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and plan bounded pytest suite partitions.")
    parser.add_argument("--policy", default="noemaforge/configs/pytest-suite-partition-policy.json")
    parser.add_argument("--tests-root", default="noemaforge/tests")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--package-root", default="noemaforge")
    parser.add_argument("--command", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    package_root = (project_root / args.package_root).resolve() if not Path(args.package_root).is_absolute() else Path(args.package_root).resolve()
    policy = load_policy(project_root / args.policy if not Path(args.policy).is_absolute() else args.policy)
    policy_report = validate_pytest_suite_partition_policy(policy, project_root=project_root, package_root=package_root)
    tests_root = project_root / args.tests_root if not Path(args.tests_root).is_absolute() else Path(args.tests_root)
    plan = partition_tests(discover_test_files(tests_root), policy=policy)
    plan_report = validate_partition_plan(plan, policy=policy)
    command_report = validate_pytest_command(args.command, policy=policy) if args.command else {"ok": True, "failures": []}
    report = {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": policy_report["ok"] and plan_report["ok"] and command_report["ok"],
        "policy": policy_report,
        "plan": plan,
        "plan_validation": plan_report,
        "command_validation": command_report,
    }
    if args.summary:
        report = {
            "apiVersion": API_VERSION,
            "kind": REPORT_KIND,
            "ok": report["ok"],
            "metrics": plan.get("metrics", {}),
            "failures": policy_report["failures"] + plan_report["failures"] + command_report["failures"],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
