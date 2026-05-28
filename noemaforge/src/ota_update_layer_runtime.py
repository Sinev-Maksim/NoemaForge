#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/ota_update_layer_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate offline OTA update contracts for staged rollout, rollback and health gates.
Inputs: noemaforge/configs/ota-update-layer.json plus local project/package roots.
Outputs: JSON-compatible OTAUpdateLayerReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_ota_update_layer_runtime.py
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


API_VERSION = "noemaforge.ota-update-layer/v1"
POLICY_KIND = "OTAUpdateLayerPolicy"
MANIFEST_KIND = "OTAUpdateManifest"
REPORT_KIND = "OTAUpdateLayerReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_TARGETS = {"model", "container", "gateway"}
VALID_STAGES = {"shadow", "canary", "stable"}
REQUIRED_HEALTH_CHECKS = {"health", "ready", "metrics"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
SHA256_RE = re.compile(r"^[A-Fa-f0-9]{64}$")


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


def _yaml_has(text: str, key: str, value: str) -> bool:
    return f"{key}: {value}" in text or f"- {value}" in text


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
        "require_staged_rollout",
        "require_rollback_bundle",
        "require_health_gate",
        "require_signed_model_manifest",
        "require_ci_release_evidence",
        "forbid_activation_without_health_gate",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    targets = set(_as_string_list(policy.get("allowed_targets")))
    stages = set(_as_string_list(policy.get("allowed_stages")))
    health_checks = set(_as_string_list(policy.get("required_health_checks")))
    if not targets:
        failures.append("policy_allowed_targets_empty")
    if not stages:
        failures.append("policy_allowed_stages_empty")
    if not health_checks:
        failures.append("policy_required_health_checks_empty")
    failures.extend(f"policy_invalid_target:{item}" for item in sorted(targets - VALID_TARGETS))
    failures.extend(f"policy_invalid_stage:{item}" for item in sorted(stages - VALID_STAGES))
    failures.extend(f"policy_required_health_check_unknown:{item}" for item in sorted(health_checks - REQUIRED_HEALTH_CHECKS))
    failures.extend(f"policy_required_health_check_missing:{item}" for item in sorted(REQUIRED_HEALTH_CHECKS - health_checks))
    return failures


def _load_json_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
    if not resolved.get("ok"):
        raise FileNotFoundError(ref)
    return json.loads(Path(str(resolved["path"])).read_text(encoding="utf-8"))


def _check_manifest_ref(ref: str, *, project_root: Path, package_root: Path, owner: str) -> List[str]:
    failures: List[str] = []
    try:
        manifest = _load_json_ref(ref, project_root=project_root, package_root=package_root)
    except Exception as exc:
        return [f"ota_signed_manifest_load_failed:{owner}:{ref}:{exc}"]
    if manifest.get("kind") != "SignedModelManifest":
        failures.append(f"ota_signed_manifest_kind_invalid:{owner}")
    if not SHA256_RE.match(str(manifest.get("sha256") or "")):
        failures.append(f"ota_signed_manifest_sha256_invalid:{owner}")
    if not str(manifest.get("signature") or "").strip():
        failures.append(f"ota_signed_manifest_signature_missing:{owner}")
    if not str(manifest.get("fallback") or ""):
        failures.append(f"ota_signed_manifest_fallback_missing:{owner}")
    return failures


def _check_release_evidence_ref(ref: str, *, project_root: Path, package_root: Path, owner: str) -> List[str]:
    failures: List[str] = []
    try:
        evidence = _load_json_ref(ref, project_root=project_root, package_root=package_root)
    except Exception as exc:
        return [f"ota_release_evidence_load_failed:{owner}:{ref}:{exc}"]
    if evidence.get("kind") != "ReleaseEvidence":
        failures.append(f"ota_release_evidence_kind_invalid:{owner}")
    checks = evidence.get("checks") if isinstance(evidence.get("checks"), list) else []
    if not checks:
        failures.append(f"ota_release_evidence_checks_empty:{owner}")
    failed = [str(item.get("id") or "<missing>") for item in checks if not isinstance(item, dict) or item.get("status") != "passed"]
    failures.extend(f"ota_release_evidence_check_not_passed:{owner}:{item}" for item in failed)
    return failures


def _check_yaml_ref(ref: str, *, project_root: Path, package_root: Path, owner: str, kind: str) -> List[str]:
    resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
    if not resolved.get("ok"):
        return [f"ota_yaml_ref_missing:{owner}:{ref}"]
    text = Path(str(resolved["path"])).read_text(encoding="utf-8")
    failures: List[str] = []
    if not _yaml_has(text, "apiVersion", API_VERSION):
        failures.append(f"ota_yaml_api_version_missing:{owner}:{ref}")
    if kind not in text:
        failures.append(f"ota_yaml_kind_missing:{owner}:{ref}:{kind}")
    return failures


def _bundle_failures(bundle: Dict[str, Any], *, owner: str, label: str) -> List[str]:
    failures: List[str] = []
    bundle_id = str(bundle.get("id") or "").strip()
    if not SAFE_ID_RE.match(bundle_id):
        failures.append(f"ota_{label}_bundle_id_invalid:{owner}")
    if str(bundle.get("kind") or "") not in VALID_TARGETS:
        failures.append(f"ota_{label}_bundle_kind_invalid:{owner}:{bundle.get('kind')}")
    if not str(bundle.get("version") or "").strip():
        failures.append(f"ota_{label}_bundle_version_missing:{owner}")
    if not SHA256_RE.match(str(bundle.get("sha256") or "")):
        failures.append(f"ota_{label}_bundle_sha256_invalid:{owner}")
    return failures


def _manifest_failures(manifest: Dict[str, Any], policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> List[str]:
    failures: List[str] = []
    manifest_id = str(manifest.get("id") or "").strip()
    owner = manifest_id or "<missing>"
    if manifest.get("apiVersion") != API_VERSION:
        failures.append(f"ota_manifest_api_version_invalid:{owner}")
    if manifest.get("kind") != MANIFEST_KIND:
        failures.append(f"ota_manifest_kind_invalid:{owner}")
    if not SAFE_ID_RE.match(manifest_id):
        failures.append(f"ota_manifest_id_invalid:{owner}")
    target = str(manifest.get("target") or "")
    if target not in set(_as_string_list(policy.get("allowed_targets"))) or target not in VALID_TARGETS:
        failures.append(f"ota_manifest_target_not_allowed:{owner}:{target}")
    if str(manifest.get("state") or "") not in VALID_STATUSES:
        failures.append(f"ota_manifest_state_invalid:{owner}:{manifest.get('state')}")

    staged = manifest.get("staged_rollout") if isinstance(manifest.get("staged_rollout"), dict) else {}
    stages = set(_as_string_list(staged.get("stages")))
    if policy.get("require_staged_rollout") is True and staged.get("enabled") is not True:
        failures.append(f"ota_staged_rollout_not_enabled:{owner}")
    if not stages:
        failures.append(f"ota_staged_rollout_stages_empty:{owner}")
    failures.extend(f"ota_staged_rollout_stage_not_allowed:{owner}:{item}" for item in sorted(stages - set(_as_string_list(policy.get("allowed_stages")))))
    if str(staged.get("current_stage") or "") not in stages:
        failures.append(f"ota_current_stage_not_in_stages:{owner}:{staged.get('current_stage')}")

    candidate = manifest.get("candidate_bundle") if isinstance(manifest.get("candidate_bundle"), dict) else {}
    previous = manifest.get("previous_bundle") if isinstance(manifest.get("previous_bundle"), dict) else {}
    failures.extend(_bundle_failures(candidate, owner=owner, label="candidate"))
    failures.extend(_bundle_failures(previous, owner=owner, label="previous"))
    if policy.get("require_rollback_bundle") is True and not previous.get("id"):
        failures.append(f"ota_previous_bundle_missing:{owner}")

    for label, bundle in [("candidate", candidate), ("previous", previous)]:
        manifest_ref = str(bundle.get("signed_model_manifest_ref") or "")
        if policy.get("require_signed_model_manifest") is True:
            if not _is_safe_relative_ref(manifest_ref):
                failures.append(f"ota_{label}_signed_manifest_ref_unsafe:{owner}:{manifest_ref}")
            else:
                failures.extend(_check_manifest_ref(manifest_ref, project_root=project_root, package_root=package_root, owner=f"{owner}:{label}"))

    evidence_ref = str(candidate.get("release_evidence_ref") or "")
    if policy.get("require_ci_release_evidence") is True:
        if not _is_safe_relative_ref(evidence_ref):
            failures.append(f"ota_release_evidence_ref_unsafe:{owner}:{evidence_ref}")
        else:
            failures.extend(_check_release_evidence_ref(evidence_ref, project_root=project_root, package_root=package_root, owner=owner))

    rollback = manifest.get("rollback") if isinstance(manifest.get("rollback"), dict) else {}
    if rollback.get("enabled") is not True:
        failures.append(f"ota_rollback_not_enabled:{owner}")
    if str(rollback.get("failure_action") or "") != "rollback_previous_bundle":
        failures.append(f"ota_rollback_failure_action_invalid:{owner}:{rollback.get('failure_action')}")
    rollback_ref = str(rollback.get("policy_ref") or "")
    if _is_safe_relative_ref(rollback_ref):
        failures.extend(_check_yaml_ref(rollback_ref, project_root=project_root, package_root=package_root, owner=owner, kind="OTARollbackPolicy"))
    else:
        failures.append(f"ota_rollback_policy_ref_unsafe:{owner}:{rollback_ref}")

    gate = manifest.get("health_gate") if isinstance(manifest.get("health_gate"), dict) else {}
    checks = gate.get("checks") if isinstance(gate.get("checks"), list) else []
    check_ids = {str(item.get("id") or "") for item in checks if isinstance(item, dict)}
    required_checks = set(_as_string_list(policy.get("required_health_checks")))
    if policy.get("require_health_gate") is True and gate.get("required") is not True:
        failures.append(f"ota_health_gate_not_required:{owner}")
    if gate.get("status") != "passed":
        failures.append(f"ota_health_gate_not_passed:{owner}")
    failures.extend(f"ota_health_gate_check_missing:{owner}:{item}" for item in sorted(required_checks - check_ids))
    failures.extend(
        f"ota_health_gate_check_not_passed:{owner}:{item.get('id', '<missing>')}"
        for item in checks
        if not isinstance(item, dict) or item.get("status") != "passed"
    )
    activation = manifest.get("activation") if isinstance(manifest.get("activation"), dict) else {}
    if activation.get("enabled") is True and activation.get("requires_health_gate") is not True:
        failures.append(f"ota_activation_without_health_gate:{owner}")
    if activation.get("activated") is True and gate.get("status") != "passed":
        failures.append(f"ota_activated_without_passed_health_gate:{owner}")
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


def validate_ota_update_layer_policy(
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
    manifest_refs = payload.get("update_manifests") if isinstance(payload.get("update_manifests"), list) else []
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    if not manifest_refs:
        failures.append("update_manifests_empty")

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    manifest_results: List[Dict[str, Any]] = []

    policy_refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(policy_refs["failures"])
    all_resolved_refs.extend(policy_refs["resolved_refs"])
    all_missing_refs.extend(policy_refs["missing_refs"])
    all_unsafe_refs.extend(policy_refs["unsafe_refs"])

    for item in manifest_refs:
        if not isinstance(item, dict):
            failures.append("update_manifest_ref_not_object")
            continue
        manifest_id = str(item.get("id") or "<missing>")
        ref = str(item.get("ref") or "")
        manifest_failures: List[str] = []
        manifest_payload: Dict[str, Any] = {}
        if not _is_safe_relative_ref(ref):
            manifest_failures.append(f"ota_manifest_ref_unsafe:{manifest_id}:{ref}")
        else:
            resolved = _resolve_ref(ref, project_root=project, package_root=package)
            resolved["owner"] = manifest_id
            if resolved.get("ok"):
                all_resolved_refs.append(resolved)
                try:
                    manifest_payload = json.loads(Path(str(resolved["path"])).read_text(encoding="utf-8"))
                    manifest_failures.extend(_manifest_failures(manifest_payload, policy, project_root=project, package_root=package))
                except Exception as exc:
                    manifest_failures.append(f"ota_manifest_load_failed:{manifest_id}:{exc}")
            else:
                all_missing_refs.append(resolved)
                manifest_failures.append(f"missing_ref:{manifest_id}:{ref}")
        refs = _as_string_list(manifest_payload.get("refs")) if manifest_payload else []
        refs_result = _resolve_refs(refs, project_root=project, package_root=package, owner=manifest_id)
        manifest_failures.extend(refs_result["failures"])
        failures.extend(manifest_failures)
        all_resolved_refs.extend(refs_result["resolved_refs"])
        all_missing_refs.extend(refs_result["missing_refs"])
        all_unsafe_refs.extend(refs_result["unsafe_refs"])
        gate = manifest_payload.get("health_gate") if isinstance(manifest_payload.get("health_gate"), dict) else {}
        manifest_results.append(
            {
                "id": manifest_id,
                "ok": not manifest_failures,
                "target": str(manifest_payload.get("target") or ""),
                "staged_rollout": (manifest_payload.get("staged_rollout") if isinstance(manifest_payload.get("staged_rollout"), dict) else {}).get("enabled") is True,
                "rollback": (manifest_payload.get("rollback") if isinstance(manifest_payload.get("rollback"), dict) else {}).get("enabled") is True,
                "health_gate": gate.get("status") == "passed",
                "activation_enabled": (manifest_payload.get("activation") if isinstance(manifest_payload.get("activation"), dict) else {}).get("enabled") is True,
                "failures": sorted(set(manifest_failures)),
            }
        )

    checks = [
        {"id": "staged_rollout", "status": "passed" if not any("staged_rollout" in item for item in failures) else "failed"},
        {"id": "rollback", "status": "passed" if not any("rollback" in item or "previous_bundle" in item for item in failures) else "failed"},
        {"id": "health_gate", "status": "passed" if not any("health_gate" in item or "activation_without_health_gate" in item for item in failures) else "failed"},
        {"id": "signed_model_manifest", "status": "passed" if not any("signed_manifest" in item for item in failures) else "failed"},
        {"id": "ci_release_evidence", "status": "passed" if not any("release_evidence" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "update_manifests": len(manifest_results),
        "passing_update_manifests": sum(1 for item in manifest_results if item["ok"]),
        "staged_rollouts": sum(1 for item in manifest_results if item["staged_rollout"]),
        "rollback_enabled": sum(1 for item in manifest_results if item["rollback"]),
        "health_gates_passed": sum(1 for item in manifest_results if item["health_gate"]),
        "activation_enabled": sum(1 for item in manifest_results if item["activation_enabled"]),
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
        "manifest_results": sorted(manifest_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def ota_update_layer_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("ota_update_layer_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge OTA update layer contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/ota-update-layer.json",
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

    report = validate_ota_update_layer_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "OTAUpdateLayerSummary",
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
