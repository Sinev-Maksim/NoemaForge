#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/gateway_inference_service_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate offline gateway inference service contracts before edge deployment consideration.
Inputs: noemaforge/configs/gateway-inference-service.json plus local project/package roots.
Outputs: JSON-compatible GatewayInferenceServiceReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_gateway_inference_service_runtime.py
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


API_VERSION = "noemaforge.gateway-inference-service/v1"
POLICY_KIND = "GatewayInferenceServicePolicy"
REPORT_KIND = "GatewayInferenceServiceReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_PROTOCOLS = {"rest", "mqtt"}
VALID_ENDPOINT_KINDS = {"inference", "health", "ready", "metrics"}
VALID_MODEL_SOURCES = {"signed_manifest"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
SHA256_RE = re.compile(r"^[A-Fa-f0-9]{64}$")
REGISTRY_REF_RE = re.compile(r"^[a-z-]+:[A-Za-z0-9_.:-]+:[A-Za-z0-9_.:-]+$")


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


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


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
        "require_inference_endpoint",
        "require_manifest_only_model_loading",
        "require_signed_model_manifest",
        "require_health_endpoint",
        "require_ready_endpoint",
        "require_metrics_endpoint",
        "require_edge_rules_fallback",
        "forbid_direct_model_path",
        "forbid_direct_control_decisions",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    protocols = set(_as_string_list(policy.get("allowed_protocols")))
    model_sources = set(_as_string_list(policy.get("allowed_model_sources")))
    endpoint_kinds = set(_as_string_list(policy.get("allowed_endpoint_kinds")))
    if not protocols:
        failures.append("policy_allowed_protocols_empty")
    if not model_sources:
        failures.append("policy_allowed_model_sources_empty")
    if not endpoint_kinds:
        failures.append("policy_allowed_endpoint_kinds_empty")
    failures.extend(f"policy_invalid_protocol:{item}" for item in sorted(protocols - VALID_PROTOCOLS))
    failures.extend(f"policy_invalid_model_source:{item}" for item in sorted(model_sources - VALID_MODEL_SOURCES))
    failures.extend(f"policy_invalid_endpoint_kind:{item}" for item in sorted(endpoint_kinds - VALID_ENDPOINT_KINDS))
    return failures


def _load_manifest(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_failures(manifest: Dict[str, Any], owner: str) -> List[str]:
    failures: List[str] = []
    if manifest.get("kind") != "SignedModelManifest":
        failures.append(f"service_manifest_kind_invalid:{owner}")
    if not SAFE_ID_RE.match(str(manifest.get("id") or "")):
        failures.append(f"service_manifest_id_invalid:{owner}")
    if not REGISTRY_REF_RE.match(str(manifest.get("model_ref") or "")):
        failures.append(f"service_manifest_model_ref_invalid:{owner}")
    if not SHA256_RE.match(str(manifest.get("sha256") or "")):
        failures.append(f"service_manifest_sha256_invalid:{owner}")
    if not str(manifest.get("signature") or "").strip():
        failures.append(f"service_manifest_signature_missing:{owner}")
    if not str(manifest.get("artifact_uri") or "").strip():
        failures.append(f"service_manifest_artifact_uri_missing:{owner}")
    if not str(manifest.get("input_contract") or "").strip():
        failures.append(f"service_manifest_input_contract_missing:{owner}")
    if not str(manifest.get("output_contract") or "").strip():
        failures.append(f"service_manifest_output_contract_missing:{owner}")
    if str(manifest.get("fallback") or "") != "whitebox":
        failures.append(f"service_manifest_fallback_not_whitebox:{owner}")
    return failures


def _endpoint_failures(endpoint: Dict[str, Any], policy: Dict[str, Any], owner: str) -> List[str]:
    failures: List[str] = []
    endpoint_id = str(endpoint.get("id") or "").strip()
    label = f"{owner}:{endpoint_id or '<missing>'}"
    if not SAFE_ID_RE.match(endpoint_id):
        failures.append(f"endpoint_id_invalid:{label}")
    kind = str(endpoint.get("kind") or "")
    protocol = str(endpoint.get("protocol") or "")
    if kind not in set(_as_string_list(policy.get("allowed_endpoint_kinds"))) or kind not in VALID_ENDPOINT_KINDS:
        failures.append(f"endpoint_kind_not_allowed:{label}:{kind}")
    if protocol not in set(_as_string_list(policy.get("allowed_protocols"))) or protocol not in VALID_PROTOCOLS:
        failures.append(f"endpoint_protocol_not_allowed:{label}:{protocol}")
    if endpoint.get("enabled") is not True:
        failures.append(f"endpoint_not_enabled:{label}")
    if protocol == "rest":
        if not str(endpoint.get("path") or "").startswith("/"):
            failures.append(f"endpoint_rest_path_invalid:{label}")
        method = str(endpoint.get("method") or "")
        if method not in {"GET", "POST"}:
            failures.append(f"endpoint_rest_method_invalid:{label}:{method}")
    if protocol == "mqtt" and not str(endpoint.get("topic") or "").strip():
        failures.append(f"endpoint_mqtt_topic_missing:{label}")
    if kind in {"health", "ready", "metrics"} and protocol != "rest":
        failures.append(f"endpoint_control_plane_not_rest:{label}")
    return failures


def _service_failures(service: Dict[str, Any], policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> List[str]:
    failures: List[str] = []
    service_id = str(service.get("id") or "").strip()
    owner = service_id or "<missing>"
    if not SAFE_ID_RE.match(service_id):
        failures.append(f"service_id_invalid:{owner}")
    if str(service.get("state") or "") not in VALID_STATUSES:
        failures.append(f"service_state_invalid:{owner}:{service.get('state')}")
    if service.get("containerized") is not True:
        failures.append(f"service_not_containerized:{owner}")
    if not str(service.get("image") or "").strip():
        failures.append(f"service_image_missing:{owner}")
    model_source = str(service.get("model_source") or "")
    if model_source not in set(_as_string_list(policy.get("allowed_model_sources"))) or model_source not in VALID_MODEL_SOURCES:
        failures.append(f"service_model_source_not_allowed:{owner}:{model_source}")
    if policy.get("forbid_direct_model_path") is True and str(service.get("direct_model_path") or "").strip():
        failures.append(f"service_direct_model_path_present:{owner}")
    if policy.get("forbid_direct_control_decisions") is True and service.get("direct_control_decisions") is not False:
        failures.append(f"service_direct_control_decision_enabled:{owner}")

    for ref_key in ["signed_model_manifest_ref", "tinyml_node_policy_ref", "edge_rules_ref"]:
        ref = str(service.get(ref_key) or "")
        if not _is_safe_relative_ref(ref):
            failures.append(f"service_{ref_key}_unsafe:{owner}:{ref}")

    manifest_ref = str(service.get("signed_model_manifest_ref") or "")
    manifest_resolved = _resolve_ref(manifest_ref, project_root=project_root, package_root=package_root) if _is_safe_relative_ref(manifest_ref) else {"ok": False}
    if manifest_resolved.get("ok"):
        try:
            failures.extend(_manifest_failures(_load_manifest(Path(str(manifest_resolved["path"]))), owner))
        except Exception as exc:
            failures.append(f"service_manifest_load_failed:{owner}:{exc}")
    else:
        failures.append(f"service_manifest_missing:{owner}:{manifest_ref}")

    endpoints = service.get("endpoints") if isinstance(service.get("endpoints"), list) else []
    if not endpoints:
        failures.append(f"service_endpoints_empty:{owner}")
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            failures.append(f"endpoint_not_object:{owner}")
            continue
        failures.extend(_endpoint_failures(endpoint, policy, owner))

    enabled = [endpoint for endpoint in endpoints if isinstance(endpoint, dict) and endpoint.get("enabled") is True]
    by_kind = {kind: [item for item in enabled if item.get("kind") == kind] for kind in VALID_ENDPOINT_KINDS}
    if policy.get("require_inference_endpoint") is True and not by_kind["inference"]:
        failures.append(f"service_inference_endpoint_missing:{owner}")
    if policy.get("require_health_endpoint") is True and not any(item.get("path") == "/health" for item in by_kind["health"]):
        failures.append(f"service_health_endpoint_missing:{owner}")
    if policy.get("require_ready_endpoint") is True and not any(item.get("path") == "/ready" for item in by_kind["ready"]):
        failures.append(f"service_ready_endpoint_missing:{owner}")
    if policy.get("require_metrics_endpoint") is True and not any(item.get("path") == "/metrics" for item in by_kind["metrics"]):
        failures.append(f"service_metrics_endpoint_missing:{owner}")
    if by_kind["inference"] and not any(item.get("protocol") in VALID_PROTOCOLS for item in by_kind["inference"]):
        failures.append(f"service_rest_or_mqtt_inference_endpoint_missing:{owner}")
    return failures


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


def validate_gateway_inference_service_policy(
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
    services = payload.get("services") if isinstance(payload.get("services"), list) else []
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    if not services:
        failures.append("services_empty")

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    service_results: List[Dict[str, Any]] = []

    policy_refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(policy_refs["failures"])
    all_resolved_refs.extend(policy_refs["resolved_refs"])
    all_missing_refs.extend(policy_refs["missing_refs"])
    all_unsafe_refs.extend(policy_refs["unsafe_refs"])

    for service in services:
        if not isinstance(service, dict):
            failures.append("service_not_object")
            continue
        service_id = str(service.get("id") or "<missing>")
        service_failures = _service_failures(service, policy, project_root=project, package_root=package)
        refs = _as_string_list(service.get("refs"))
        for ref_key in ["signed_model_manifest_ref", "tinyml_node_policy_ref", "edge_rules_ref"]:
            ref = str(service.get(ref_key) or "")
            if ref and ref not in refs:
                refs.append(ref)
        refs_result = _resolve_refs(refs, project_root=project, package_root=package, owner=service_id)
        service_failures.extend(refs_result["failures"])
        failures.extend(service_failures)
        all_resolved_refs.extend(refs_result["resolved_refs"])
        all_missing_refs.extend(refs_result["missing_refs"])
        all_unsafe_refs.extend(refs_result["unsafe_refs"])
        endpoints = service.get("endpoints") if isinstance(service.get("endpoints"), list) else []
        service_results.append(
            {
                "id": service_id,
                "ok": not service_failures,
                "model_source": str(service.get("model_source") or ""),
                "containerized": service.get("containerized") is True,
                "direct_control_decisions": service.get("direct_control_decisions") is True,
                "endpoints": len(endpoints),
                "inference_endpoints": sum(1 for endpoint in endpoints if isinstance(endpoint, dict) and endpoint.get("kind") == "inference" and endpoint.get("enabled") is True),
                "failures": sorted(set(service_failures)),
            }
        )

    endpoint_rows = [
        endpoint
        for service in services
        if isinstance(service, dict)
        for endpoint in (service.get("endpoints") if isinstance(service.get("endpoints"), list) else [])
        if isinstance(endpoint, dict)
    ]
    checks = [
        {"id": "inference_endpoint", "status": "passed" if not any("inference_endpoint" in item for item in failures) else "failed"},
        {"id": "manifest_only_loading", "status": "passed" if not any("model_source" in item or "direct_model_path" in item or "manifest_" in item for item in failures) else "failed"},
        {"id": "health_endpoint", "status": "passed" if not any("health_endpoint" in item for item in failures) else "failed"},
        {"id": "ready_endpoint", "status": "passed" if not any("ready_endpoint" in item for item in failures) else "failed"},
        {"id": "metrics_endpoint", "status": "passed" if not any("metrics_endpoint" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "services": len(service_results),
        "passing_services": sum(1 for item in service_results if item["ok"]),
        "endpoints": len(endpoint_rows),
        "inference_endpoints": sum(1 for item in endpoint_rows if item.get("kind") == "inference" and item.get("enabled") is True),
        "rest_endpoints": sum(1 for item in endpoint_rows if item.get("protocol") == "rest" and item.get("enabled") is True),
        "mqtt_endpoints": sum(1 for item in endpoint_rows if item.get("protocol") == "mqtt" and item.get("enabled") is True),
        "manifest_loaded_services": sum(1 for item in service_results if item["model_source"] == "signed_manifest"),
        "direct_control_decision_services": sum(1 for item in service_results if item["direct_control_decisions"]),
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
        "service_results": sorted(service_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def gateway_inference_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("gateway_inference_service_report_required")
    status = "passed" if report.get("ok") else "failed"
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": [
            {"id": "model_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "safety_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
        ],
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge gateway inference service contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/gateway-inference-service.json",
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

    report = validate_gateway_inference_service_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "GatewayInferenceServiceSummary",
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
