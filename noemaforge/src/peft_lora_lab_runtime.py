#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/peft_lora_lab_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate disabled PEFT/LoRA lab readiness gates without training or weight mutation.
Inputs: noemaforge/configs/peft-lora-lab-policy.json plus local project/package roots.
Outputs: JSON-compatible PEFTLoRALabValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_peft_lora_lab_runtime.py
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


API_VERSION = "noemaforge.peft-lora-lab/v1"
POLICY_KIND = "PEFTLoRALabPolicy"
REPORT_KIND = "PEFTLoRALabValidationReport"

VALID_STATUSES = {"disabled", "draft", "shadow", "retired"}
VALID_LAB_STATES = {"disabled", "draft", "shadow", "canary", "enabled", "retired"}
ACTIVE_LAB_STATES = {"shadow", "canary", "enabled"}
VALID_METHODS = {"lora", "qlora"}
VALID_FORMATS = {"json", "safetensors"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
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
    path = Path(policy_path)
    return json.loads(path.read_text(encoding="utf-8"))


def _policy_failures(policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    required_false = ["training_enabled", "weight_mutation_enabled"]
    required_true = [
        "require_evaluation_gate",
        "require_release_evidence_before_training",
        "require_rollback_manifest",
        "require_dataset_manifest",
        "require_operator_review",
        "require_trace_id",
        "require_resource_guard",
    ]
    if str(policy.get("mode") or "") != "readiness_only":
        failures.append("policy_mode_not_readiness_only")
    if str(policy.get("default_state") or "") != "disabled":
        failures.append("policy_default_state_not_disabled")
    if str(policy.get("network") or "") != "deny":
        failures.append("policy_network_not_deny")
    for key in required_false:
        if policy.get(key) is not False:
            failures.append(f"policy_{key}_not_false")
    for key in required_true:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    formats = set(_as_string_list(policy.get("allowed_artifact_formats")))
    methods = set(_as_string_list(policy.get("allowed_adapter_methods")))
    if not formats:
        failures.append("policy_allowed_artifact_formats_empty")
    if not methods:
        failures.append("policy_allowed_adapter_methods_empty")
    failures.extend(f"policy_invalid_artifact_format:{item}" for item in sorted(formats - VALID_FORMATS))
    failures.extend(f"policy_invalid_adapter_method:{item}" for item in sorted(methods - VALID_METHODS))
    try:
        rank = int(policy.get("max_adapter_rank"))
    except Exception:
        rank = 0
    if rank < 1 or rank > 64:
        failures.append("policy_max_adapter_rank_invalid")
    baseline_refs = _as_string_list(policy.get("baseline_eval_pack_refs"))
    if not baseline_refs:
        failures.append("policy_baseline_eval_pack_refs_empty")
    for ref in baseline_refs:
        if not ref.startswith("eval-pack:"):
            failures.append(f"policy_baseline_eval_pack_ref_invalid:{ref}")
    return failures


def _lab_failures(lab: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    lab_id = str(lab.get("id") or "").strip()
    owner = lab_id or "<missing>"
    if not SAFE_ID_RE.match(lab_id):
        failures.append(f"lab_id_invalid:{owner}")
    state = str(lab.get("state") or policy.get("default_state") or "").strip()
    if state not in VALID_LAB_STATES:
        failures.append(f"lab_state_invalid:{owner}:{state}")
    if not REGISTRY_REF_RE.match(str(lab.get("target_model_ref") or "")):
        failures.append(f"lab_target_model_ref_invalid:{owner}")
    method = str(lab.get("adapter_method") or "")
    if method not in set(_as_string_list(policy.get("allowed_adapter_methods"))) or method not in VALID_METHODS:
        failures.append(f"lab_adapter_method_not_allowed:{owner}:{method}")
    try:
        rank = int(lab.get("adapter_rank"))
    except Exception:
        rank = 0
    if rank < 1 or rank > int(policy.get("max_adapter_rank") or 0):
        failures.append(f"lab_adapter_rank_invalid:{owner}:{rank}")
    if str(lab.get("network") or "") != "deny":
        failures.append(f"lab_network_not_deny:{owner}")

    training = lab.get("training_plan") if isinstance(lab.get("training_plan"), dict) else {}
    if training.get("enabled") is not False:
        failures.append(f"lab_training_enabled:{owner}")
    if str(training.get("mode") or "") != "dry_run":
        failures.append(f"lab_training_mode_not_dry_run:{owner}")
    if training.get("writes_production_weights") is not False:
        failures.append(f"lab_writes_production_weights:{owner}")
    if training.get("writes_adapter_artifact") is not False:
        failures.append(f"lab_writes_adapter_artifact:{owner}")
    output_format = str(training.get("output_format") or "")
    if output_format not in set(_as_string_list(policy.get("allowed_artifact_formats"))) or output_format not in VALID_FORMATS:
        failures.append(f"lab_output_format_not_allowed:{owner}:{output_format}")

    dataset = lab.get("dataset_manifest") if isinstance(lab.get("dataset_manifest"), dict) else {}
    if dataset.get("required") is not True:
        failures.append(f"lab_dataset_manifest_not_required:{owner}")
    if not str(dataset.get("dataset_ref") or "").strip():
        failures.append(f"lab_dataset_ref_missing:{owner}")
    if str(dataset.get("classification") or "") != "eval_only":
        failures.append(f"lab_dataset_not_eval_only:{owner}")
    if dataset.get("approved_for_training") is not False:
        failures.append(f"lab_dataset_approved_for_training:{owner}")

    gate = lab.get("evaluation_gate") if isinstance(lab.get("evaluation_gate"), dict) else {}
    if gate.get("required") is not True:
        failures.append(f"lab_evaluation_gate_not_required:{owner}")
    if str(gate.get("domain") or "") != "model":
        failures.append(f"lab_evaluation_gate_domain_not_model:{owner}")
    eval_pack_refs = _as_string_list(gate.get("eval_pack_refs"))
    if not eval_pack_refs:
        failures.append(f"lab_eval_pack_refs_empty:{owner}")
    for ref in eval_pack_refs:
        if not ref.startswith("eval-pack:"):
            failures.append(f"lab_eval_pack_ref_invalid:{owner}:{ref}")

    guard = lab.get("resource_guard") if isinstance(lab.get("resource_guard"), dict) else {}
    if guard.get("required") is not True:
        failures.append(f"lab_resource_guard_not_required:{owner}")
    if guard.get("single_active_llm") is not True:
        failures.append(f"lab_single_active_llm_not_required:{owner}")
    if str(guard.get("gpu_policy") or "") != "explicit_only":
        failures.append(f"lab_gpu_policy_not_explicit_only:{owner}")
    try:
        max_training_minutes = int(guard.get("max_training_minutes"))
    except Exception:
        max_training_minutes = -1
    if max_training_minutes != 0:
        failures.append(f"lab_max_training_minutes_not_zero:{owner}")

    rollback = lab.get("rollback_manifest") if isinstance(lab.get("rollback_manifest"), dict) else {}
    if rollback.get("required") is not True:
        failures.append(f"lab_rollback_manifest_not_required:{owner}")
    if not REGISTRY_REF_RE.match(str(rollback.get("restore_target") or "")):
        failures.append(f"lab_rollback_restore_target_invalid:{owner}")
    if not _as_string_list(rollback.get("steps")):
        failures.append(f"lab_rollback_steps_empty:{owner}")

    review = lab.get("review") if isinstance(lab.get("review"), dict) else {}
    if review.get("required") is not True:
        failures.append(f"lab_review_not_required:{owner}")
    if not str(review.get("route") or "").strip():
        failures.append(f"lab_review_route_missing:{owner}")
    if not _as_string_list(review.get("reviewers")):
        failures.append(f"lab_reviewers_missing:{owner}")

    evidence = lab.get("release_evidence") if isinstance(lab.get("release_evidence"), dict) else {}
    if evidence.get("required_before_training") is not True:
        failures.append(f"lab_release_evidence_not_required:{owner}")
    if state in ACTIVE_LAB_STATES and not str(evidence.get("evidence_ref") or "").strip():
        failures.append(f"lab_active_without_release_evidence:{owner}")
    if state in ACTIVE_LAB_STATES and training.get("enabled") is True:
        failures.append(f"lab_active_training_enabled:{owner}")
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


def validate_peft_lora_lab_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Optional[Path | str] = None,
    policy_path: Path | str = "",
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root or (project / "noemaforge"))
    failures: List[str] = []
    if not isinstance(payload, dict):
        failures.append("policy_payload_not_object")
        return {
            "apiVersion": API_VERSION,
            "kind": REPORT_KIND,
            "ok": False,
            "created_at": _nowz(),
            "policy_path": str(policy_path or ""),
            "failures": failures,
            "metrics": {},
            "lab_results": [],
        }

    if payload.get("apiVersion") != API_VERSION:
        failures.append(f"policy_api_version_invalid:{payload.get('apiVersion')}")
    if payload.get("kind") != POLICY_KIND:
        failures.append(f"policy_kind_invalid:{payload.get('kind')}")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append(f"policy_status_invalid:{payload.get('status')}")
    if not str(payload.get("id") or "").strip():
        failures.append("policy_id_missing")

    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    if not policy:
        failures.append("policy_missing")
    failures.extend(_policy_failures(policy))

    labs = payload.get("labs") if isinstance(payload.get("labs"), list) else []
    if not labs:
        failures.append("labs_empty")

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    lab_results: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    active_count = 0
    disabled_count = 0

    top_refs = _resolve_refs(
        _as_string_list(payload.get("refs")),
        project_root=project,
        package_root=package,
        owner=str(payload.get("id") or "policy"),
    )
    failures.extend(top_refs["failures"])
    all_resolved_refs.extend(top_refs["resolved_refs"])
    all_missing_refs.extend(top_refs["missing_refs"])
    all_unsafe_refs.extend(top_refs["unsafe_refs"])

    for idx, raw_lab in enumerate(labs):
        lab = raw_lab if isinstance(raw_lab, dict) else {}
        lab_id = str(lab.get("id") or f"<index:{idx}>").strip()
        lab_failures = _lab_failures(lab, policy)
        if lab_id in seen_ids:
            lab_failures.append(f"lab_duplicate_id:{lab_id}")
        seen_ids.add(lab_id)

        state = str(lab.get("state") or policy.get("default_state") or "").strip()
        active_count += 1 if state in ACTIVE_LAB_STATES else 0
        disabled_count += 1 if state == "disabled" else 0

        lab_refs = _as_string_list(lab.get("refs"))
        dataset_ref = str((lab.get("dataset_manifest") or {}).get("dataset_ref") or "").strip() if isinstance(lab.get("dataset_manifest"), dict) else ""
        if dataset_ref:
            lab_refs.append(dataset_ref)
        if not lab_refs:
            lab_failures.append(f"lab_refs_empty:{lab_id}")
        ref_report = _resolve_refs(lab_refs, project_root=project, package_root=package, owner=lab_id)
        lab_failures.extend(ref_report["failures"])
        all_resolved_refs.extend(ref_report["resolved_refs"])
        all_missing_refs.extend(ref_report["missing_refs"])
        all_unsafe_refs.extend(ref_report["unsafe_refs"])

        failures.extend(lab_failures)
        lab_results.append(
            {
                "id": lab_id,
                "ok": not lab_failures,
                "state": state,
                "target_model_ref": str(lab.get("target_model_ref") or ""),
                "adapter_method": str(lab.get("adapter_method") or ""),
                "adapter_rank": lab.get("adapter_rank"),
                "training_enabled": bool((lab.get("training_plan") or {}).get("enabled")) if isinstance(lab.get("training_plan"), dict) else False,
                "writes_production_weights": bool((lab.get("training_plan") or {}).get("writes_production_weights")) if isinstance(lab.get("training_plan"), dict) else False,
                "failures": sorted(set(lab_failures)),
            }
        )

    checks = [
        {"id": "training_disabled", "status": "passed" if policy.get("training_enabled") is False else "failed"},
        {"id": "weight_mutation_disabled", "status": "passed" if policy.get("weight_mutation_enabled") is False else "failed"},
        {"id": "evaluation_gate_required", "status": "passed" if policy.get("require_evaluation_gate") is True else "failed"},
        {"id": "rollback_manifest_required", "status": "passed" if policy.get("require_rollback_manifest") is True else "failed"},
        {"id": "dataset_manifest_required", "status": "passed" if policy.get("require_dataset_manifest") is True else "failed"},
        {"id": "resource_guard_required", "status": "passed" if policy.get("require_resource_guard") is True else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "labs": len(labs),
        "disabled_labs": disabled_count,
        "active_labs": active_count,
        "refs": len(all_resolved_refs) + len(all_missing_refs) + len(all_unsafe_refs),
        "resolved_refs": len(all_resolved_refs),
        "missing_refs": len(all_missing_refs),
        "unsafe_refs": len(all_unsafe_refs),
        "training_enabled_labs": sum(1 for item in lab_results if item["training_enabled"]),
        "production_weight_write_labs": sum(1 for item in lab_results if item["writes_production_weights"]),
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
        "lab_results": sorted(lab_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def peft_lora_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("peft_lora_lab_report_required")
    model_eval_status = "passed" if report.get("ok") else "failed"
    safety_status = "passed" if not report.get("failures") else "failed"
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": [
            {"id": "model_eval", "status": model_eval_status, "score": 1.0 if report.get("ok") else 0.0, "threshold": 1.0},
            {"id": "safety_eval", "status": safety_status, "score": 1.0 if not report.get("failures") else 0.0, "threshold": 1.0},
        ],
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the NoemaForge disabled PEFT/LoRA lab readiness policy.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/peft-lora-lab-policy.json",
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

    report = validate_peft_lora_lab_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "PEFTLoRALabValidationSummary",
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
