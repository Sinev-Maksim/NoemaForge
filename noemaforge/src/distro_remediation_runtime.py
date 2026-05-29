#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/distro_remediation_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate distro detection and missing dependency remediation contracts.
Inputs: distro-remediation policy, preflight script, first-launch script and CLI help.
Outputs: JSON-compatible DistroRemediationValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_distro_remediation_runtime.py
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
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set


SRC_DIR = Path(__file__).resolve().parent
API_VERSION = "noemaforge.distro-remediation/v1"
POLICY_KIND = "DistroRemediationPolicy"
REPORT_KIND = "DistroRemediationValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
OS_RELEASE_LINE_RE = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]+)=(?P<value>.*)$")

FAMILY_ALIASES: Mapping[str, Set[str]] = {
    "debian": {"debian", "ubuntu", "linuxmint", "raspbian", "pop"},
    "fedora": {"fedora", "rhel", "centos", "rocky", "almalinux"},
    "arch": {"arch", "manjaro"},
    "suse": {"opensuse", "opensuse-leap", "suse", "sles"},
}
DEFAULT_PACKAGE_MANAGERS = {
    "debian": "apt-get",
    "fedora": "dnf",
    "arch": "pacman",
    "suse": "zypper",
}
DEFAULT_DEPENDENCY_COMMANDS = [
    "jq",
    "curl",
    "git",
    "rsync",
    "python3",
    "bwrap",
    "ffmpeg",
    "v4l2-ctl",
    "cmake",
    "go",
    "findmnt",
    "systemctl",
]
DEFAULT_PACKAGES = {
    "debian": [
        "jq",
        "curl",
        "git",
        "rsync",
        "ca-certificates",
        "procps",
        "findutils",
        "coreutils",
        "util-linux",
        "python3",
        "python3-yaml",
        "python3-venv",
        "bubblewrap",
        "ffmpeg",
        "alsa-utils",
        "pipewire",
        "pipewire-bin",
        "pipewire-audio",
        "wireplumber",
        "v4l-utils",
        "golang-go",
        "build-essential",
        "cmake",
        "ntfs-3g",
    ],
    "fedora": [
        "jq",
        "curl",
        "git",
        "rsync",
        "ca-certificates",
        "procps-ng",
        "findutils",
        "coreutils",
        "util-linux",
        "python3",
        "python3-pyyaml",
        "bubblewrap",
        "ffmpeg",
        "alsa-utils",
        "pipewire",
        "wireplumber",
        "v4l-utils",
        "golang",
        "gcc",
        "gcc-c++",
        "make",
        "cmake",
        "ntfs-3g",
    ],
    "arch": [
        "jq",
        "curl",
        "git",
        "rsync",
        "ca-certificates",
        "procps-ng",
        "findutils",
        "coreutils",
        "util-linux",
        "python",
        "python-yaml",
        "bubblewrap",
        "ffmpeg",
        "alsa-utils",
        "pipewire",
        "wireplumber",
        "v4l-utils",
        "go",
        "base-devel",
        "cmake",
        "ntfs-3g",
    ],
    "suse": [
        "jq",
        "curl",
        "git",
        "rsync",
        "ca-certificates",
        "procps",
        "findutils",
        "coreutils",
        "util-linux",
        "python3",
        "python3-PyYAML",
        "python3-venv",
        "bubblewrap",
        "ffmpeg",
        "alsa-utils",
        "pipewire",
        "wireplumber",
        "v4l-utils",
        "go",
        "gcc",
        "gcc-c++",
        "make",
        "cmake",
        "ntfs-3g",
    ],
}


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


def _unquote_os_release_value(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def parse_os_release(text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = OS_RELEASE_LINE_RE.match(line)
        if match:
            values[match.group("key")] = _unquote_os_release_value(match.group("value"))
    return values


def classify_os_release(text: str) -> Dict[str, str]:
    values = parse_os_release(text)
    tokens = {str(values.get("ID", "")).lower()}
    tokens.update(item.lower() for item in str(values.get("ID_LIKE", "")).split())
    family = "unknown"
    for candidate, aliases in FAMILY_ALIASES.items():
        if tokens.intersection(aliases):
            family = candidate
            break
    manager = DEFAULT_PACKAGE_MANAGERS.get(family, "")
    return {
        "id": values.get("ID", ""),
        "id_like": values.get("ID_LIKE", ""),
        "version_id": values.get("VERSION_ID", ""),
        "codename": values.get("VERSION_CODENAME", ""),
        "pretty_name": values.get("PRETTY_NAME", ""),
        "family": family,
        "package_manager": manager,
    }


def install_command_for_family(family: str, package_manager: str | None = None) -> str:
    manager = package_manager or DEFAULT_PACKAGE_MANAGERS.get(family, "")
    packages = " ".join(DEFAULT_PACKAGES.get(family, []))
    if not manager or not packages:
        return ""
    if manager == "apt-get":
        return f"DEBIAN_FRONTEND=noninteractive apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y {packages}"
    if manager in {"dnf", "yum"}:
        return f"{manager} install -y {packages}"
    if manager == "pacman":
        return f"pacman -Sy --noconfirm {packages}"
    if manager == "zypper":
        return f"zypper --non-interactive refresh && zypper --non-interactive install {packages}"
    return ""


def missing_dependency_commands(available_commands: Iterable[str] | None = None) -> List[str]:
    available = set(available_commands or [])
    return [cmd for cmd in DEFAULT_DEPENDENCY_COMMANDS if cmd not in available]


def build_remediation_plan(os_release_text: str, *, available_commands: Iterable[str] | None = None) -> Dict[str, Any]:
    distro = classify_os_release(os_release_text)
    family = distro["family"]
    manager = distro["package_manager"]
    packages = list(DEFAULT_PACKAGES.get(family, []))
    return {
        "distro": distro,
        "supported": family in DEFAULT_PACKAGES and bool(manager),
        "package_manager": manager,
        "packages": packages,
        "missing_commands": missing_dependency_commands(available_commands),
        "install_command": install_command_for_family(family, manager),
        "apply_gates": [
            "--apply-remediation",
            "--yes-i-understand-package-manager-changes",
            "NOEMAFORGE_ALLOW_PACKAGE_REMEDIATION=1",
            "root privileges",
        ],
    }


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
    if str(policy.get("activation_state") or "") != "distro_detection_missing_dependency_remediation":
        failures.append("policy_activation_state_invalid")
    for key in ["require_docs_and_changelog_refs", "require_no_live_host_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    families = set(_as_string_list(policy.get("supported_families")))
    missing_families = set(DEFAULT_PACKAGES) - families
    if missing_families:
        failures.append(f"policy_supported_families_missing:{','.join(sorted(missing_families))}")
    for key in ["required_dependency_commands", "required_preflight_flags", "required_json_fields", "required_scripts"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def _package_failures(policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    managers = policy.get("package_managers") if isinstance(policy.get("package_managers"), dict) else {}
    packages = policy.get("required_packages") if isinstance(policy.get("required_packages"), dict) else {}
    for family, expected_manager in DEFAULT_PACKAGE_MANAGERS.items():
        local_failures: List[str] = []
        if managers.get(family) != expected_manager:
            local_failures.append(f"manager_mismatch:{family}:{managers.get(family)}")
        package_list = _as_string_list(packages.get(family))
        if not package_list:
            local_failures.append(f"required_packages_empty:{family}")
        for package in ["jq", "curl", "git", "rsync", "bubblewrap", "ffmpeg", "cmake"]:
            if package not in package_list:
                local_failures.append(f"required_package_missing:{family}:{package}")
        failures.extend(local_failures)
        reports.append({"family": family, "manager": managers.get(family, ""), "packages": package_list, "ok": not local_failures, "failures": local_failures})
    return {"failures": failures, "reports": reports}


def _script_failures(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_scripts")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        text = load_text(resolved["path"]) if resolved.get("ok") else ""
        local_failures: List[str] = []
        if not resolved.get("ok"):
            local_failures.append(f"script_missing:{ref}")
        if ref.endswith("noemaforge-trixie-preflight.sh"):
            for token in [
                "noemaforge_detect_distro_family()",
                "noemaforge_package_manager_for_family()",
                "noemaforge_missing_dependency_commands()",
                "--remediation-plan",
                "--apply-remediation",
                "--yes-i-understand-package-manager-changes",
                "NOEMAFORGE_ALLOW_PACKAGE_REMEDIATION",
                "distro_remediation",
                "'distro': {",
                "'remediation': {",
                "'missing_commands'",
                "'install_command'",
            ]:
                if text and token not in text:
                    local_failures.append(f"preflight_token_missing:{token}")
        elif ref.endswith("noemaforge-first-launch.sh"):
            for token in [
                "noemaforge_detect_distro_family()",
                "noemaforge_package_manager_for_family()",
                "noemaforge_packages_for_family()",
                "apt-get",
                "dnf",
                "pacman",
                "zypper",
                "run noemaforge trixie-preflight --remediation-plan",
            ]:
                if text and token not in text:
                    local_failures.append(f"first_launch_token_missing:{token}")
            if text and text.count("command -v apt-get") > 1:
                local_failures.append("first_launch_apt_only_probe_reintroduced")
        elif ref.endswith("bin/noemaforge"):
            if text and "trixie-preflight [--json] [--remediation-plan]" not in text:
                local_failures.append("cli_help_remediation_plan_missing")
        failures.extend(local_failures)
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved})
    return {"failures": failures, "reports": reports}


def validate_distro_remediation_policy(
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
    packages = _package_failures(policy)
    scripts = _script_failures(policy, project_root=project, package_root=package)
    failures.extend(packages["failures"])
    failures.extend(scripts["failures"])
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "supported_families": len(_as_string_list(policy.get("supported_families"))),
        "package_reports": len(packages["reports"]),
        "valid_package_reports": sum(1 for item in packages["reports"] if item.get("ok")),
        "script_reports": len(scripts["reports"]),
        "valid_script_reports": sum(1 for item in scripts["reports"] if item.get("ok")),
        "dependency_commands": len(_as_string_list(policy.get("required_dependency_commands"))),
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
        "packages": packages,
        "scripts": scripts,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "DistroRemediationValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge distro remediation contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "distro-remediation-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_distro_remediation_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
