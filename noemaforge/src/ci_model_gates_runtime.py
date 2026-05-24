#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/ci_model_gates_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate offline CI model gates before model attachment or edge/gateway release.
Inputs: noemaforge/configs/ci-model-gates.json plus local project/package roots.
Outputs: JSON-compatible CIModelGatesReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_ci_model_gates_runtime.py
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


API_VERSION = "noemaforge.ci-model-gates/v1"
POLICY_KIND = "CIModelGatesPolicy"
REPORT_KIND = "CIModelGatesReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_GATE_STATES = {"draft", "shadow", "canary", "stable", "retired"}
VALID_TARGET_TYPES = {"edge", "gateway", "local_model"}
VALID_RUNTIMES = {"onnx", "tflm", "llama.cpp", "python", "mock"}
VALID_SIGNATURE_SCHEMES = {"sha256-selftest", "cosign", "minisign", "pgp"}
REQUIRED_CHECKS = {"accuracy_regression", "latency", "memory", "schema_compatibility", "signature"}
EDGE_REQUIRED_CHECKS = {"golden_replay"}
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
    if str(policy.get("mode") or "") != "offline_validation":
        failures.append("policy_mode_not_offline_validation")
    if str(policy.get("evidence_filename") or "") != "release_evidence.json":
        failures.append("policy_evidence_filename_not_release_evidence_json")
    for key in [
        "require_release_evidence",
        "require_accuracy_regression",
        "require_latency_budget",
        "require_memory_budget",
        "require_schema_compatibility",
        "require_signature",
        "require_golden_replay_for_edge",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")

    runtimes = set(_as_string_list(policy.get("allowed_runtimes")))
    schemes = set(_as_string_list(policy.get("allowed_signature_schemes")))
    required_checks = set(_as_string_list(policy.get("required_checks")))
    edge_checks = set(_as_string_list(policy.get("edge_required_checks")))
    if not runtimes:
        failures.append("policy_allowed_runtimes_empty")
    if not schemes:
        failures.append("policy_allowed_signature_schemes_empty")
    failures.extend(f"policy_invalid_runtime:{item}" for item in sorted(runtimes - VALID_RUNTIMES))
    failures.extend(f"policy_invalid_signature_scheme:{item}" for item in sorted(schemes - VALID_SIGNATURE_SCHEMES))
    for item in sorted(REQUIRED_CHECKS - required_checks):
        failures.append(f"policy_required_check_missing:{item}")
    for item in sorted(EDGE_REQUIRED_CHECKS - edge_checks):
        failures.append(f"policy_edge_required_check_missing:{item}")
    return failures


def _checks_by_id(evidence: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    checks: Dict[str, Dict[str, Any]] = {}
    for item in evidence.get("checks") or []:
        if not isinstance(item, dict):
            continue
        check_id = str(item.get("id") or "").strip()
        if check_id:
            checks[check_id] = dict(item)
    return checks


def _check_status_ok(check: Dict[str, Any]) -> bool:
    return str(check.get("status") or "").strip().lower() in {"pass", "passed", "ok"}


def _gate_failures(gate: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    gate_id = str(gate.get("id") or "").strip()
    owner = gate_id or "<missing>"
    if not SAFE_ID_RE.match(gate_id):
        failures.append(f"gate_id_invalid:{owner}")
    if str(gate.get("state") or "") not in VALID_GATE_STATES:
        failures.append(f"gate_state_invalid:{owner}:{gate.get('state')}")
    target_type = str(gate.get("target_type") or "")
    if target_type not in VALID_TARGET_TYPES:
        failures.append(f"gate_target_type_invalid:{owner}:{target_type}")
    if not REGISTRY_REF_RE.match(str(gate.get("model_ref") or "")):
        failures.append(f"gate_model_ref_invalid:{owner}")

    runtime = str(gate.get("runtime") or "")
    if runtime not in set(_as_string_list(policy.get("allowed_runtimes"))) or runtime not in VALID_RUNTIMES:
        failures.append(f"gate_runtime_not_allowed:{owner}:{runtime}")

    budgets = gate.get("budgets") if isinstance(gate.get("budgets"), dict) else {}
    max_latency = _as_float(budgets.get("max_p95_latency_ms"), -1.0)
    max_memory = _as_float(budgets.get("max_peak_memory_mb"), -1.0)
    max_artifact = _as_int(budgets.get("max_artifact_bytes"), -1)
    max_regression = _as_float(budgets.get("max_accuracy_regression"), -1.0)
    if max_latency <= 0:
        failures.append(f"gate_latency_budget_invalid:{owner}")
    if max_memory <= 0:
        failures.append(f"gate_memory_budget_invalid:{owner}")
    if max_artifact <= 0:
        failures.append(f"gate_artifact_budget_invalid:{owner}")
    if max_regression < 0:
        failures.append(f"gate_accuracy_regression_budget_invalid:{owner}")

    manifest = gate.get("manifest") if isinstance(gate.get("manifest"), dict) else {}
    if not str(manifest.get("artifact_uri") or "").strip():
        failures.append(f"gate_manifest_artifact_uri_missing:{owner}")
    if not SHA256_RE.match(str(manifest.get("sha256") or "")):
        failures.append(f"gate_manifest_sha256_invalid:{owner}")
    scheme = str(manifest.get("signature_scheme") or "")
    if scheme not in set(_as_string_list(policy.get("allowed_signature_schemes"))) or scheme not in VALID_SIGNATURE_SCHEMES:
        failures.append(f"gate_signature_scheme_not_allowed:{owner}:{scheme}")
    if not str(manifest.get("signature") or "").strip():
        failures.append(f"gate_signature_missing:{owner}")
    if not str(manifest.get("input_contract") or "").strip():
        failures.append(f"gate_input_contract_missing:{owner}")
    if not str(manifest.get("output_contract") or "").strip():
        failures.append(f"gate_output_contract_missing:{owner}")

    evidence_ref = str(gate.get("release_evidence_ref") or "").strip().replace("\\", "/")
    if not evidence_ref:
        failures.append(f"gate_release_evidence_ref_missing:{owner}")
    elif PurePosixPath(evidence_ref).name != str(policy.get("evidence_filename") or "release_evidence.json"):
        failures.append(f"gate_release_evidence_ref_not_release_evidence_json:{owner}:{evidence_ref}")

    evidence = gate.get("release_evidence") if isinstance(gate.get("release_evidence"), dict) else {}
    checks = _checks_by_id(evidence)
    required_checks = set(_as_string_list(policy.get("required_checks")))
    if target_type == "edge":
        required_checks |= set(_as_string_list(policy.get("edge_required_checks")))

    for check_id in sorted(required_checks):
        check = checks.get(check_id)
        if check is None:
            failures.append(f"gate_check_missing:{owner}:{check_id}")
            continue
        if not _check_status_ok(check):
            failures.append(f"gate_check_not_passed:{owner}:{check_id}")

    accuracy = checks.get("accuracy_regression") or {}
    baseline = _as_float(accuracy.get("baseline_accuracy"), 0.0)
    candidate = _as_float(accuracy.get("candidate_accuracy"), -1.0)
    allowed_regression = _as_float(accuracy.get("max_regression"), max_regression)
    if candidate < 0 or baseline - candidate > allowed_regression:
        failures.append(f"gate_accuracy_regression_exceeded:{owner}")

    latency = checks.get("latency") or {}
    latency_value = _as_float(latency.get("p95_latency_ms"), -1.0)
    latency_threshold = _as_float(latency.get("threshold_ms"), max_latency)
    if latency_value < 0 or latency_value > min(max_latency, latency_threshold):
        failures.append(f"gate_latency_budget_exceeded:{owner}")

    memory = checks.get("memory") or {}
    memory_value = _as_float(memory.get("peak_memory_mb"), -1.0)
    memory_threshold = _as_float(memory.get("threshold_mb"), max_memory)
    if memory_value < 0 or memory_value > min(max_memory, memory_threshold):
        failures.append(f"gate_memory_budget_exceeded:{owner}")

    artifact_size = _as_int((checks.get("artifact_size") or {}).get("artifact_bytes"), 0)
    if artifact_size > max_artifact:
        failures.append(f"gate_artifact_size_budget_exceeded:{owner}")

    schema = checks.get("schema_compatibility") or {}
    if schema.get("compatible") is not True:
        failures.append(f"gate_schema_not_compatible:{owner}")

    signature = checks.get("signature") or {}
    if signature.get("verified") is not True:
        failures.append(f"gate_signature_not_verified:{owner}")
    if str(signature.get("scheme") or "") != scheme:
        failures.append(f"gate_signature_scheme_mismatch:{owner}")

    replay = checks.get("golden_replay") or {}
    if target_type == "edge":
        cases_total = _as_int(replay.get("cases_total"), 0)
        cases_passed = _as_int(replay.get("cases_passed"), -1)
        if cases_total <= 0 or cases_passed != cases_total:
            failures.append(f"gate_golden_replay_not_complete:{owner}")
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


def validate_ci_model_gates(
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
    gates = payload.get("gates") if isinstance(payload.get("gates"), list) else []
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    if not gates:
        failures.append("gates_empty")

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    gate_results: List[Dict[str, Any]] = []
    observed_latencies: List[float] = []
    observed_memory: List[float] = []

    policy_refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(policy_refs["failures"])
    all_resolved_refs.extend(policy_refs["resolved_refs"])
    all_missing_refs.extend(policy_refs["missing_refs"])
    all_unsafe_refs.extend(policy_refs["unsafe_refs"])

    for gate in gates:
        if not isinstance(gate, dict):
            failures.append("gate_not_object")
            continue
        gate_id = str(gate.get("id") or "<missing>")
        gate_failures = _gate_failures(gate, policy)
        failures.extend(gate_failures)

        refs = _as_string_list(gate.get("refs"))
        evidence_ref = str(gate.get("release_evidence_ref") or "").strip()
        if evidence_ref and evidence_ref not in refs:
            refs.append(evidence_ref)
        refs_result = _resolve_refs(refs, project_root=project, package_root=package, owner=gate_id)
        failures.extend(refs_result["failures"])
        all_resolved_refs.extend(refs_result["resolved_refs"])
        all_missing_refs.extend(refs_result["missing_refs"])
        all_unsafe_refs.extend(refs_result["unsafe_refs"])

        checks = _checks_by_id(gate.get("release_evidence") if isinstance(gate.get("release_evidence"), dict) else {})
        observed_latencies.append(_as_float((checks.get("latency") or {}).get("p95_latency_ms"), 0.0))
        observed_memory.append(_as_float((checks.get("memory") or {}).get("peak_memory_mb"), 0.0))
        gate_results.append(
            {
                "id": gate_id,
                "ok": not gate_failures and not refs_result["failures"],
                "target_type": str(gate.get("target_type") or ""),
                "runtime": str(gate.get("runtime") or ""),
                "release_evidence_ref": str(gate.get("release_evidence_ref") or ""),
                "failures": sorted(set(gate_failures + refs_result["failures"])),
            }
        )

    checks_summary = [
        {"id": "accuracy_regression", "status": "passed" if not any("accuracy" in item for item in failures) else "failed"},
        {"id": "latency", "status": "passed" if not any("latency" in item for item in failures) else "failed"},
        {"id": "memory", "status": "passed" if not any("memory" in item for item in failures) else "failed"},
        {"id": "golden_replay", "status": "passed" if not any("golden_replay" in item for item in failures) else "failed"},
        {"id": "schema_compatibility", "status": "passed" if not any("schema" in item for item in failures) else "failed"},
        {"id": "signature", "status": "passed" if not any("signature" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "gates": len(gate_results),
        "edge_gates": sum(1 for item in gate_results if item["target_type"] == "edge"),
        "passing_gates": sum(1 for item in gate_results if item["ok"]),
        "refs": len(all_resolved_refs) + len(all_missing_refs) + len(all_unsafe_refs),
        "resolved_refs": len(all_resolved_refs),
        "missing_refs": len(all_missing_refs),
        "unsafe_refs": len(all_unsafe_refs),
        "max_observed_p95_latency_ms": max(observed_latencies) if observed_latencies else 0.0,
        "max_observed_peak_memory_mb": max(observed_memory) if observed_memory else 0.0,
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
        "checks": checks_summary,
        "gate_results": sorted(gate_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def ci_model_gates_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("ci_model_gates_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge offline CI model gates.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/ci-model-gates.json",
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

    report = validate_ci_model_gates(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "CIModelGatesSummary",
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
