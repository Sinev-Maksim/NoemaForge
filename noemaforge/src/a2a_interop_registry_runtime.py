#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/a2a_interop_registry_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate optional A2A interoperability boundaries before peer exposure.
Inputs: noemaforge/configs/a2a-interop-registry.json plus local project/package roots.
Outputs: JSON-compatible A2AInteropRegistryValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_a2a_interop_registry_runtime.py
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


CONFIG_API_VERSION = "noemaforge.a2a-interop/v1"
CONFIG_KIND = "A2AInteropRegistry"
VALIDATION_KIND = "A2AInteropRegistryValidationReport"

VALID_STATES = {"disabled", "shadow", "canary", "enabled", "retired"}
VALID_DIRECTIONS = {"none", "inbound", "outbound", "bidirectional"}
VALID_TRANSPORTS = {"offline_manifest", "local_loopback", "http", "grpc", "websocket", "tcp"}
NETWORK_TRANSPORTS = {"http", "grpc", "websocket", "tcp"}
VALID_PAYLOAD_CLASSES = {"capability_manifest", "task_summary", "review_request", "release_evidence"}
RISK_LEVELS = {"low": 1, "medium": 2, "high": 3, "critical": 4}

_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,119}$")
_SAFE_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,80}$")
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
    return {
        "apiVersion": CONFIG_API_VERSION,
        "kind": VALIDATION_KIND,
        "ok": False,
        "created_at": _nowz(),
        "registry_path": str(registry_path or ""),
        "project_root": _display_path(project_root),
        "package_root": _display_path(package_root),
        "failures": sorted(set(str(item) for item in failures)),
        "metrics": {
            "peers": 0,
            "disabled_peers": 0,
            "active_peers": 0,
            "refs": 0,
            "resolved_refs": 0,
            "missing_refs": 0,
            "unsafe_refs": 0,
        },
        "peer_results": [],
    }


def _policy_failure_checks(policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    if str(policy.get("default_state") or "") != "disabled":
        failures.append("policy_default_state_not_disabled")
    if str(policy.get("default_direction") or "") != "none":
        failures.append("policy_default_direction_not_none")
    if str(policy.get("default_network") or "") != "deny":
        failures.append("policy_default_network_not_deny")
    for key in [
        "require_trace_id",
        "require_capability_token",
        "require_registry_entry",
        "require_operator_review",
        "require_release_evidence_before_enable",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")

    allowed_transports = set(_as_string_list(policy.get("allowed_transports")))
    blocked_transports = set(_as_string_list(policy.get("blocked_transports")))
    if not allowed_transports:
        failures.append("policy_allowed_transports_empty")
    failures.extend(f"policy_invalid_allowed_transport:{item}" for item in sorted(allowed_transports - VALID_TRANSPORTS))
    failures.extend(f"policy_invalid_blocked_transport:{item}" for item in sorted(blocked_transports - VALID_TRANSPORTS))
    failures.extend(f"policy_transport_allowed_and_blocked:{item}" for item in sorted(allowed_transports & blocked_transports))
    for transport in sorted(NETWORK_TRANSPORTS):
        if transport not in blocked_transports:
            failures.append(f"policy_network_transport_not_blocked:{transport}")

    payload_classes = set(_as_string_list(policy.get("allowed_payload_classes")))
    if not payload_classes:
        failures.append("policy_allowed_payload_classes_empty")
    failures.extend(f"policy_invalid_payload_class:{item}" for item in sorted(payload_classes - VALID_PAYLOAD_CLASSES))

    max_risk = str(policy.get("max_peer_risk") or "")
    if max_risk not in RISK_LEVELS:
        failures.append(f"policy_invalid_max_peer_risk:{max_risk}")
    return failures


def _peer_failure_checks(peer: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    peer_id = str(peer.get("id") or "").strip()
    owner = peer_id or "<missing>"
    if not _SAFE_ID_RE.match(peer_id):
        failures.append(f"peer_id_invalid:{owner}")
    if str(peer.get("protocol") or "").strip() != "a2a":
        failures.append(f"peer_protocol_not_a2a:{owner}")

    state = str(peer.get("state") or policy.get("default_state") or "").strip()
    if state not in VALID_STATES:
        failures.append(f"peer_invalid_state:{owner}:{state}")

    direction = str(peer.get("direction") or policy.get("default_direction") or "").strip()
    if direction not in VALID_DIRECTIONS:
        failures.append(f"peer_invalid_direction:{owner}:{direction}")

    transport = str(peer.get("transport") or "").strip()
    allowed_transports = set(_as_string_list(policy.get("allowed_transports")))
    blocked_transports = set(_as_string_list(policy.get("blocked_transports")))
    if transport not in VALID_TRANSPORTS:
        failures.append(f"peer_invalid_transport:{owner}:{transport}")
    if transport in blocked_transports:
        failures.append(f"peer_transport_blocked:{owner}:{transport}")
    if allowed_transports and transport not in allowed_transports:
        failures.append(f"peer_transport_not_allowed:{owner}:{transport}")

    risk = str(peer.get("risk") or "").strip()
    max_risk = str(policy.get("max_peer_risk") or "")
    if risk not in RISK_LEVELS:
        failures.append(f"peer_invalid_risk:{owner}:{risk}")
    elif max_risk in RISK_LEVELS and RISK_LEVELS[risk] > RISK_LEVELS[max_risk]:
        failures.append(f"peer_risk_exceeds_policy:{owner}:{risk}>{max_risk}")

    if str(peer.get("network") or "").strip() != "deny":
        failures.append(f"peer_network_not_deny:{owner}")
    if peer.get("autonomy_increase") is not False:
        failures.append(f"peer_autonomy_increase_not_false:{owner}")

    scopes = _as_string_list(peer.get("capability_scopes"))
    if not scopes:
        failures.append(f"peer_capability_scopes_empty:{owner}")
    for scope in scopes:
        if not _SAFE_TOKEN_RE.match(scope):
            failures.append(f"peer_capability_scope_invalid:{owner}:{scope}")
    if len(scopes) != len(set(scopes)):
        failures.append(f"peer_capability_scopes_duplicate:{owner}")

    payloads = _as_string_list(peer.get("allowed_payload_classes"))
    allowed_payloads = set(_as_string_list(policy.get("allowed_payload_classes")))
    if not payloads:
        failures.append(f"peer_allowed_payload_classes_empty:{owner}")
    for payload_class in payloads:
        if payload_class not in VALID_PAYLOAD_CLASSES:
            failures.append(f"peer_invalid_payload_class:{owner}:{payload_class}")
        if allowed_payloads and payload_class not in allowed_payloads:
            failures.append(f"peer_payload_class_not_allowed:{owner}:{payload_class}")

    actions = _as_string_list(peer.get("allowed_actions"))
    if not actions:
        failures.append(f"peer_allowed_actions_empty:{owner}")
    for action in actions:
        if not _SAFE_TOKEN_RE.match(action):
            failures.append(f"peer_allowed_action_invalid:{owner}:{action}")

    if policy.get("require_trace_id") is True and peer.get("trace_required") is not True:
        failures.append(f"peer_trace_not_required:{owner}")
    if policy.get("require_capability_token") is True and peer.get("capability_token_required") is not True:
        failures.append(f"peer_capability_token_not_required:{owner}")
    if policy.get("require_registry_entry") is True:
        if peer.get("registry_entry_required") is not True:
            failures.append(f"peer_registry_entry_not_required:{owner}")
        registry_ref = str(peer.get("registry_ref") or "").strip()
        if not _REGISTRY_REF_RE.match(registry_ref):
            failures.append(f"peer_registry_ref_invalid:{owner}:{registry_ref}")

    if peer.get("audit_logging") is not True:
        failures.append(f"peer_audit_logging_not_required:{owner}")
    if peer.get("human_review_required") is not True:
        failures.append(f"peer_human_review_not_required:{owner}")

    sandbox = peer.get("sandbox") if isinstance(peer.get("sandbox"), dict) else {}
    if not sandbox:
        failures.append(f"peer_sandbox_missing:{owner}")
    if sandbox.get("write") is not False:
        failures.append(f"peer_sandbox_write_not_false:{owner}")
    if str(sandbox.get("egress") or "").strip() != "deny":
        failures.append(f"peer_sandbox_egress_not_deny:{owner}")
    if str(sandbox.get("external_identity") or "").strip() != "none":
        failures.append(f"peer_sandbox_external_identity_not_none:{owner}")
    if not str(sandbox.get("profile") or "").strip():
        failures.append(f"peer_sandbox_profile_missing:{owner}")

    review = peer.get("review") if isinstance(peer.get("review"), dict) else {}
    if policy.get("require_operator_review") is True:
        if review.get("required") is not True:
            failures.append(f"peer_review_not_required:{owner}")
        if not str(review.get("route") or "").strip():
            failures.append(f"peer_review_route_missing:{owner}")
        if not _as_string_list(review.get("reviewers")):
            failures.append(f"peer_reviewers_missing:{owner}")

    release_evidence = peer.get("release_evidence") if isinstance(peer.get("release_evidence"), dict) else {}
    if policy.get("require_release_evidence_before_enable") is True:
        if release_evidence.get("required_before_enable") is not True:
            failures.append(f"peer_release_evidence_not_required:{owner}")
        if state in {"shadow", "canary", "enabled"} and not str(release_evidence.get("evidence_ref") or "").strip():
            failures.append(f"peer_active_without_release_evidence:{owner}")

    rollback_plan = str(peer.get("rollback_plan") or "").strip()
    if len(rollback_plan) < 20:
        failures.append(f"peer_rollback_plan_missing:{owner}")

    if state in {"shadow", "canary", "enabled"}:
        if review.get("required") is not True:
            failures.append(f"peer_active_without_review:{owner}")
        if peer.get("trace_required") is not True:
            failures.append(f"peer_active_without_trace:{owner}")
        if peer.get("capability_token_required") is not True:
            failures.append(f"peer_active_without_capability_token:{owner}")
        if str(peer.get("network") or "").strip() != "deny":
            failures.append(f"peer_active_network_not_denied:{owner}")
        if peer.get("autonomy_increase") is not False:
            failures.append(f"peer_active_increases_autonomy:{owner}")

    return failures


def validate_a2a_interop_registry(
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

    peers = registry.get("peers") if isinstance(registry.get("peers"), list) else []
    if not peers:
        failures.append("peers_empty")

    seen_ids: set[str] = set()
    peer_results: List[Dict[str, Any]] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    state_counts: Dict[str, int] = {}
    direction_counts: Dict[str, int] = {}

    for idx, raw_peer in enumerate(peers):
        peer = raw_peer if isinstance(raw_peer, dict) else {}
        peer_id = str(peer.get("id") or f"<index:{idx}>").strip()
        peer_failures = _peer_failure_checks(peer, policy)
        if peer_id in seen_ids:
            peer_failures.append(f"peer_duplicate_id:{peer_id}")
        seen_ids.add(peer_id)

        state = str(peer.get("state") or policy.get("default_state") or "").strip()
        direction = str(peer.get("direction") or policy.get("default_direction") or "").strip()
        state_counts[state] = state_counts.get(state, 0) + 1
        direction_counts[direction] = direction_counts.get(direction, 0) + 1

        peer_resolved_refs: List[Dict[str, Any]] = []
        peer_missing_refs: List[Dict[str, Any]] = []
        peer_unsafe_refs: List[Dict[str, Any]] = []
        refs = _as_string_list(peer.get("refs"))
        if not refs:
            peer_failures.append(f"peer_refs_empty:{peer_id}")
        for ref in refs:
            if not _is_safe_relative_ref(ref):
                item = {"peer_id": peer_id, "ref": ref}
                peer_unsafe_refs.append(item)
                unsafe_refs.append(item)
                peer_failures.append(f"unsafe_ref:{peer_id}:{ref}")
                continue
            resolved = _resolve_ref(ref, project_root=project, package_root=package)
            resolved["peer_id"] = peer_id
            if resolved["ok"]:
                peer_resolved_refs.append(resolved)
                resolved_refs.append(resolved)
            else:
                peer_missing_refs.append(resolved)
                missing_refs.append(resolved)
                peer_failures.append(f"missing_ref:{peer_id}:{ref}")

        failures.extend(peer_failures)
        peer_results.append(
            {
                "id": peer_id,
                "ok": not peer_failures,
                "state": state,
                "direction": direction,
                "transport": str(peer.get("transport") or ""),
                "risk": str(peer.get("risk") or ""),
                "capability_scopes": _as_string_list(peer.get("capability_scopes")),
                "allowed_payload_classes": _as_string_list(peer.get("allowed_payload_classes")),
                "allowed_actions": _as_string_list(peer.get("allowed_actions")),
                "failures": sorted(set(peer_failures)),
                "resolved_refs": sorted(peer_resolved_refs, key=lambda item: item["ref"]),
                "missing_refs": sorted(peer_missing_refs, key=lambda item: item["ref"]),
                "unsafe_refs": sorted(peer_unsafe_refs, key=lambda item: item["ref"]),
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
            "peers": len(peers),
            "disabled_peers": sum(1 for item in peers if isinstance(item, dict) and str(item.get("state") or "") == "disabled"),
            "active_peers": sum(1 for item in peers if isinstance(item, dict) and str(item.get("state") or "") in active_states),
            "refs": sum(len(_as_string_list(item.get("refs"))) for item in peers if isinstance(item, dict)),
            "resolved_refs": len(resolved_refs),
            "missing_refs": len(missing_refs),
            "unsafe_refs": len(unsafe_refs),
            "states": dict(sorted(state_counts.items())),
            "directions": dict(sorted(direction_counts.items())),
        },
        "peer_results": sorted(peer_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(resolved_refs, key=lambda item: (item["peer_id"], item["ref"])),
        "missing_refs": sorted(missing_refs, key=lambda item: (item["peer_id"], item["ref"])),
        "unsafe_refs": sorted(unsafe_refs, key=lambda item: (item["peer_id"], item["ref"])),
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge optional A2A interoperability safety policy.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--registry",
        default="noemaforge/configs/a2a-interop-registry.json",
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

    report = validate_a2a_interop_registry(
        load_registry(registry_path),
        project_root=project_root,
        package_root=package_root,
        registry_path=registry_path,
    )
    payload: Dict[str, Any]
    if args.summary:
        payload = {
            "apiVersion": report["apiVersion"],
            "kind": "A2AInteropRegistryValidationSummary",
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
