#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/sense_privacy_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate Sense_State and Privacy_Filter contracts before persistence/export.
Inputs: noemaforge/configs/sense-privacy-policy.json and SensePrivacy example sets.
Outputs: JSON-compatible SensePrivacyValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_sense_privacy_runtime.py
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
from typing import Any, Dict, List, Optional, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import production_ai_contracts as pac


API_VERSION = "noemaforge.sense-privacy/v1"
POLICY_KIND = "SensePrivacyPolicy"
SET_KIND = "SensePrivacySet"
STATE_KIND = "SenseState"
REPORT_KIND = "SensePrivacyValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_METRIC_GROUPS = {"cpu", "memory", "disk", "network", "load", "runtime"}
REQUIRED_METRIC_GROUPS = {"cpu", "memory", "disk", "network", "load"}
VALID_PRESSURE_LEVELS = {"unknown", "low", "medium", "high", "critical"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,180}$")
PATH_VALUE_RE = re.compile(r"([A-Za-z]:\\|/home/|/Users/|/mnt/|\\\\)")


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_path(value: Path | str) -> Path:
    return Path(value).resolve()


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    candidates = [
        ("package", package_root / ref),
        ("project", project_root / ref),
    ]
    if not str(ref).startswith("noemaforge/"):
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
    return {"failures": failures, "resolved_refs": resolved_refs, "missing_refs": missing_refs, "unsafe_refs": unsafe_refs}


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def load_example_set(example_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(example_path).read_text(encoding="utf-8"))


def _forbidden_keys(policy: Dict[str, Any]) -> set[str]:
    return {item.lower() for item in _as_string_list(policy.get("forbidden_keys"))}


def _key_forbidden(key: str, policy: Dict[str, Any]) -> bool:
    lower = str(key or "").strip().lower()
    forbidden = _forbidden_keys(policy)
    return lower in forbidden or any(token in lower for token in ["secret", "token", "cmdline", "command_line"])


def apply_privacy_filter(value: Any, policy: Dict[str, Any], *, path: str = "$") -> Dict[str, Any]:
    redactions: List[Dict[str, str]] = []

    def visit(item: Any, current_path: str) -> Any:
        if isinstance(item, dict):
            output: Dict[str, Any] = {}
            for key, child in item.items():
                child_path = f"{current_path}.{key}"
                if _key_forbidden(str(key), policy):
                    redactions.append({"path": child_path, "reason": "forbidden_key"})
                    continue
                output[str(key)] = visit(child, child_path)
            return output
        if isinstance(item, list):
            return [visit(child, f"{current_path}[{index}]") for index, child in enumerate(item)]
        if isinstance(item, str) and policy.get("forbid_raw_paths") is True and PATH_VALUE_RE.search(item):
            redactions.append({"path": current_path, "reason": "path_like_value"})
            return "[REDACTED]"
        return item

    return {"filtered": visit(value, path), "redactions": redactions}


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
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
    for key in [
        "require_coarse_host_metrics",
        "require_privacy_filter_before_persistence",
        "forbid_raw_process_metadata",
        "forbid_raw_paths",
        "forbid_raw_usernames",
        "forbid_raw_environment",
        "forbid_raw_command_lines",
        "local_only_default",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    allowed = set(_as_string_list(policy.get("allowed_metric_groups")))
    required = set(_as_string_list(policy.get("required_metric_groups")))
    pressures = set(_as_string_list(policy.get("allowed_pressure_levels")))
    failures.extend(f"policy_invalid_metric_group:{item}" for item in sorted(allowed - VALID_METRIC_GROUPS))
    failures.extend(f"policy_unknown_required_metric_group:{item}" for item in sorted(required - VALID_METRIC_GROUPS))
    failures.extend(f"policy_invalid_pressure_level:{item}" for item in sorted(pressures - VALID_PRESSURE_LEVELS))
    if not REQUIRED_METRIC_GROUPS.issubset(required):
        failures.append("policy_required_metric_groups_incomplete")
    if not _forbidden_keys(policy):
        failures.append("policy_forbidden_keys_empty")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _raw_metadata_keys_in_metrics(metrics: Any, policy: Dict[str, Any], path: str = "metrics") -> List[str]:
    found: List[str] = []
    if isinstance(metrics, dict):
        for key, value in metrics.items():
            child_path = f"{path}.{key}"
            if _key_forbidden(str(key), policy):
                found.append(child_path)
            found.extend(_raw_metadata_keys_in_metrics(value, policy, child_path))
    elif isinstance(metrics, list):
        for index, value in enumerate(metrics):
            found.extend(_raw_metadata_keys_in_metrics(value, policy, f"{path}[{index}]"))
    return found


def _metric_value_failures(metrics: Dict[str, Any], policy: Dict[str, Any], state_id: str) -> List[str]:
    failures: List[str] = []
    allowed_pressure = set(_as_string_list(policy.get("allowed_pressure_levels")))
    for group, payload in metrics.items():
        if not isinstance(payload, dict):
            failures.append(f"state_metric_group_not_object:{state_id}:{group}")
            continue
        pressure = payload.get("pressure")
        if pressure is not None and str(pressure) not in allowed_pressure:
            failures.append(f"state_pressure_invalid:{state_id}:{group}:{pressure}")
        for key, value in payload.items():
            if key.endswith("_percent"):
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    failures.append(f"state_percent_not_numeric:{state_id}:{group}:{key}")
                    continue
                if numeric < 0.0 or numeric > 100.0:
                    failures.append(f"state_percent_out_of_range:{state_id}:{group}:{key}:{numeric}")
    return failures


def _state_failures(state: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    state_id = str(state.get("id") or "<missing>")
    if state.get("apiVersion") != API_VERSION:
        failures.append(f"state_api_version_invalid:{state_id}")
    if state.get("kind") != STATE_KIND:
        failures.append(f"state_kind_invalid:{state_id}")
    if not SAFE_ID_RE.match(state_id):
        failures.append(f"state_id_invalid:{state_id}")
    if not SAFE_ID_RE.match(str(state.get("trace_id") or "")):
        failures.append(f"state_trace_id_invalid:{state_id}")
    privacy = state.get("privacy") if isinstance(state.get("privacy"), dict) else {}
    required_false_flags = {
        "raw_process_metadata_stored": "state_raw_process_metadata_stored",
        "raw_paths_stored": "state_raw_paths_stored",
        "raw_usernames_stored": "state_raw_usernames_stored",
        "raw_environment_stored": "state_raw_environment_stored",
        "raw_cmdline_stored": "state_raw_cmdline_stored",
    }
    if privacy.get("filtered") is not True:
        failures.append(f"state_privacy_not_filtered:{state_id}")
    if policy.get("local_only_default") is True and privacy.get("local_only") is not True:
        failures.append(f"state_not_local_only:{state_id}")
    for key, failure_key in required_false_flags.items():
        if privacy.get(key) is not False:
            failures.append(f"{failure_key}:{state_id}")
    metrics = state.get("metrics") if isinstance(state.get("metrics"), dict) else {}
    if not metrics:
        failures.append(f"state_metrics_missing:{state_id}")
    allowed_groups = set(_as_string_list(policy.get("allowed_metric_groups")))
    required_groups = set(_as_string_list(policy.get("required_metric_groups")))
    state_groups = set(metrics)
    failures.extend(f"state_metric_group_not_allowed:{state_id}:{item}" for item in sorted(state_groups - allowed_groups))
    failures.extend(f"state_required_metric_group_missing:{state_id}:{item}" for item in sorted(required_groups - state_groups))
    for found in _raw_metadata_keys_in_metrics(metrics, policy):
        failures.append(f"state_raw_metadata_key_present:{state_id}:{found}")
    failures.extend(_metric_value_failures(metrics, policy, state_id))
    return failures


def _filter_case_failures(case: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    case_id = str(case.get("id") or "<missing>")
    filtered = apply_privacy_filter(case.get("input"), policy)
    redactions = filtered["redactions"]
    expected = int(case.get("expected_redaction_count") or 0)
    if len(redactions) < expected:
        failures.append(f"filter_case_redaction_count_low:{case_id}:{len(redactions)}:{expected}")
    forbidden_after = _raw_metadata_keys_in_metrics(filtered["filtered"], policy, path="filtered")
    if forbidden_after:
        failures.extend(f"filter_case_forbidden_key_remaining:{case_id}:{item}" for item in forbidden_after)
    serialized = json.dumps(filtered["filtered"], ensure_ascii=False)
    if policy.get("forbid_raw_paths") is True and PATH_VALUE_RE.search(serialized):
        failures.append(f"filter_case_path_like_value_remaining:{case_id}")
    return failures


def validate_sense_privacy_policy(
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
    failures: List[str] = []
    failures.extend(_policy_failures(payload))

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    state_results: List[Dict[str, Any]] = []
    filter_case_results: List[Dict[str, Any]] = []
    total_redactions = 0

    policy_refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(policy_refs["failures"])
    all_resolved_refs.extend(policy_refs["resolved_refs"])
    all_missing_refs.extend(policy_refs["missing_refs"])
    all_unsafe_refs.extend(policy_refs["unsafe_refs"])

    example_refs = _as_string_list(policy.get("required_example_sets"))
    example_ref_results = _resolve_refs(example_refs, project_root=project, package_root=package, owner="required_example_sets")
    failures.extend(example_ref_results["failures"])
    all_resolved_refs.extend(example_ref_results["resolved_refs"])
    all_missing_refs.extend(example_ref_results["missing_refs"])
    all_unsafe_refs.extend(example_ref_results["unsafe_refs"])

    for item in example_ref_results["resolved_refs"]:
        example_path = Path(item["path"])
        example_set = load_example_set(example_path)
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{item['ref']}")
        states = example_set.get("states") if isinstance(example_set.get("states"), list) else []
        if not states:
            failures.append(f"example_set_states_empty:{item['ref']}")
        for state in states:
            if not isinstance(state, dict):
                failures.append(f"state_not_object:{item['ref']}")
                continue
            state_id = str(state.get("id") or "<missing>")
            state_failures = _state_failures(state, policy)
            refs_result = _resolve_refs(_as_string_list(state.get("refs")), project_root=project, package_root=package, owner=state_id)
            state_failures.extend(refs_result["failures"])
            failures.extend(state_failures)
            all_resolved_refs.extend(refs_result["resolved_refs"])
            all_missing_refs.extend(refs_result["missing_refs"])
            all_unsafe_refs.extend(refs_result["unsafe_refs"])
            state_results.append(
                {
                    "id": state_id,
                    "ok": not state_failures,
                    "metric_groups": sorted((state.get("metrics") or {}).keys()) if isinstance(state.get("metrics"), dict) else [],
                    "failures": sorted(set(state_failures)),
                }
            )
        for case in example_set.get("filter_cases") if isinstance(example_set.get("filter_cases"), list) else []:
            if not isinstance(case, dict):
                failures.append(f"filter_case_not_object:{item['ref']}")
                continue
            case_id = str(case.get("id") or "<missing>")
            case_failures = _filter_case_failures(case, policy)
            filtered = apply_privacy_filter(case.get("input"), policy)
            total_redactions += len(filtered["redactions"])
            failures.extend(case_failures)
            filter_case_results.append(
                {
                    "id": case_id,
                    "ok": not case_failures,
                    "redactions": len(filtered["redactions"]),
                    "failures": sorted(set(case_failures)),
                }
            )

    checks = [
        {"id": "coarse_metrics", "status": "passed" if not any("required_metric_group" in item or "metric_group_not_allowed" in item for item in failures) else "failed"},
        {"id": "privacy_filtered", "status": "passed" if not any("privacy_not_filtered" in item for item in failures) else "failed"},
        {"id": "no_raw_process_metadata", "status": "passed" if not any("raw_process_metadata" in item or "raw_metadata_key" in item for item in failures) else "failed"},
        {
            "id": "no_raw_paths_usernames_env_cmdline",
            "status": "passed"
            if not any(
                any(token in failure for token in ["raw_paths", "raw_usernames", "raw_environment", "raw_cmdline", "path_like"])
                for failure in failures
            )
            else "failed",
        },
        {"id": "filter_cases", "status": "passed" if filter_case_results and not any(not item["ok"] for item in filter_case_results) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "states": len(state_results),
        "passing_states": sum(1 for item in state_results if item["ok"]),
        "filter_cases": len(filter_case_results),
        "passing_filter_cases": sum(1 for item in filter_case_results if item["ok"]),
        "redactions": total_redactions,
        "refs": len(all_resolved_refs) + len(all_missing_refs) + len(all_unsafe_refs),
        "resolved_refs": len(all_resolved_refs),
        "missing_refs": len(all_missing_refs),
        "unsafe_refs": len(all_unsafe_refs),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "policy_path": str(policy_path or ""),
        "project_root": _display_path(project),
        "package_root": _display_path(package),
        "failures": sorted(set(failures)),
        "metrics": metrics,
        "checks": checks,
        "state_results": sorted(state_results, key=lambda item: item["id"]),
        "filter_case_results": sorted(filter_case_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def sense_privacy_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("sense_privacy_report_required")
    status = "passed" if report.get("ok") else "failed"
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": [
            {"id": "pipeline_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "rollback_plan", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "safety_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
        ],
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Sense_State and Privacy_Filter contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/sense-privacy-policy.json",
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

    report = validate_sense_privacy_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "SensePrivacyValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "policy_path": report["policy_path"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
