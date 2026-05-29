#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/machine_local_defaults_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate /etc/default/noemaforge-* machine-local override defaults.
Inputs: machine-local-defaults policy, example default files, installer and systemd unit files.
Outputs: JSON-compatible MachineLocalDefaultsValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_machine_local_defaults_runtime.py
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
from typing import Any, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
API_VERSION = "noemaforge.machine-local-defaults/v1"
POLICY_KIND = "MachineLocalDefaultsPolicy"
REPORT_KIND = "MachineLocalDefaultsValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
ENV_LINE_RE = re.compile(r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$")
SECRET_KEY_RE = re.compile(r"(PASSWORD|SECRET|TOKEN|PRIVATE)", re.IGNORECASE)


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


def _strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_double:
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.strip()


def _unquote_env_value(value: str) -> str:
    text = _strip_inline_comment(value)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def parse_default_env(text: str) -> Dict[str, str]:
    env: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = ENV_LINE_RE.match(line)
        if not match:
            continue
        env[match.group("key")] = _unquote_env_value(match.group("value"))
    return env


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
    if str(policy.get("activation_state") or "") != "etc_default_noemaforge_machine_local_overrides":
        failures.append("policy_activation_state_invalid")
    for key in ["require_docs_and_changelog_refs", "require_no_live_host_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if not isinstance(policy.get("defaults"), list) or not policy.get("defaults"):
        failures.append("policy_defaults_empty")
    if not isinstance(policy.get("required_service_envfiles"), list) or not policy.get("required_service_envfiles"):
        failures.append("policy_required_service_envfiles_empty")
    if not _as_string_list(policy.get("required_installer_targets")):
        failures.append("policy_required_installer_targets_empty")
    return failures


def _default_file_report(default: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    refs = {
        "source": str(default.get("source") or ""),
        "docs": str(default.get("docs") or ""),
        "package_docs": str(default.get("package_docs") or ""),
    }
    resolved = {key: _resolve_ref(ref, project_root=project_root, package_root=package_root) for key, ref in refs.items()}
    for key, item in resolved.items():
        if not item.get("ok"):
            failures.append(f"default_ref_missing:{default.get('name')}:{key}:{refs[key]}")
    texts: Dict[str, str] = {}
    for key, item in resolved.items():
        if item.get("ok"):
            texts[key] = load_text(item["path"])
    if len(texts) == 3 and not (texts["source"] == texts["docs"] == texts["package_docs"]):
        failures.append(f"default_docs_copy_mismatch:{default.get('name')}")
    env = parse_default_env(texts.get("source", ""))
    required = _as_string_list(default.get("required_vars"))
    for var in required:
        if var not in env:
            failures.append(f"default_required_var_missing:{default.get('name')}:{var}")
    for var in _as_string_list(default.get("absolute_path_vars")):
        value = env.get(var, "")
        if value and not value.startswith("/"):
            failures.append(f"default_path_not_absolute:{default.get('name')}:{var}")
    for var in _as_string_list(default.get("numeric_vars")):
        value = env.get(var, "")
        if not value.isdigit():
            failures.append(f"default_numeric_var_invalid:{default.get('name')}:{var}")
    for key, value in env.items():
        if SECRET_KEY_RE.search(key) and value:
            failures.append(f"default_secret_like_value_present:{default.get('name')}:{key}")
    target = str(default.get("target") or "")
    if not target.startswith("/etc/default/noemaforge-"):
        failures.append(f"default_target_invalid:{default.get('name')}:{target}")
    return {
        "name": str(default.get("name") or ""),
        "ok": not failures,
        "target": target,
        "vars": sorted(env),
        "failures": failures,
        "resolved": resolved,
    }


def _service_envfile_reports(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    for item in policy.get("required_service_envfiles", []):
        service = str(item.get("service") or "")
        envfiles = _as_string_list(item.get("envfiles"))
        resolved = _resolve_ref(service, project_root=project_root, package_root=package_root)
        local_failures: List[str] = []
        text = load_text(resolved["path"]) if resolved.get("ok") else ""
        if not resolved.get("ok"):
            local_failures.append(f"service_ref_missing:{service}")
        for envfile in envfiles:
            token = f"EnvironmentFile=-{envfile}"
            if text and token not in text:
                local_failures.append(f"service_envfile_missing:{service}:{envfile}")
        failures.extend(local_failures)
        reports.append({"service": service, "ok": not local_failures, "envfiles": envfiles, "failures": local_failures, "resolved": resolved})
    return {"failures": failures, "reports": reports}


def _installer_report(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    resolved = _resolve_ref("install_noemaforge_0.32.1_mvp.sh", project_root=project_root, package_root=package_root)
    text = load_text(resolved["path"]) if resolved.get("ok") else ""
    if not resolved.get("ok"):
        failures.append("installer_missing")
    if text and "install_default_once()" not in text:
        failures.append("installer_install_default_once_missing")
    if text and "install-default $rel mode=$mode if-missing" not in text:
        failures.append("installer_dry_run_if_missing_message_missing")
    for target in _as_string_list(policy.get("required_installer_targets")):
        if text and target not in text:
            failures.append(f"installer_target_missing:{target}")
        name = target.rsplit("/", 1)[-1]
        example = f'policies/${{default_name}}.example'
        if text and name not in text:
            failures.append(f"installer_default_name_missing:{name}")
        if text and example not in text:
            failures.append("installer_default_example_loop_missing")
    return {"ok": not failures, "failures": failures, "resolved": resolved}


def validate_machine_local_defaults_policy(
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
    default_reports = [_default_file_report(default, project_root=project, package_root=package) for default in policy.get("defaults", []) if isinstance(default, dict)]
    for report in default_reports:
        failures.extend(report["failures"])
    service_report = _service_envfile_reports(policy, project_root=project, package_root=package)
    failures.extend(service_report["failures"])
    installer = _installer_report(policy, project_root=project, package_root=package)
    failures.extend(installer["failures"])
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "defaults": len(default_reports),
        "valid_defaults": sum(1 for item in default_reports if item.get("ok")),
        "services": len(service_report["reports"]),
        "valid_services": sum(1 for item in service_report["reports"] if item.get("ok")),
        "installer_targets": len(_as_string_list(policy.get("required_installer_targets"))),
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
        "defaults": default_reports,
        "services": service_report,
        "installer": installer,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "MachineLocalDefaultsValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge machine-local default examples")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "machine-local-defaults-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_machine_local_defaults_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
