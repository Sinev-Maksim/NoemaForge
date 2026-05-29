#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/edge_tinyml_ota_pack_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the aggregate Edge/TinyML/OTA offline release contract.
Inputs: edge-tinyml-ota-pack policy plus component Edge/TinyML/Gateway/OTA policies.
Outputs: JSON-compatible EdgeTinyMLOTAPackValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_edge_tinyml_ota_pack_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import edge_reference_targets_runtime as ert
import edge_rules_engine_runtime as ere
import gateway_inference_service_runtime as gis
import ota_update_layer_runtime as ota
import sense_layer_edge_runtime as sle
import tinyml_node_runtime as tml


API_VERSION = "noemaforge.edge-tinyml-ota-pack/v1"
POLICY_KIND = "EdgeTinyMLOTAPackPolicy"
REPORT_KIND = "EdgeTinyMLOTAPackValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")

COMPONENT_VALIDATORS: Dict[str, tuple[Any, Callable[..., Dict[str, Any]]]] = {
    "sense-layer-edge-core": (sle, sle.validate_sense_layer_edge_policy),
    "tinyml-node-core": (tml, tml.validate_tinyml_node_policy),
    "gateway-inference-service-core": (gis, gis.validate_gateway_inference_service_policy),
    "edge-rules-engine-core": (ere, ere.validate_edge_rules_engine_policy),
    "ota-update-layer-core": (ota, ota.validate_ota_update_layer_policy),
    "edge-reference-targets-core": (ert, ert.validate_edge_reference_targets_policy),
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
    if str(policy.get("mode") or "") != "offline_aggregate_contract":
        failures.append("policy_mode_not_offline_aggregate_contract")
    if str(policy.get("activation_state") or "") != "aggregate_components_shadow_ready":
        failures.append("policy_activation_state_invalid")
    for key in [
        "require_docs_and_changelog_refs",
        "require_no_live_edge_dependency",
        "require_mqtt_serial_ingestion",
        "require_tinyml_validation",
        "require_gateway_inference",
        "require_rules_engine",
        "require_manifest_signing",
        "require_ota_rollback",
        "forbid_live_device_required",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    components = policy.get("required_components") if isinstance(policy.get("required_components"), list) else []
    if len(components) < 6:
        failures.append("policy_required_components_incomplete")
    for component in components:
        cid = str(component.get("id") or "")
        if cid not in COMPONENT_VALIDATORS:
            failures.append(f"policy_unknown_component:{cid}")
        if not _is_safe_relative_ref(str(component.get("config") or "")):
            failures.append(f"policy_component_config_ref_invalid:{cid}")
        if not _is_safe_relative_ref(str(component.get("runtime") or "")):
            failures.append(f"policy_component_runtime_ref_invalid:{cid}")
        if not _as_string_list(component.get("capabilities")):
            failures.append(f"policy_component_capabilities_empty:{cid}")
    if not _as_string_list(policy.get("required_pack_tokens")):
        failures.append("policy_required_pack_tokens_empty")
    return failures


def _component_report(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    components: List[Dict[str, Any]] = []
    all_capabilities: List[str] = []
    component_ids: List[str] = []
    for component in policy.get("required_components", []):
        cid = str(component.get("id") or "")
        module, validator = COMPONENT_VALIDATORS.get(cid, (None, None))  # type: ignore[assignment]
        config_ref = str(component.get("config") or "")
        component_ids.append(cid)
        resolved = _resolve_ref(config_ref, project_root=project_root, package_root=package_root)
        component_failures: List[str] = []
        report: Dict[str, Any] = {}
        if not resolved.get("ok"):
            component_failures.append(f"component_config_missing:{cid}:{config_ref}")
        elif module is None or validator is None:
            component_failures.append(f"component_validator_missing:{cid}")
        else:
            payload = module.load_policy(resolved["path"])
            if payload.get("id") != cid:
                component_failures.append(f"component_id_mismatch:{cid}:{payload.get('id')}")
            if payload.get("version") != "0.32.2":
                component_failures.append(f"component_version_invalid:{cid}:{payload.get('version')}")
            report = validator(payload, project_root=project_root, package_root=package_root, policy_path=resolved["path"])
            if report.get("ok") is not True:
                component_failures.append(f"component_report_failed:{cid}")
                component_failures.extend(f"{cid}:{item}" for item in report.get("failures", []))
        all_capabilities.extend(_as_string_list(component.get("capabilities")))
        failures.extend(component_failures)
        components.append(
            {
                "id": cid,
                "ok": not component_failures,
                "config": config_ref,
                "resolved": resolved,
                "capabilities": _as_string_list(component.get("capabilities")),
                "failures": component_failures,
                "metrics": report.get("metrics", {}) if isinstance(report, dict) else {},
            }
        )
    capability_text = " ".join(all_capabilities + component_ids).lower()
    required_capabilities = [
        "mqtt",
        "serial",
        "golden_vectors",
        "gateway",
        "rule_guard",
        "rollback_bundle",
        "manifest",
    ]
    for token in required_capabilities:
        if token not in capability_text:
            failures.append(f"aggregate_capability_missing:{token}")
    return {"failures": failures, "components": components, "capabilities": sorted(set(all_capabilities))}


def _registry_report(policy: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    path = package_root / "configs" / "unified-registry.json"
    text = load_text(path) if path.exists() else ""
    if not text:
        failures.append("unified_registry_missing")
    for component in policy.get("required_components", []):
        cid = str(component.get("id") or "")
        ref = f"eval-pack:{cid}:0.32.2"
        if ref not in text:
            failures.append(f"registry_eval_pack_ref_missing:{ref}")
    return {"failures": failures, "path": _display_path(path), "chars": len(text)}


def _docs_report(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    docs = [
        project_root / "TODO.md",
        package_root / "TODO.md",
        project_root / "docs" / "TODO.md",
        package_root / "docs" / "TODO.md",
        project_root / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        package_root / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        project_root / "CHANGELOG.md",
        project_root / "RELEASE_NOTES.md",
        project_root / "docs" / "history" / "CHANGELOG.md",
        package_root / "docs" / "history" / "CHANGELOG.md",
    ]
    tokens = [
        str(payload.get("id") or ""),
        "Edge/TinyML/OTA pack: MQTT/serial, TinyML validation, gateway inference, rules, manifest signing and OTA rollback",
        "offline aggregate contract",
    ]
    reports: List[Dict[str, Any]] = []
    for path in docs:
        text = load_text(path) if path.exists() else ""
        missing = [token for token in tokens if token and token not in text]
        if missing:
            failures.append(f"docs_tokens_missing:{_display_path(path)}:{','.join(missing)}")
        reports.append({"path": _display_path(path), "ok": not missing, "missing": missing})
    return {"failures": failures, "reports": reports}


def validate_edge_tinyml_ota_pack_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Path | str | None = None,
    include_docs: bool = True,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(ref_report["failures"])
    components = _component_report(policy, project_root=project, package_root=package)
    failures.extend(components["failures"])
    registry = _registry_report(policy, package_root=package)
    failures.extend(registry["failures"])
    docs = _docs_report(payload, project_root=project, package_root=package) if include_docs else {"failures": [], "reports": []}
    failures.extend(docs["failures"])
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "components": len(components["components"]),
        "valid_components": sum(1 for item in components["components"] if item.get("ok")),
        "capabilities": len(components["capabilities"]),
        "registry_chars": registry["chars"],
        "docs_reports": len(docs["reports"]),
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
        "components": components,
        "registry": registry,
        "docs": docs,
    }


def benchmark_edge_tinyml_ota_pack(*, package_root: Path | str, iterations: int = 20) -> Dict[str, Any]:
    root = Path(package_root).resolve()
    policy = load_policy(root / "configs" / "edge-tinyml-ota-pack-policy.json")
    started = time.perf_counter()
    failures = 0
    for _ in range(iterations):
        report = validate_edge_tinyml_ota_pack_policy(policy, project_root=root.parent, package_root=root, include_docs=False)
        if not report.get("ok"):
            failures += 1
    elapsed = time.perf_counter() - started
    return {
        "ok": failures == 0,
        "iterations": iterations,
        "failures": failures,
        "elapsed_seconds": round(elapsed, 6),
        "iterations_per_second": round(iterations / elapsed, 3) if elapsed else iterations,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "EdgeTinyMLOTAPackValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Edge/TinyML/OTA aggregate pack contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "edge-tinyml-ota-pack-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--skip-docs", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_edge_tinyml_ota_pack_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
        include_docs=not args.skip_docs,
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

