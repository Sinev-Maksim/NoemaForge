#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/signed_model_manifest_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate signed model manifests before model attachment or deployment consideration.
Inputs: noemaforge/configs/signed-model-manifest-policy.json plus local project/package roots.
Outputs: JSON-compatible SignedModelManifestReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_signed_model_manifest_runtime.py
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
from typing import Any, Dict, Iterable, List, Optional, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import production_ai_contracts as pac


API_VERSION = "noemaforge.signed-model-manifest/v1"
POLICY_KIND = "SignedModelManifestPolicy"
MANIFEST_KIND = "SignedModelManifest"
REPORT_KIND = "SignedModelManifestReport"

VALID_POLICY_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_MANIFEST_STATUSES = {"draft", "shadow", "canary", "stable", "retired"}
VALID_TARGET_TYPES = {"edge", "gateway", "local_model"}
VALID_RUNTIMES = {"onnx", "tflm", "llama.cpp", "python", "mock"}
VALID_SIGNATURE_SCHEMES = {"sha256-selftest", "cosign", "minisign", "pgp"}
VALID_ROLLOUTS = {"shadow", "canary", "stable"}
VALID_FALLBACKS = {"whitebox", "previous_model", "manual_review"}
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


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


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


def load_manifest(manifest_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
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

    for key in [
        "require_sha256",
        "require_signature",
        "require_input_contract",
        "require_output_contract",
        "require_resource_budgets",
        "require_whitebox_fallback",
        "require_rollout_state",
        "require_independent_qa_gate",
        "require_qa_can_block_release",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")

    runtimes = set(_as_string_list(policy.get("allowed_runtimes")))
    schemes = set(_as_string_list(policy.get("allowed_signature_schemes")))
    rollouts = set(_as_string_list(policy.get("allowed_rollouts")))
    fallbacks = set(_as_string_list(policy.get("allowed_fallbacks")))
    deployable = set(_as_string_list(policy.get("deployable_rollouts")))
    qa_statuses = set(_as_string_list(policy.get("qa_approved_statuses")))
    if not runtimes:
        failures.append("policy_allowed_runtimes_empty")
    if not schemes:
        failures.append("policy_allowed_signature_schemes_empty")
    if not rollouts:
        failures.append("policy_allowed_rollouts_empty")
    if not fallbacks:
        failures.append("policy_allowed_fallbacks_empty")
    if not deployable:
        failures.append("policy_deployable_rollouts_empty")
    if not qa_statuses:
        failures.append("policy_qa_approved_statuses_empty")
    failures.extend(f"policy_invalid_runtime:{item}" for item in sorted(runtimes - VALID_RUNTIMES))
    failures.extend(f"policy_invalid_signature_scheme:{item}" for item in sorted(schemes - VALID_SIGNATURE_SCHEMES))
    failures.extend(f"policy_invalid_rollout:{item}" for item in sorted(rollouts - VALID_ROLLOUTS))
    failures.extend(f"policy_invalid_fallback:{item}" for item in sorted(fallbacks - VALID_FALLBACKS))
    failures.extend(f"policy_deployable_rollout_not_allowed:{item}" for item in sorted(deployable - rollouts))
    return failures


def _manifest_failures(manifest: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    manifest_id = str(manifest.get("id") or "").strip()
    owner = manifest_id or "<missing>"
    if manifest.get("apiVersion") != API_VERSION:
        failures.append(f"manifest_api_version_invalid:{owner}")
    if manifest.get("kind") != MANIFEST_KIND:
        failures.append(f"manifest_kind_invalid:{owner}")
    if not SAFE_ID_RE.match(manifest_id):
        failures.append(f"manifest_id_invalid:{owner}")
    if not SAFE_ID_RE.match(str(manifest.get("model_id") or "")):
        failures.append(f"manifest_model_id_invalid:{owner}")
    if str(manifest.get("status") or "") not in VALID_MANIFEST_STATUSES:
        failures.append(f"manifest_status_invalid:{owner}:{manifest.get('status')}")
    target_type = str(manifest.get("target_type") or "")
    if target_type not in VALID_TARGET_TYPES:
        failures.append(f"manifest_target_type_invalid:{owner}:{target_type}")
    if not REGISTRY_REF_RE.match(str(manifest.get("model_ref") or "")):
        failures.append(f"manifest_model_ref_invalid:{owner}")

    runtime = str(manifest.get("runtime") or "")
    if runtime not in set(_as_string_list(policy.get("allowed_runtimes"))) or runtime not in VALID_RUNTIMES:
        failures.append(f"manifest_runtime_not_allowed:{owner}:{runtime}")
    if not str(manifest.get("artifact_uri") or "").strip():
        failures.append(f"manifest_artifact_uri_missing:{owner}")
    if not SHA256_RE.match(str(manifest.get("sha256") or "")):
        failures.append(f"manifest_sha256_invalid:{owner}")
    scheme = str(manifest.get("signature_scheme") or "")
    if scheme not in set(_as_string_list(policy.get("allowed_signature_schemes"))) or scheme not in VALID_SIGNATURE_SCHEMES:
        failures.append(f"manifest_signature_scheme_not_allowed:{owner}:{scheme}")
    if not str(manifest.get("signature") or "").strip():
        failures.append(f"manifest_signature_missing:{owner}")
    elif scheme and not str(manifest.get("signature") or "").startswith(f"{scheme}:"):
        failures.append(f"manifest_signature_scheme_prefix_mismatch:{owner}")
    if not str(manifest.get("input_contract") or "").strip():
        failures.append(f"manifest_input_contract_missing:{owner}")
    if not str(manifest.get("output_contract") or "").strip():
        failures.append(f"manifest_output_contract_missing:{owner}")

    budgets = manifest.get("budgets") if isinstance(manifest.get("budgets"), dict) else {}
    if _as_float(budgets.get("latency_budget_ms"), -1.0) <= 0:
        failures.append(f"manifest_latency_budget_invalid:{owner}")
    if _as_float(budgets.get("memory_budget_mb"), -1.0) <= 0:
        failures.append(f"manifest_memory_budget_invalid:{owner}")
    if _as_int(budgets.get("max_artifact_bytes"), -1) <= 0:
        failures.append(f"manifest_artifact_budget_invalid:{owner}")

    fallback = str(manifest.get("fallback") or "")
    rollout = str(manifest.get("rollout") or "")
    if fallback not in set(_as_string_list(policy.get("allowed_fallbacks"))) or fallback not in VALID_FALLBACKS:
        failures.append(f"manifest_fallback_not_allowed:{owner}:{fallback}")
    if policy.get("require_whitebox_fallback") is True and target_type == "edge" and fallback != "whitebox":
        failures.append(f"manifest_edge_fallback_not_whitebox:{owner}")
    if rollout not in set(_as_string_list(policy.get("allowed_rollouts"))) or rollout not in VALID_ROLLOUTS:
        failures.append(f"manifest_rollout_not_allowed:{owner}:{rollout}")

    qa_gate = manifest.get("qa_gate") if isinstance(manifest.get("qa_gate"), dict) else {}
    if qa_gate.get("required") is not True:
        failures.append(f"manifest_qa_gate_not_required:{owner}")
    if str(qa_gate.get("reviewer_role") or "") != "qa":
        failures.append(f"manifest_qa_reviewer_not_qa:{owner}")
    if str(qa_gate.get("developer_role") or "") == str(qa_gate.get("reviewer_role") or ""):
        failures.append(f"manifest_qa_not_independent_from_developer:{owner}")
    if qa_gate.get("independent_from_developer") is not True:
        failures.append(f"manifest_qa_independent_flag_missing:{owner}")
    if qa_gate.get("can_block_release") is not True:
        failures.append(f"manifest_qa_cannot_block_release:{owner}")
    if qa_gate.get("review_required") is not True:
        failures.append(f"manifest_qa_review_not_required:{owner}")
    approved_statuses = set(_as_string_list(policy.get("qa_approved_statuses")))
    qa_status = str(qa_gate.get("status") or "")
    deployable_rollouts = set(_as_string_list(policy.get("deployable_rollouts")))
    if rollout in deployable_rollouts and qa_status not in approved_statuses:
        failures.append(f"manifest_deployable_without_qa_approval:{owner}:{qa_status}")
    review_ref = str(qa_gate.get("review_ref") or "")
    if not review_ref.strip():
        failures.append(f"manifest_qa_review_ref_missing:{owner}")
    elif not _is_safe_relative_ref(review_ref):
        failures.append(f"manifest_qa_review_ref_unsafe:{owner}:{review_ref}")
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
    return {
        "failures": failures,
        "resolved_refs": resolved_refs,
        "missing_refs": missing_refs,
        "unsafe_refs": unsafe_refs,
    }


def validate_signed_model_manifest_policy(
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
    manifest_refs = payload.get("manifest_refs") if isinstance(payload.get("manifest_refs"), list) else []
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    if not manifest_refs:
        failures.append("manifest_refs_empty")

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
            failures.append("manifest_ref_not_object")
            continue
        expected_id = str(item.get("id") or "").strip()
        ref = str(item.get("ref") or "").strip()
        owner = expected_id or ref or "<missing>"
        refs_result = _resolve_refs([ref], project_root=project, package_root=package, owner=owner)
        failures.extend(refs_result["failures"])
        all_resolved_refs.extend(refs_result["resolved_refs"])
        all_missing_refs.extend(refs_result["missing_refs"])
        all_unsafe_refs.extend(refs_result["unsafe_refs"])
        if refs_result["missing_refs"] or refs_result["unsafe_refs"]:
            manifest_results.append({"id": owner, "ok": False, "ref": ref, "failures": refs_result["failures"]})
            continue
        manifest_path = Path(refs_result["resolved_refs"][0]["path"])
        try:
            manifest = load_manifest(manifest_path)
        except Exception as exc:
            reason = f"manifest_load_failed:{owner}:{exc}"
            failures.append(reason)
            manifest_results.append({"id": owner, "ok": False, "ref": ref, "failures": [reason]})
            continue

        manifest_id = str(manifest.get("id") or owner)
        manifest_failures = _manifest_failures(manifest, policy)
        if expected_id and manifest_id != expected_id:
            manifest_failures.append(f"manifest_id_mismatch:{expected_id}:{manifest_id}")
        manifest_internal_refs = _as_string_list(manifest.get("refs"))
        review_ref = str((manifest.get("qa_gate") or {}).get("review_ref") or "") if isinstance(manifest.get("qa_gate"), dict) else ""
        if review_ref and review_ref not in manifest_internal_refs:
            manifest_internal_refs.append(review_ref)
        manifest_refs_result = _resolve_refs(manifest_internal_refs, project_root=project, package_root=package, owner=manifest_id)
        manifest_failures.extend(manifest_refs_result["failures"])
        all_resolved_refs.extend(manifest_refs_result["resolved_refs"])
        all_missing_refs.extend(manifest_refs_result["missing_refs"])
        all_unsafe_refs.extend(manifest_refs_result["unsafe_refs"])
        failures.extend(manifest_failures)

        budgets = manifest.get("budgets") if isinstance(manifest.get("budgets"), dict) else {}
        qa_gate = manifest.get("qa_gate") if isinstance(manifest.get("qa_gate"), dict) else {}
        manifest_results.append(
            {
                "id": manifest_id,
                "ok": not manifest_failures,
                "ref": ref,
                "model_ref": str(manifest.get("model_ref") or ""),
                "runtime": str(manifest.get("runtime") or ""),
                "rollout": str(manifest.get("rollout") or ""),
                "fallback": str(manifest.get("fallback") or ""),
                "signed": bool(str(manifest.get("signature") or "").strip()),
                "has_sha256": bool(SHA256_RE.match(str(manifest.get("sha256") or ""))),
                "latency_budget_ms": _as_float(budgets.get("latency_budget_ms"), 0.0),
                "memory_budget_mb": _as_float(budgets.get("memory_budget_mb"), 0.0),
                "qa_can_block_release": bool(qa_gate.get("can_block_release")),
                "qa_status": str(qa_gate.get("status") or ""),
                "failures": sorted(set(manifest_failures)),
            }
        )

    checks = [
        {"id": "sha256_required", "status": "passed" if not any("sha256" in item for item in failures) else "failed"},
        {"id": "signature_required", "status": "passed" if not any("signature" in item for item in failures) else "failed"},
        {"id": "resource_budgets", "status": "passed" if not any("budget" in item for item in failures) else "failed"},
        {"id": "qa_blocker", "status": "passed" if not any("qa" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "manifests": len(manifest_results),
        "passing_manifests": sum(1 for item in manifest_results if item["ok"]),
        "signed_manifests": sum(1 for item in manifest_results if item.get("signed")),
        "sha256_manifests": sum(1 for item in manifest_results if item.get("has_sha256")),
        "budgeted_manifests": sum(1 for item in manifest_results if item.get("latency_budget_ms", 0) > 0 and item.get("memory_budget_mb", 0) > 0),
        "qa_blocker_ready_manifests": sum(1 for item in manifest_results if item.get("qa_can_block_release")),
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


def signed_model_manifest_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("signed_model_manifest_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge signed model manifest contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/signed-model-manifest-policy.json",
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

    report = validate_signed_model_manifest_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "SignedModelManifestSummary",
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
