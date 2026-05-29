#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/mcp_adapter_registry_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate MCP adapter registry safety boundaries before adapter exposure.
Inputs: noemaforge/configs/mcp-adapter-registry.json plus local project/package roots.
Outputs: JSON-compatible MCPAdapterRegistryValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_mcp_adapter_registry_runtime.py
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
from typing import Any, Dict, Iterable, List, Optional, Sequence


CONFIG_API_VERSION = "noemaforge.mcp-adapter-registry/v1"
CONFIG_KIND = "MCPAdapterRegistry"
VALIDATION_KIND = "MCPAdapterRegistryValidationReport"

VALID_STATES = {"disabled", "shadow", "canary", "enabled", "retired"}
VALID_TRANSPORTS = {"stdio", "unix_socket", "tcp", "http", "websocket"}
NETWORK_TRANSPORTS = {"tcp", "http", "websocket"}
RISK_LEVELS = {"low": 1, "medium": 2, "high": 3, "critical": 4}

_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,119}$")
_SAFE_SCOPE_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,80}$")
_REGISTRY_REF_RE = re.compile(r"^[a-z-]+:[A-Za-z0-9_.:-]+:[A-Za-z0-9_.:-]+$")


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
    if not text:
        return False
    if text.startswith("/") or text.startswith("~"):
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


def load_registry(registry_path: Path | str) -> Dict[str, Any]:
    path = Path(registry_path)
    return json.loads(path.read_text(encoding="utf-8"))


def _empty_report(
    *,
    project_root: Path,
    package_root: Path,
    registry_path: Path | str,
    failures: Iterable[str],
) -> Dict[str, Any]:
    failure_list = sorted(set(str(item) for item in failures))
    return {
        "apiVersion": CONFIG_API_VERSION,
        "kind": VALIDATION_KIND,
        "ok": False,
        "created_at": _nowz(),
        "registry_path": str(registry_path or ""),
        "project_root": _display_path(project_root),
        "package_root": _display_path(package_root),
        "failures": failure_list,
        "metrics": {
            "adapters": 0,
            "disabled_adapters": 0,
            "active_adapters": 0,
            "refs": 0,
            "resolved_refs": 0,
            "missing_refs": 0,
            "unsafe_refs": 0,
        },
        "adapter_results": [],
    }


def _policy_failure_checks(policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    if str(policy.get("default_state") or "") != "disabled":
        failures.append("policy_default_state_not_disabled")
    if str(policy.get("default_network") or "") != "deny":
        failures.append("policy_default_network_not_deny")
    for key in [
        "require_trace_id",
        "require_capability_token",
        "require_registry_entry",
        "require_operator_review_for_enable",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")

    allowed = set(_as_string_list(policy.get("allowed_transports")))
    blocked = set(_as_string_list(policy.get("blocked_transports")))
    if not allowed:
        failures.append("policy_allowed_transports_empty")
    invalid_allowed = sorted(allowed - VALID_TRANSPORTS)
    invalid_blocked = sorted(blocked - VALID_TRANSPORTS)
    failures.extend(f"policy_invalid_allowed_transport:{item}" for item in invalid_allowed)
    failures.extend(f"policy_invalid_blocked_transport:{item}" for item in invalid_blocked)
    overlap = sorted(allowed & blocked)
    failures.extend(f"policy_transport_allowed_and_blocked:{item}" for item in overlap)
    for transport in sorted(NETWORK_TRANSPORTS):
        if transport not in blocked:
            failures.append(f"policy_network_transport_not_blocked:{transport}")

    max_risk = str(policy.get("max_tool_risk") or "")
    if max_risk not in RISK_LEVELS:
        failures.append(f"policy_invalid_max_tool_risk:{max_risk}")
    return failures


def _adapter_failure_checks(adapter: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    adapter_id = str(adapter.get("id") or "").strip()
    owner = adapter_id or "<missing>"
    if not _SAFE_ID_RE.match(adapter_id):
        failures.append(f"adapter_id_invalid:{owner}")

    state = str(adapter.get("state") or policy.get("default_state") or "").strip()
    if state not in VALID_STATES:
        failures.append(f"adapter_invalid_state:{owner}:{state}")

    transport = str(adapter.get("transport") or "").strip()
    allowed = set(_as_string_list(policy.get("allowed_transports")))
    blocked = set(_as_string_list(policy.get("blocked_transports")))
    if transport not in VALID_TRANSPORTS:
        failures.append(f"adapter_invalid_transport:{owner}:{transport}")
    if transport in blocked:
        failures.append(f"adapter_transport_blocked:{owner}:{transport}")
    if allowed and transport not in allowed:
        failures.append(f"adapter_transport_not_allowed:{owner}:{transport}")

    risk = str(adapter.get("risk") or "").strip()
    max_risk = str(policy.get("max_tool_risk") or "")
    if risk not in RISK_LEVELS:
        failures.append(f"adapter_invalid_risk:{owner}:{risk}")
    elif max_risk in RISK_LEVELS and RISK_LEVELS[risk] > RISK_LEVELS[max_risk]:
        failures.append(f"adapter_risk_exceeds_policy:{owner}:{risk}>{max_risk}")

    if str(adapter.get("network") or "").strip() != "deny":
        failures.append(f"adapter_network_not_deny:{owner}")

    scopes = _as_string_list(adapter.get("capability_scopes"))
    if not scopes:
        failures.append(f"adapter_capability_scopes_empty:{owner}")
    for scope in scopes:
        if not _SAFE_SCOPE_RE.match(scope):
            failures.append(f"adapter_capability_scope_invalid:{owner}:{scope}")
    if len(scopes) != len(set(scopes)):
        failures.append(f"adapter_capability_scopes_duplicate:{owner}")

    tools = _as_string_list(adapter.get("tool_allowlist"))
    if not tools:
        failures.append(f"adapter_tool_allowlist_empty:{owner}")
    for tool_name in tools:
        if not _SAFE_SCOPE_RE.match(tool_name):
            failures.append(f"adapter_tool_allowlist_invalid:{owner}:{tool_name}")

    if policy.get("require_trace_id") is True and adapter.get("trace_required") is not True:
        failures.append(f"adapter_trace_not_required:{owner}")
    if policy.get("require_capability_token") is True and adapter.get("capability_token_required") is not True:
        failures.append(f"adapter_capability_token_not_required:{owner}")
    if policy.get("require_registry_entry") is True:
        if adapter.get("registry_entry_required") is not True:
            failures.append(f"adapter_registry_entry_not_required:{owner}")
        registry_ref = str(adapter.get("registry_ref") or "").strip()
        if not _REGISTRY_REF_RE.match(registry_ref):
            failures.append(f"adapter_registry_ref_invalid:{owner}:{registry_ref}")

    if adapter.get("audit_logging") is not True:
        failures.append(f"adapter_audit_logging_not_required:{owner}")

    sandbox = adapter.get("sandbox") if isinstance(adapter.get("sandbox"), dict) else {}
    if not sandbox:
        failures.append(f"adapter_sandbox_missing:{owner}")
    if sandbox.get("write") is not False:
        failures.append(f"adapter_sandbox_write_not_false:{owner}")
    if str(sandbox.get("egress") or "").strip() != "deny":
        failures.append(f"adapter_sandbox_egress_not_deny:{owner}")
    if not str(sandbox.get("profile") or "").strip():
        failures.append(f"adapter_sandbox_profile_missing:{owner}")

    review = adapter.get("review") if isinstance(adapter.get("review"), dict) else {}
    if policy.get("require_operator_review_for_enable") is True:
        if review.get("required") is not True:
            failures.append(f"adapter_review_not_required:{owner}")
        if not str(review.get("route") or "").strip():
            failures.append(f"adapter_review_route_missing:{owner}")
        if not _as_string_list(review.get("reviewers")):
            failures.append(f"adapter_reviewers_missing:{owner}")

    rollback_plan = str(adapter.get("rollback_plan") or "").strip()
    if len(rollback_plan) < 20:
        failures.append(f"adapter_rollback_plan_missing:{owner}")

    if state in {"shadow", "canary", "enabled"}:
        if review.get("required") is not True:
            failures.append(f"adapter_active_without_review:{owner}")
        if adapter.get("trace_required") is not True:
            failures.append(f"adapter_active_without_trace:{owner}")
        if adapter.get("capability_token_required") is not True:
            failures.append(f"adapter_active_without_capability_token:{owner}")
        if str(adapter.get("network") or "").strip() != "deny":
            failures.append(f"adapter_active_network_not_denied:{owner}")

    return failures


def validate_mcp_adapter_registry(
    registry: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Optional[Path | str] = None,
    registry_path: Path | str = "",
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root or (project / "noemaforge"))

    if not isinstance(registry, dict):
        return _empty_report(
            project_root=project,
            package_root=package,
            registry_path=registry_path,
            failures=["registry_payload_not_object"],
        )

    failures: List[str] = []
    if registry.get("apiVersion") != CONFIG_API_VERSION:
        failures.append(f"registry_api_version_invalid:{registry.get('apiVersion')}")
    if registry.get("kind") != CONFIG_KIND:
        failures.append(f"registry_kind_invalid:{registry.get('kind')}")
    registry_id = str(registry.get("id") or "").strip()
    if not _SAFE_ID_RE.match(registry_id):
        failures.append(f"registry_id_invalid:{registry_id}")

    policy = registry.get("policy") if isinstance(registry.get("policy"), dict) else {}
    if not policy:
        failures.append("policy_missing")
    failures.extend(_policy_failure_checks(policy))

    adapters = registry.get("adapters") if isinstance(registry.get("adapters"), list) else []
    if not adapters:
        failures.append("adapters_empty")

    seen_ids: set[str] = set()
    adapter_results: List[Dict[str, Any]] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    state_counts: Dict[str, int] = {}

    for idx, raw_adapter in enumerate(adapters):
        adapter = raw_adapter if isinstance(raw_adapter, dict) else {}
        adapter_id = str(adapter.get("id") or f"<index:{idx}>").strip()
        adapter_failures = _adapter_failure_checks(adapter, policy)
        if adapter_id in seen_ids:
            adapter_failures.append(f"adapter_duplicate_id:{adapter_id}")
        seen_ids.add(adapter_id)

        state = str(adapter.get("state") or policy.get("default_state") or "").strip()
        state_counts[state] = state_counts.get(state, 0) + 1

        adapter_resolved_refs: List[Dict[str, Any]] = []
        adapter_missing_refs: List[Dict[str, Any]] = []
        adapter_unsafe_refs: List[Dict[str, Any]] = []
        refs = _as_string_list(adapter.get("refs"))
        if not refs:
            adapter_failures.append(f"adapter_refs_empty:{adapter_id}")
        for ref in refs:
            if not _is_safe_relative_ref(ref):
                item = {"adapter_id": adapter_id, "ref": ref}
                adapter_unsafe_refs.append(item)
                unsafe_refs.append(item)
                adapter_failures.append(f"unsafe_ref:{adapter_id}:{ref}")
                continue
            resolved = _resolve_ref(ref, project_root=project, package_root=package)
            resolved["adapter_id"] = adapter_id
            if resolved["ok"]:
                adapter_resolved_refs.append(resolved)
                resolved_refs.append(resolved)
            else:
                adapter_missing_refs.append(resolved)
                missing_refs.append(resolved)
                adapter_failures.append(f"missing_ref:{adapter_id}:{ref}")

        failures.extend(adapter_failures)
        adapter_results.append(
            {
                "id": adapter_id,
                "ok": not adapter_failures,
                "state": state,
                "transport": str(adapter.get("transport") or ""),
                "risk": str(adapter.get("risk") or ""),
                "capability_scopes": _as_string_list(adapter.get("capability_scopes")),
                "tool_allowlist": _as_string_list(adapter.get("tool_allowlist")),
                "failures": sorted(set(adapter_failures)),
                "resolved_refs": sorted(adapter_resolved_refs, key=lambda item: item["ref"]),
                "missing_refs": sorted(adapter_missing_refs, key=lambda item: item["ref"]),
                "unsafe_refs": sorted(adapter_unsafe_refs, key=lambda item: item["ref"]),
            }
        )

    active_states = {"shadow", "canary", "enabled"}
    return {
        "apiVersion": CONFIG_API_VERSION,
        "kind": VALIDATION_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "registry_path": str(registry_path or ""),
        "project_root": _display_path(project),
        "package_root": _display_path(package),
        "failures": sorted(set(failures)),
        "policy": policy,
        "metrics": {
            "adapters": len(adapters),
            "disabled_adapters": sum(1 for item in adapters if isinstance(item, dict) and str(item.get("state") or "") == "disabled"),
            "active_adapters": sum(1 for item in adapters if isinstance(item, dict) and str(item.get("state") or "") in active_states),
            "refs": sum(len(_as_string_list(item.get("refs"))) for item in adapters if isinstance(item, dict)),
            "resolved_refs": len(resolved_refs),
            "missing_refs": len(missing_refs),
            "unsafe_refs": len(unsafe_refs),
            "states": dict(sorted(state_counts.items())),
        },
        "adapter_results": sorted(adapter_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(resolved_refs, key=lambda item: (item["adapter_id"], item["ref"])),
        "missing_refs": sorted(missing_refs, key=lambda item: (item["adapter_id"], item["ref"])),
        "unsafe_refs": sorted(unsafe_refs, key=lambda item: (item["adapter_id"], item["ref"])),
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge MCP adapter registry safety policy.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--registry",
        default="noemaforge/configs/mcp-adapter-registry.json",
        help="Registry path, absolute or relative to project root.",
    )
    parser.add_argument("--summary", action="store_true", help="Emit a compact validation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = _as_path(args.project_root)
    package_root = _as_path(args.package_root) if args.package_root else project_root / "noemaforge"
    registry_path = Path(args.registry)
    if not registry_path.is_absolute():
        registry_path = project_root / registry_path

    report = validate_mcp_adapter_registry(
        load_registry(registry_path),
        project_root=project_root,
        package_root=package_root,
        registry_path=registry_path,
    )
    payload: Dict[str, Any]
    if args.summary:
        payload = {
            "apiVersion": report["apiVersion"],
            "kind": "MCPAdapterRegistryValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
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
