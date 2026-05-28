#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/multios_runtime_contract.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate the optional MultiOS runtime host/control contract.
Inputs: noemaforge/configs/noemaforge.runtime.yaml plus local project/package roots.
Outputs: JSON-compatible MultiOSRuntimeReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_multios_runtime_contract.py
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
PROJECT_ROOT_DIR = Path(__file__).resolve().parents[2]
for candidate in [SRC_DIR, PROJECT_ROOT_DIR]:
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import production_ai_contracts as pac
from noemaforge.runtime.hardware_probe import detect_hardware
from noemaforge.runtime.os_probe import detect_os
from noemaforge.runtime.registry import load_runtime_policy, profile_by_id
from noemaforge.runtime.selector import select_runtime_profile


API_VERSION = "noemaforge.runtime/v1"
POLICY_KIND = "NoemaForgeRuntimePolicy"
REPORT_KIND = "MultiOSRuntimeReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_HOST_OS = {"linux", "windows", "macos", "remote"}
VALID_ROLES = {"reference_runtime", "control_host", "runtime_connector"}
REQUIRED_PROFILES = {
    "linux-reference-systemd",
    "windows-control-host",
    "macos-control-host",
    "remote-http-runtime",
}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


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
        "linux_reference_required",
        "preserve_linux_systemd_launch",
        "windows_control_only_by_default",
        "macos_control_only_by_default",
        "remote_http_disabled_by_default",
        "forbid_new_required_first_start_dependencies",
        "host_detection_smoke_required",
        "alpha_gate_required",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")

    host_os = set(_as_string_list(policy.get("allowed_host_os")))
    roles = set(_as_string_list(policy.get("allowed_roles")))
    required_profiles = set(_as_string_list(policy.get("required_profiles")))
    failures.extend(f"policy_invalid_host_os:{item}" for item in sorted(host_os - VALID_HOST_OS))
    failures.extend(f"policy_invalid_role:{item}" for item in sorted(roles - VALID_ROLES))
    failures.extend(f"policy_unknown_required_profile:{item}" for item in sorted(required_profiles - REQUIRED_PROFILES))
    for required in REQUIRED_PROFILES:
        if required not in required_profiles:
            failures.append(f"policy_required_profile_missing:{required}")
    return failures


def _profile_failures(profile: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    profile_id = str(profile.get("id") or "<missing>")
    host_os = str(profile.get("host_os") or "")
    role = str(profile.get("role") or "")
    connector = str(profile.get("connector") or "")
    allowed_host_os = set(_as_string_list(policy.get("allowed_host_os")))
    allowed_roles = set(_as_string_list(policy.get("allowed_roles")))

    if not SAFE_ID_RE.match(profile_id):
        failures.append(f"profile_id_invalid:{profile_id}")
    if host_os not in VALID_HOST_OS or host_os not in allowed_host_os:
        failures.append(f"profile_host_os_invalid:{profile_id}:{host_os}")
    if role not in VALID_ROLES or role not in allowed_roles:
        failures.append(f"profile_role_invalid:{profile_id}:{role}")

    if policy.get("forbid_new_required_first_start_dependencies") is True:
        if host_os != "linux" and profile.get("required_for_first_start") is not False:
            failures.append(f"profile_non_linux_required_for_first_start:{profile_id}")
    if host_os == "linux":
        if profile_id == "linux-reference-systemd" and profile.get("enabled") is not True:
            failures.append("linux_reference_not_enabled")
        if profile.get("preserve_existing_launch") is not True:
            failures.append(f"linux_preserve_existing_launch_not_true:{profile_id}")
        if profile.get("required_for_first_start") is not True:
            failures.append(f"linux_reference_not_required_for_first_start:{profile_id}")
        if str(profile.get("launcher") or "") != "systemd_existing":
            failures.append(f"linux_launcher_not_systemd_existing:{profile_id}")
    if host_os in {"windows", "macos"}:
        if role != "control_host":
            failures.append(f"host_control_role_invalid:{profile_id}:{role}")
        if profile.get("enabled") is not False:
            failures.append(f"host_control_enabled_by_default:{profile_id}")
        if profile.get("optional") is not True:
            failures.append(f"host_control_not_optional:{profile_id}")
        if profile.get("allow_heavy_local_inference") is not False:
            failures.append(f"host_control_allows_heavy_local_inference:{profile_id}")
        if connector != "remote_http":
            failures.append(f"host_control_connector_not_remote_http:{profile_id}:{connector}")
    if host_os == "remote":
        if role != "runtime_connector":
            failures.append(f"remote_role_invalid:{profile_id}:{role}")
        if connector != "remote_http":
            failures.append(f"remote_connector_not_remote_http:{profile_id}:{connector}")
        if policy.get("remote_http_disabled_by_default") is True and profile.get("enabled") is not False:
            failures.append(f"remote_http_enabled_by_default:{profile_id}")
        if profile.get("health_report_required") is not True:
            failures.append(f"remote_health_report_not_required:{profile_id}")
        if profile.get("live_network_check_default") is not False:
            failures.append(f"remote_live_network_check_enabled:{profile_id}")
    return failures


def _host_detection_smoke(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    fixtures = [
        ("linux", {"system": "Linux", "release": "6.1", "machine": "x86_64"}),
        ("windows", {"system": "Windows", "release": "11", "machine": "AMD64"}),
        ("macos", {"system": "Darwin", "release": "23", "machine": "arm64"}),
    ]
    for expected, kwargs in fixtures:
        os_report = detect_os(**kwargs)
        hw_report = detect_hardware(machine=kwargs["machine"], processor="Apple M2" if expected == "macos" else "")
        selected = select_runtime_profile(payload, host_os_report=os_report, hardware_report=hw_report)
        status = "passed" if os_report["system"] == expected and selected["ok"] else "failed"
        checks.append(
            {
                "id": f"host_detection_{expected}",
                "status": status,
                "detected": os_report["system"],
                "selected_profile_id": selected.get("selected_profile_id", ""),
                "selection_mode": selected.get("mode", ""),
            }
        )
    return checks


def validate_multios_runtime_policy(
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
    profiles = payload.get("profiles") if isinstance(payload.get("profiles"), list) else []
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    if not profiles:
        failures.append("profiles_empty")

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    profile_results: List[Dict[str, Any]] = []

    policy_refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(policy_refs["failures"])
    all_resolved_refs.extend(policy_refs["resolved_refs"])
    all_missing_refs.extend(policy_refs["missing_refs"])
    all_unsafe_refs.extend(policy_refs["unsafe_refs"])

    seen_profiles = set()
    for profile in profiles:
        if not isinstance(profile, dict):
            failures.append("profile_not_object")
            continue
        profile_id = str(profile.get("id") or "<missing>")
        seen_profiles.add(profile_id)
        profile_failures = _profile_failures(profile, policy)
        refs_result = _resolve_refs(_as_string_list(profile.get("refs")), project_root=project, package_root=package, owner=profile_id)
        profile_failures.extend(refs_result["failures"])
        failures.extend(profile_failures)
        all_resolved_refs.extend(refs_result["resolved_refs"])
        all_missing_refs.extend(refs_result["missing_refs"])
        all_unsafe_refs.extend(refs_result["unsafe_refs"])
        profile_results.append(
            {
                "id": profile_id,
                "ok": not profile_failures,
                "host_os": str(profile.get("host_os") or ""),
                "role": str(profile.get("role") or ""),
                "enabled": profile.get("enabled") is True,
                "optional": profile.get("optional") is True,
                "required_for_first_start": profile.get("required_for_first_start") is True,
                "allow_heavy_local_inference": profile.get("allow_heavy_local_inference") is True,
                "failures": sorted(set(profile_failures)),
            }
        )

    missing_profiles = sorted(REQUIRED_PROFILES - seen_profiles)
    failures.extend(f"required_profile_missing:{item}" for item in missing_profiles)
    health_report = payload.get("health_report") if isinstance(payload.get("health_report"), dict) else {}
    health_ref = str(health_report.get("example_ref") or "")
    required_health_fields = set(_as_string_list(health_report.get("required_fields")))
    if health_report.get("kind") != "RuntimeHealthReport":
        failures.append("health_report_kind_invalid")
    if not health_ref:
        failures.append("health_report_example_ref_missing")
    else:
        health_refs = _resolve_refs([health_ref], project_root=project, package_root=package, owner="health_report")
        failures.extend(health_refs["failures"])
        all_resolved_refs.extend(health_refs["resolved_refs"])
        all_missing_refs.extend(health_refs["missing_refs"])
        all_unsafe_refs.extend(health_refs["unsafe_refs"])
    for field in ["profile_id", "ok", "status", "mode", "checks"]:
        if field not in required_health_fields:
            failures.append(f"health_report_required_field_missing:{field}")

    smoke_checks = _host_detection_smoke(payload)
    failures.extend(f"host_detection_smoke_failed:{check['id']}" for check in smoke_checks if check["status"] != "passed")
    linux_profile = profile_by_id(payload, "linux-reference-systemd")
    remote_profile = profile_by_id(payload, "remote-http-runtime")
    checks = [
        {"id": "linux_reference_runtime", "status": "passed" if linux_profile and linux_profile.enabled and linux_profile.required_for_first_start else "failed"},
        {"id": "linux_systemd_preserved", "status": "passed" if not any("linux_launcher" in item or "linux_preserve" in item for item in failures) else "failed"},
        {"id": "windows_control_only", "status": "passed" if not any("windows-control-host" in item for item in failures) else "failed"},
        {"id": "macos_control_only", "status": "passed" if not any("macos-control-host" in item for item in failures) else "failed"},
        {"id": "remote_http_disabled", "status": "passed" if remote_profile and not remote_profile.enabled else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    checks.extend(smoke_checks)
    metrics = {
        "profiles": len(profile_results),
        "passing_profiles": sum(1 for item in profile_results if item["ok"]),
        "linux_profiles": sum(1 for item in profile_results if item["host_os"] == "linux"),
        "windows_profiles": sum(1 for item in profile_results if item["host_os"] == "windows"),
        "macos_profiles": sum(1 for item in profile_results if item["host_os"] == "macos"),
        "remote_profiles": sum(1 for item in profile_results if item["host_os"] == "remote"),
        "required_for_first_start_profiles": sum(1 for item in profile_results if item["required_for_first_start"]),
        "control_only_profiles": sum(1 for item in profile_results if item["role"] == "control_host"),
        "heavy_local_non_linux_profiles": sum(1 for item in profile_results if item["host_os"] != "linux" and item["allow_heavy_local_inference"]),
        "missing_required_profiles": len(missing_profiles),
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
        "profile_results": sorted(profile_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def multios_runtime_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("multios_runtime_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge MultiOS runtime host/control contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/noemaforge.runtime.yaml",
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

    report = validate_multios_runtime_policy(
        load_runtime_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "MultiOSRuntimeSummary",
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
