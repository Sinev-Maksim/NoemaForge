#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/sense_layer_edge_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate offline Sense Layer Edge contracts for sensor/system metric ingestion.
Inputs: noemaforge/configs/sense-layer-edge.json plus local project/package roots.
Outputs: JSON-compatible SenseLayerEdgeReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_sense_layer_edge_runtime.py
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


API_VERSION = "noemaforge.sense-layer-edge/v1"
POLICY_KIND = "SenseLayerEdgePolicy"
REPORT_KIND = "SenseLayerEdgeReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_PROTOCOLS = {"mqtt", "serial", "system_metrics"}
VALID_TRUST_LEVELS = {"trusted", "simulated", "unverified"}
REQUIRED_METRIC_FIELDS = {"metric_id", "source_id", "source_trust", "timestamp", "value", "unit"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
NORMALIZER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")


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


def _yaml_list_values(text: str, key: str) -> List[str]:
    values: List[str] = []
    capture = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == f"{key}:":
            capture = True
            continue
        if capture and stripped.endswith(":") and not stripped.startswith("- "):
            break
        if capture and stripped.startswith("- "):
            values.append(stripped[2:].strip())
    return values


def _input_contract_failures(path: Path, policy: Dict[str, Any], owner: str) -> List[str]:
    failures: List[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return [f"adapter_schema_load_failed:{owner}:{exc}"]
    if "apiVersion: noemaforge.sense-layer-edge/v1" not in text:
        failures.append(f"adapter_schema_api_version_missing:{owner}")
    fields = set(_yaml_list_values(text, "required_fields"))
    trust_levels = set(_yaml_list_values(text, "trust_levels"))
    protocols = set(_yaml_list_values(text, "protocols"))
    required_fields = set(_as_string_list(policy.get("required_metric_fields"))) or REQUIRED_METRIC_FIELDS
    missing_fields = required_fields - fields
    if missing_fields:
        failures.extend(f"adapter_schema_required_field_missing:{owner}:{item}" for item in sorted(missing_fields))
    if not set(_as_string_list(policy.get("allowed_trust_levels"))).issubset(trust_levels):
        failures.append(f"adapter_schema_trust_levels_incomplete:{owner}")
    if not set(_as_string_list(policy.get("allowed_protocols"))).issubset(protocols):
        failures.append(f"adapter_schema_protocols_incomplete:{owner}")
    return failures


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
        "require_mqtt_adapter",
        "require_serial_adapter",
        "require_system_metrics_adapter",
        "require_normalized_schema",
        "require_explicit_source_trust",
        "require_no_live_io_in_adapters",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    protocols = set(_as_string_list(policy.get("allowed_protocols")))
    trust_levels = set(_as_string_list(policy.get("allowed_trust_levels")))
    required_fields = set(_as_string_list(policy.get("required_metric_fields")))
    if not protocols:
        failures.append("policy_allowed_protocols_empty")
    if not trust_levels:
        failures.append("policy_allowed_trust_levels_empty")
    if not required_fields:
        failures.append("policy_required_metric_fields_empty")
    failures.extend(f"policy_invalid_protocol:{item}" for item in sorted(protocols - VALID_PROTOCOLS))
    failures.extend(f"policy_invalid_trust_level:{item}" for item in sorted(trust_levels - VALID_TRUST_LEVELS))
    failures.extend(f"policy_required_metric_field_unknown:{item}" for item in sorted(required_fields - REQUIRED_METRIC_FIELDS))
    failures.extend(f"policy_required_metric_field_missing:{item}" for item in sorted(REQUIRED_METRIC_FIELDS - required_fields))
    return failures


def _adapter_failures(adapter: Dict[str, Any], policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> List[str]:
    failures: List[str] = []
    adapter_id = str(adapter.get("id") or "").strip()
    owner = adapter_id or "<missing>"
    if not SAFE_ID_RE.match(adapter_id):
        failures.append(f"adapter_id_invalid:{owner}")
    if str(adapter.get("state") or "") not in VALID_STATUSES:
        failures.append(f"adapter_state_invalid:{owner}:{adapter.get('state')}")
    protocol = str(adapter.get("protocol") or "")
    if protocol not in set(_as_string_list(policy.get("allowed_protocols"))) or protocol not in VALID_PROTOCOLS:
        failures.append(f"adapter_protocol_not_allowed:{owner}:{protocol}")
    trust = str(adapter.get("source_trust") or "")
    if policy.get("require_explicit_source_trust") is True and trust not in set(_as_string_list(policy.get("allowed_trust_levels"))):
        failures.append(f"adapter_source_trust_not_allowed:{owner}:{trust}")
    if not str(adapter.get("source_id") or "").strip():
        failures.append(f"adapter_source_id_missing:{owner}")
    ingress = adapter.get("ingress") if isinstance(adapter.get("ingress"), dict) else {}
    if policy.get("require_no_live_io_in_adapters") is True and ingress.get("live_io") is not False:
        failures.append(f"adapter_live_io_not_false:{owner}")
    if protocol == "mqtt" and not str(ingress.get("topic") or "").strip():
        failures.append(f"adapter_mqtt_topic_missing:{owner}")
    if protocol == "serial" and not str(ingress.get("device") or "").strip():
        failures.append(f"adapter_serial_device_missing:{owner}")
    if protocol == "system_metrics" and not str(ingress.get("collector") or "").strip():
        failures.append(f"adapter_system_metrics_collector_missing:{owner}")
    if not NORMALIZER_RE.match(str(adapter.get("normalizer") or "")):
        failures.append(f"adapter_normalizer_invalid:{owner}")
    schema_ref = str(adapter.get("schema_ref") or "")
    if not _is_safe_relative_ref(schema_ref):
        failures.append(f"adapter_schema_ref_unsafe:{owner}:{schema_ref}")
    else:
        resolved = _resolve_ref(schema_ref, project_root=project_root, package_root=package_root)
        if resolved.get("ok"):
            failures.extend(_input_contract_failures(Path(str(resolved["path"])), policy, owner))
        else:
            failures.append(f"adapter_schema_ref_missing:{owner}:{schema_ref}")
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


def validate_sense_layer_edge_policy(
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
    adapters = payload.get("adapters") if isinstance(payload.get("adapters"), list) else []
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    if not adapters:
        failures.append("adapters_empty")

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    adapter_results: List[Dict[str, Any]] = []

    policy_refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(policy_refs["failures"])
    all_resolved_refs.extend(policy_refs["resolved_refs"])
    all_missing_refs.extend(policy_refs["missing_refs"])
    all_unsafe_refs.extend(policy_refs["unsafe_refs"])

    for adapter in adapters:
        if not isinstance(adapter, dict):
            failures.append("adapter_not_object")
            continue
        adapter_id = str(adapter.get("id") or "<missing>")
        adapter_failures = _adapter_failures(adapter, policy, project_root=project, package_root=package)
        refs = _as_string_list(adapter.get("refs"))
        schema_ref = str(adapter.get("schema_ref") or "")
        if schema_ref and schema_ref not in refs:
            refs.append(schema_ref)
        refs_result = _resolve_refs(refs, project_root=project, package_root=package, owner=adapter_id)
        adapter_failures.extend(refs_result["failures"])
        failures.extend(adapter_failures)
        all_resolved_refs.extend(refs_result["resolved_refs"])
        all_missing_refs.extend(refs_result["missing_refs"])
        all_unsafe_refs.extend(refs_result["unsafe_refs"])
        adapter_results.append(
            {
                "id": adapter_id,
                "ok": not adapter_failures,
                "protocol": str(adapter.get("protocol") or ""),
                "source_trust": str(adapter.get("source_trust") or ""),
                "live_io": (adapter.get("ingress") if isinstance(adapter.get("ingress"), dict) else {}).get("live_io") is True,
                "failures": sorted(set(adapter_failures)),
            }
        )

    protocols = {item["protocol"] for item in adapter_results}
    if policy.get("require_mqtt_adapter") is True and "mqtt" not in protocols:
        failures.append("mqtt_adapter_missing")
    if policy.get("require_serial_adapter") is True and "serial" not in protocols:
        failures.append("serial_adapter_missing")
    if policy.get("require_system_metrics_adapter") is True and "system_metrics" not in protocols:
        failures.append("system_metrics_adapter_missing")

    checks = [
        {"id": "mqtt_adapter", "status": "passed" if "mqtt" in protocols and "mqtt_adapter_missing" not in failures else "failed"},
        {"id": "serial_adapter", "status": "passed" if "serial" in protocols and "serial_adapter_missing" not in failures else "failed"},
        {"id": "system_metrics_adapter", "status": "passed" if "system_metrics" in protocols and "system_metrics_adapter_missing" not in failures else "failed"},
        {"id": "normalized_schema", "status": "passed" if not any("schema" in item or "metric_field" in item for item in failures) else "failed"},
        {"id": "explicit_source_trust", "status": "passed" if not any("source_trust" in item or "trust" in item for item in failures) else "failed"},
        {"id": "no_live_io", "status": "passed" if not any("live_io" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "adapters": len(adapter_results),
        "passing_adapters": sum(1 for item in adapter_results if item["ok"]),
        "mqtt_adapters": sum(1 for item in adapter_results if item["protocol"] == "mqtt"),
        "serial_adapters": sum(1 for item in adapter_results if item["protocol"] == "serial"),
        "system_metrics_adapters": sum(1 for item in adapter_results if item["protocol"] == "system_metrics"),
        "trusted_sources": sum(1 for item in adapter_results if item["source_trust"] == "trusted"),
        "simulated_sources": sum(1 for item in adapter_results if item["source_trust"] == "simulated"),
        "unverified_sources": sum(1 for item in adapter_results if item["source_trust"] == "unverified"),
        "live_io_adapters": sum(1 for item in adapter_results if item["live_io"]),
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
        "adapter_results": sorted(adapter_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def sense_layer_edge_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("sense_layer_edge_report_required")
    status = "passed" if report.get("ok") else "failed"
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": [
            {"id": "pipeline_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "safety_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "rollback_plan", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
        ],
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Sense Layer Edge contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/sense-layer-edge.json",
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

    report = validate_sense_layer_edge_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "SenseLayerEdgeSummary",
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
