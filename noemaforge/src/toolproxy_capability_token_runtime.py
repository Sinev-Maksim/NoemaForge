#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/toolproxy_capability_token_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate ToolProxy capability-token issuance UX contracts.
Inputs: noemaforge/configs/toolproxy-capability-token-policy.json and capability-token examples.
Outputs: JSON-compatible ToolProxyCapabilityTokenValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_toolproxy_capability_token_runtime.py
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
from typing import Any, Dict, List, Optional, Sequence, Set


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import noemaforge_toolproxy_diag as diag
import unified_registry_runtime as urr


API_VERSION = "noemaforge.toolproxy-capability/v1"
POLICY_KIND = "ToolProxyCapabilityTokenPolicy"
SET_KIND = "ToolProxyCapabilityTokenExampleSet"
REPORT_KIND = "ToolProxyCapabilityTokenValidationReport"

VALID_POLICY_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_UX_COMMANDS = {"issue", "list", "verify", "revoke", "smoke"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,180}$")
SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


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


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def load_example_set(example_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(example_path).read_text(encoding="utf-8"))


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if not SAFE_ID_RE.match(str(payload.get("id") or "")):
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_POLICY_STATUSES:
        failures.append("policy_status_invalid")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if str(policy.get("activation_state") or "") != "capability_token_issuance_ux":
        failures.append("policy_activation_state_invalid")
    for key in [
        "require_trace_id",
        "require_registry_attachment",
        "require_policy_schema_runtime_tests",
        "require_docs_and_changelog_refs",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if not str(policy.get("required_tool_policy_ref") or "").startswith("tool-policy:"):
        failures.append("policy_required_tool_policy_ref_invalid")
    if not {"src/caps.py", "src/noemaforge_toolproxy_diag.py", "contracts/capability_token.schema.json"}.issubset(set(_as_string_list(policy.get("required_runtime_refs")))):
        failures.append("policy_required_runtime_refs_missing")
    if not REQUIRED_UX_COMMANDS.issubset(set(_as_string_list(policy.get("required_ux_commands")))):
        failures.append("policy_required_ux_commands_missing")
    controls = policy.get("token_controls") if isinstance(policy.get("token_controls"), dict) else {}
    for key in [
        "short_lived_required",
        "default_secret_redaction",
        "full_secret_requires_explicit_flag",
        "secret_sha256_required",
        "epoch_binding_required",
        "issued_to_binding_required",
        "live_llm_optional",
        "offline_smoke_required",
        "revoke_moves_to_revoked",
    ]:
        if controls.get(key) is not True:
            failures.append(f"policy_token_{key}_not_true")
    if controls.get("persisted_secret_plaintext_allowed") is not False:
        failures.append("policy_token_persisted_secret_plaintext_allowed_not_false")
    if int(controls.get("max_default_ttl_sec") or 0) <= 0 or int(controls.get("max_default_ttl_sec") or 0) > 600:
        failures.append("policy_token_max_default_ttl_sec_invalid")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _registry_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures = [f"registry_invalid:{item}" for item in report.get("failures", [])]
    entries = {
        _registry_ref(entry): entry
        for entry in report.get("normalized_registry", {}).get("entries", [])
        if isinstance(entry, dict)
    }
    raw_entries = {
        _registry_ref(entry): entry
        for entry in registry.get("entries", [])
        if isinstance(entry, dict)
    }
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    eval_entry = entries.get(eval_ref)
    if not eval_entry:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    else:
        entry_refs = set(_as_string_list(eval_entry.get("refs")))
        for ref in [
            "configs/toolproxy-capability-token-policy.json",
            "contracts/toolproxy_capability_token.schema.json",
            "contracts/capability_token.schema.json",
            "src/caps.py",
            "src/noemaforge_toolproxy_diag.py",
            "src/toolproxy_capability_token_runtime.py",
            "tests/test_toolproxy_capability_token_runtime.py",
        ]:
            if ref not in entry_refs:
                failures.append(f"registry_eval_pack_ref_missing:{eval_ref}:{ref}")

    tool_policy_ref = str(policy.get("required_tool_policy_ref") or "")
    tool_policy = raw_entries.get(tool_policy_ref) or entries.get(tool_policy_ref)
    if not tool_policy:
        failures.append(f"registry_tool_policy_missing:{tool_policy_ref}")
        tool_eval_refs: List[str] = []
        tool_refs: List[str] = []
    else:
        tool_eval_refs = _as_string_list(tool_policy.get("eval_pack_refs"))
        tool_refs = _as_string_list(tool_policy.get("refs"))
    if eval_ref not in tool_eval_refs:
        failures.append(f"registry_tool_policy_eval_pack_missing:{eval_ref}")
    for ref in [
        "configs/toolproxy-capability-token-policy.json",
        "contracts/capability_token.schema.json",
        "src/caps.py",
        "src/noemaforge_toolproxy_diag.py",
        "src/toolproxy_capability_token_runtime.py",
    ]:
        if ref not in tool_refs:
            failures.append(f"registry_tool_policy_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "entries": entries, "tool_eval_refs": tool_eval_refs}


def _flow_failures(flow: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    controls = _policy_dict(policy_payload).get("token_controls") or {}
    failures: List[str] = []
    flow_id = str(flow.get("id") or "<missing>")
    if not SAFE_ID_RE.match(flow_id):
        failures.append(f"flow_id_invalid:{flow_id}")
    if _policy_dict(policy_payload).get("require_trace_id") is True and not SAFE_ID_RE.match(str(flow.get("trace_id") or "")):
        failures.append(f"flow_trace_id_invalid:{flow_id}")
    commands = set(_as_string_list(flow.get("commands")))
    if not REQUIRED_UX_COMMANDS.issubset(commands):
        failures.append(f"flow_required_ux_commands_missing:{flow_id}")
    issue = flow.get("issue") if isinstance(flow.get("issue"), dict) else {}
    if int(issue.get("ttl_sec") or 0) <= 0 or int(issue.get("ttl_sec") or 0) > int(controls.get("max_default_ttl_sec") or 600):
        failures.append(f"flow_issue_ttl_invalid:{flow_id}:{issue.get('ttl_sec')}")
    if controls.get("default_secret_redaction") is True and issue.get("redacted_output") is not True:
        failures.append(f"flow_issue_redaction_missing:{flow_id}")
    if controls.get("full_secret_requires_explicit_flag") is True and issue.get("show_secret") is not False:
        failures.append(f"flow_issue_show_secret_not_false:{flow_id}")
    token_output = str(issue.get("token_output") or "")
    if not token_output.endswith(".***"):
        failures.append(f"flow_issue_token_not_redacted:{flow_id}")
    issued_to = issue.get("issued_to") if isinstance(issue.get("issued_to"), dict) else {}
    for key in ["role", "project_id", "run_id"]:
        if not str(issued_to.get(key) or "").strip():
            failures.append(f"flow_issue_issued_to_{key}_missing:{flow_id}")

    record = flow.get("record") if isinstance(flow.get("record"), dict) else {}
    if controls.get("persisted_secret_plaintext_allowed") is False and "secret" in record:
        failures.append(f"flow_record_plaintext_secret:{flow_id}")
    if controls.get("secret_sha256_required") is True and not SHA256_RE.match(str(record.get("secret_sha256") or "")):
        failures.append(f"flow_record_secret_sha256_invalid:{flow_id}")
    if controls.get("epoch_binding_required") is True and not str(record.get("epoch_id") or "").strip():
        failures.append(f"flow_record_epoch_missing:{flow_id}")
    rec_issued_to = record.get("issued_to") if isinstance(record.get("issued_to"), dict) else {}
    if controls.get("issued_to_binding_required") is True:
        for key in ["role", "project_id", "run_id"]:
            if not str(rec_issued_to.get(key) or "").strip():
                failures.append(f"flow_record_issued_to_{key}_missing:{flow_id}")
    if not _as_string_list([cap.get("action") for cap in record.get("caps") or [] if isinstance(cap, dict)]):
        failures.append(f"flow_record_caps_empty:{flow_id}")
    if str(record.get("trace_id") or "") != str(flow.get("trace_id") or ""):
        failures.append(f"flow_record_trace_mismatch:{flow_id}")
    if flow.get("verify", {}).get("ok") is not True or flow.get("verify", {}).get("reason") != "ok":
        failures.append(f"flow_verify_not_ok:{flow_id}")
    if flow.get("revoke", {}).get("ok") is not True:
        failures.append(f"flow_revoke_not_ok:{flow_id}")
    if controls.get("revoke_moves_to_revoked") is True and flow.get("revoke", {}).get("moves_to_revoked") is not True:
        failures.append(f"flow_revoke_not_moved:{flow_id}")
    if flow.get("post_revoke_verify", {}).get("ok") is not False:
        failures.append(f"flow_post_revoke_verify_not_false:{flow_id}")
    smoke = flow.get("smoke") if isinstance(flow.get("smoke"), dict) else {}
    if controls.get("live_llm_optional") is True and smoke.get("live_llm_required") is not False:
        failures.append(f"flow_live_llm_required:{flow_id}")
    if controls.get("offline_smoke_required") is True and smoke.get("offline_issue_verify_required") is not True:
        failures.append(f"flow_offline_smoke_missing:{flow_id}")
    return failures


def validate_toolproxy_capability_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Optional[Path | str] = None,
    registry_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root)
    if not project.exists():
        raise FileNotFoundError(project)
    if not package.exists():
        raise FileNotFoundError(package)
    registry = _as_path(registry_path) if registry_path else package / "configs" / "unified-registry.json"

    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    registry_result = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_result["failures"])

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    flow_results: List[Dict[str, Any]] = []

    refs_to_resolve = sorted(set(_as_string_list(payload.get("refs")) + _as_string_list(policy.get("required_runtime_refs"))))
    refs_result = _resolve_refs(refs_to_resolve, project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(refs_result["failures"])
    all_resolved_refs.extend(refs_result["resolved_refs"])
    all_missing_refs.extend(refs_result["missing_refs"])
    all_unsafe_refs.extend(refs_result["unsafe_refs"])

    example_ref_results = _resolve_refs(_as_string_list(policy.get("required_example_sets")), project_root=project, package_root=package, owner="required_example_sets")
    failures.extend(example_ref_results["failures"])
    all_resolved_refs.extend(example_ref_results["resolved_refs"])
    all_missing_refs.extend(example_ref_results["missing_refs"])
    all_unsafe_refs.extend(example_ref_results["unsafe_refs"])

    for ref_item in example_ref_results["resolved_refs"]:
        example_set = load_example_set(Path(ref_item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{ref_item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{ref_item['ref']}")
        flows = example_set.get("flows") if isinstance(example_set.get("flows"), list) else []
        if not flows:
            failures.append(f"example_set_flows_empty:{ref_item['ref']}")
        for flow in flows:
            if not isinstance(flow, dict):
                failures.append(f"flow_not_object:{ref_item['ref']}")
                continue
            flow_id = str(flow.get("id") or "<missing>")
            flow_failures = _flow_failures(flow, payload)
            failures.extend(flow_failures)
            flow_ref_result = _resolve_refs(_as_string_list(flow.get("refs")), project_root=project, package_root=package, owner=flow_id)
            failures.extend(flow_ref_result["failures"])
            all_resolved_refs.extend(flow_ref_result["resolved_refs"])
            all_missing_refs.extend(flow_ref_result["missing_refs"])
            all_unsafe_refs.extend(flow_ref_result["unsafe_refs"])
            flow_results.append(
                {
                    "id": flow_id,
                    "ok": not flow_failures,
                    "commands": len(_as_string_list(flow.get("commands"))),
                    "failures": sorted(set(flow_failures)),
                }
            )

    checks = [
        {"id": "issue_list_verify_revoke_smoke", "status": "passed" if not any("ux_commands" in item for item in failures) else "failed"},
        {"id": "secret_redaction", "status": "passed" if not any("redaction" in item or "token_not_redacted" in item or "show_secret" in item for item in failures) else "failed"},
        {"id": "sha256_only_persistence", "status": "passed" if not any("secret" in item and "redaction" not in item for item in failures) else "failed"},
        {"id": "epoch_and_issued_to_binding", "status": "passed" if not any("epoch" in item or "issued_to" in item for item in failures) else "failed"},
        {"id": "offline_smoke", "status": "passed" if not any("smoke" in item or "live_llm_required" in item for item in failures) else "failed"},
        {"id": "registry_attachment", "status": "passed" if not any("registry_" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "flows": len(flow_results),
        "passing_flows": sum(1 for item in flow_results if item["ok"]),
        "required_ux_commands": len(_as_string_list(policy.get("required_ux_commands"))),
        "registry_entries": len(registry_result["entries"]),
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
        "registry_path": _display_path(registry),
        "project_root": _display_path(project),
        "package_root": _display_path(package),
        "failures": sorted(set(failures)),
        "metrics": metrics,
        "checks": checks,
        "flow_results": sorted(flow_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def run_offline_token_cycle(tokens_dir: str, *, action: str = "llm.chat", ttl_sec: int = 120) -> Dict[str, Any]:
    token = diag.issue_token_value(
        tokens_dir,
        action,
        ttl_sec,
        role="operator",
        project_id="noemaforge-toolproxy-smoke",
        run_id="smoke",
        trace_id="trace:toolproxy:offline-smoke",
    )
    token_id = token.split(".", 1)[0]
    listing = diag.token_list(tokens_dir)
    verify = diag.token_verify(tokens_dir, token)
    revoke = diag.token_revoke(tokens_dir, token_id)
    post_revoke_verify = diag.token_verify(tokens_dir, token)
    return {
        "ok": bool(verify.get("ok")) and bool(revoke.get("ok")) and post_revoke_verify.get("ok") is False,
        "token_id": token_id,
        "token_redacted": token_id + ".***",
        "listing": listing,
        "verify": verify,
        "revoke": revoke,
        "post_revoke_verify": post_revoke_verify,
    }


def toolproxy_capability_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("toolproxy_capability_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge ToolProxy capability-token UX contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/toolproxy-capability-token-policy.json",
        help="Policy path, absolute or relative to project root.",
    )
    parser.add_argument("--registry", default="", help="Optional Unified Registry path.")
    parser.add_argument("--summary", action="store_true", help="Emit a compact validation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = _as_path(args.project_root)
    package_root = _as_path(args.package_root) if args.package_root else project_root / "noemaforge"
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = project_root / policy_path
    registry_path = Path(args.registry) if args.registry else package_root / "configs" / "unified-registry.json"
    if not registry_path.is_absolute():
        registry_path = project_root / registry_path

    report = validate_toolproxy_capability_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "ToolProxyCapabilityTokenValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "policy_path": report["policy_path"],
            "registry_path": report["registry_path"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
