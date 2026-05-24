#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/edge_rules_engine_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate offline Edge Rules Engine contracts before guarded model-score use.
Inputs: noemaforge/configs/edge-rules-engine-policy.json plus local project/package roots.
Outputs: JSON-compatible EdgeRulesEngineReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_edge_rules_engine_runtime.py
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


API_VERSION = "noemaforge.edge-rules-engine/v1"
POLICY_KIND = "EdgeRulesEnginePolicy"
REPORT_KIND = "EdgeRulesEngineReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_MODES = {"whitebox_only", "ml_guarded", "shadow"}
VALID_STAGES = {"pre_ml", "post_ml", "pre_and_post_ml"}
VALID_ACTIONS = {"allow", "fallback_whitebox", "route_anomaly", "block", "review"}
VALID_ANOMALY_ACTIONS = {"route_anomaly", "review", "block"}
VALID_DRIFT_ACTIONS = {"review", "block", "fallback_whitebox"}
VALID_FALLBACKS = {"whitebox", "manual_review", "previous_rule"}
VALID_OPS = {"gt", "gte", "lt", "lte", "eq", "neq"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,120}$")


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
        "require_whitebox_only_mode",
        "require_rule_guard_before_ml",
        "require_rule_guard_after_ml",
        "require_thresholds",
        "require_anomaly_route",
        "require_drift_flags",
        "require_signed_model_manifest",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if str(policy.get("default_fallback") or "") != "whitebox":
        failures.append("policy_default_fallback_not_whitebox")

    modes = set(_as_string_list(policy.get("allowed_modes")))
    actions = set(_as_string_list(policy.get("allowed_actions")))
    fallbacks = set(_as_string_list(policy.get("allowed_fallbacks")))
    if not modes:
        failures.append("policy_allowed_modes_empty")
    if not actions:
        failures.append("policy_allowed_actions_empty")
    if not fallbacks:
        failures.append("policy_allowed_fallbacks_empty")
    failures.extend(f"policy_invalid_mode:{item}" for item in sorted(modes - VALID_MODES))
    failures.extend(f"policy_invalid_action:{item}" for item in sorted(actions - VALID_ACTIONS))
    failures.extend(f"policy_invalid_fallback:{item}" for item in sorted(fallbacks - VALID_FALLBACKS))
    for required_mode in ["whitebox_only", "ml_guarded"]:
        if required_mode not in modes:
            failures.append(f"policy_required_mode_missing:{required_mode}")
    for required_action in ["fallback_whitebox", "route_anomaly", "review"]:
        if required_action not in actions:
            failures.append(f"policy_required_action_missing:{required_action}")
    return failures


def _threshold_failures(threshold: Dict[str, Any], *, owner: str, allowed_actions: set[str]) -> List[str]:
    failures: List[str] = []
    metric = str(threshold.get("metric") or "")
    op = str(threshold.get("op") or "")
    action = str(threshold.get("action") or "")
    if not SAFE_NAME_RE.match(metric):
        failures.append(f"rule_threshold_metric_invalid:{owner}:{metric}")
    if op not in VALID_OPS:
        failures.append(f"rule_threshold_op_invalid:{owner}:{op}")
    try:
        float(threshold.get("value"))
    except Exception:
        failures.append(f"rule_threshold_value_invalid:{owner}:{metric}")
    if action not in allowed_actions or action not in VALID_ACTIONS:
        failures.append(f"rule_threshold_action_not_allowed:{owner}:{action}")
    return failures


def _rule_failures(rule: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    rule_id = str(rule.get("id") or "").strip()
    owner = rule_id or "<missing>"
    allowed_modes = set(_as_string_list(policy.get("allowed_modes")))
    allowed_actions = set(_as_string_list(policy.get("allowed_actions")))
    allowed_fallbacks = set(_as_string_list(policy.get("allowed_fallbacks")))

    if not SAFE_ID_RE.match(rule_id):
        failures.append(f"rule_id_invalid:{owner}")
    if str(rule.get("state") or "") not in VALID_STATUSES:
        failures.append(f"rule_state_invalid:{owner}:{rule.get('state')}")
    mode = str(rule.get("mode") or "")
    stage = str(rule.get("stage") or "")
    if mode not in allowed_modes or mode not in VALID_MODES:
        failures.append(f"rule_mode_not_allowed:{owner}:{mode}")
    if stage not in VALID_STAGES:
        failures.append(f"rule_stage_invalid:{owner}:{stage}")
    if rule.get("rule_guard_required") is not True:
        failures.append(f"rule_guard_not_required:{owner}")
    if str(rule.get("fallback") or "") not in allowed_fallbacks or str(rule.get("fallback") or "") not in VALID_FALLBACKS:
        failures.append(f"rule_fallback_not_allowed:{owner}:{rule.get('fallback')}")

    thresholds = rule.get("thresholds") if isinstance(rule.get("thresholds"), list) else []
    if not thresholds:
        failures.append(f"rule_thresholds_empty:{owner}")
    for threshold in thresholds:
        if not isinstance(threshold, dict):
            failures.append(f"rule_threshold_not_object:{owner}")
            continue
        failures.extend(_threshold_failures(threshold, owner=owner, allowed_actions=allowed_actions))

    anomaly = rule.get("anomaly_route") if isinstance(rule.get("anomaly_route"), dict) else {}
    if anomaly.get("enabled") is not True:
        failures.append(f"rule_anomaly_route_not_enabled:{owner}")
    if not str(anomaly.get("route") or "").strip():
        failures.append(f"rule_anomaly_route_missing:{owner}")
    if str(anomaly.get("action") or "") not in VALID_ANOMALY_ACTIONS:
        failures.append(f"rule_anomaly_action_invalid:{owner}:{anomaly.get('action')}")

    drift = rule.get("drift_flags") if isinstance(rule.get("drift_flags"), dict) else {}
    if drift.get("enabled") is not True:
        failures.append(f"rule_drift_flags_not_enabled:{owner}")
    drift_metrics = _as_string_list(drift.get("metrics"))
    if not drift_metrics:
        failures.append(f"rule_drift_metrics_empty:{owner}")
    for metric in drift_metrics:
        if not SAFE_NAME_RE.match(metric):
            failures.append(f"rule_drift_metric_invalid:{owner}:{metric}")
    if str(drift.get("action") or "") not in VALID_DRIFT_ACTIONS:
        failures.append(f"rule_drift_action_invalid:{owner}:{drift.get('action')}")

    may_apply_ml_score = rule.get("model_score_may_apply") is True
    if mode == "whitebox_only" and may_apply_ml_score:
        failures.append(f"rule_whitebox_allows_ml_score:{owner}")
    if mode == "whitebox_only" and str(rule.get("fallback") or "") != "whitebox":
        failures.append(f"rule_whitebox_fallback_not_whitebox:{owner}")
    if may_apply_ml_score:
        if mode != "ml_guarded":
            failures.append(f"rule_ml_score_mode_not_ml_guarded:{owner}")
        if rule.get("applies_before_ml") is not True:
            failures.append(f"rule_ml_score_without_pre_guard:{owner}")
        if rule.get("applies_after_ml") is not True:
            failures.append(f"rule_ml_score_without_post_guard:{owner}")
        if not any(str(item.get("metric") or "") == "ml_score" for item in thresholds if isinstance(item, dict)):
            failures.append(f"rule_ml_score_threshold_missing:{owner}")
    if policy.get("require_signed_model_manifest") is True:
        manifest_ref = str(rule.get("signed_model_manifest_ref") or "").strip()
        if not manifest_ref:
            failures.append(f"rule_signed_model_manifest_ref_missing:{owner}")
        elif not _is_safe_relative_ref(manifest_ref):
            failures.append(f"rule_signed_model_manifest_ref_unsafe:{owner}:{manifest_ref}")
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


def validate_edge_rules_engine_policy(
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
    rules = payload.get("rules") if isinstance(payload.get("rules"), list) else []
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    if not rules:
        failures.append("rules_empty")

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    rule_results: List[Dict[str, Any]] = []

    policy_refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(policy_refs["failures"])
    all_resolved_refs.extend(policy_refs["resolved_refs"])
    all_missing_refs.extend(policy_refs["missing_refs"])
    all_unsafe_refs.extend(policy_refs["unsafe_refs"])

    modes_seen = set()
    for rule in rules:
        if not isinstance(rule, dict):
            failures.append("rule_not_object")
            continue
        rule_id = str(rule.get("id") or "<missing>")
        modes_seen.add(str(rule.get("mode") or ""))
        rule_failures = _rule_failures(rule, policy)
        refs = _as_string_list(rule.get("refs"))
        manifest_ref = str(rule.get("signed_model_manifest_ref") or "").strip()
        if manifest_ref and manifest_ref not in refs:
            refs.append(manifest_ref)
        refs_result = _resolve_refs(refs, project_root=project, package_root=package, owner=rule_id)
        rule_failures.extend(refs_result["failures"])
        failures.extend(rule_failures)
        all_resolved_refs.extend(refs_result["resolved_refs"])
        all_missing_refs.extend(refs_result["missing_refs"])
        all_unsafe_refs.extend(refs_result["unsafe_refs"])
        thresholds = rule.get("thresholds") if isinstance(rule.get("thresholds"), list) else []
        rule_results.append(
            {
                "id": rule_id,
                "ok": not rule_failures,
                "mode": str(rule.get("mode") or ""),
                "stage": str(rule.get("stage") or ""),
                "model_score_may_apply": rule.get("model_score_may_apply") is True,
                "thresholds": len(thresholds),
                "anomaly_route_enabled": bool((rule.get("anomaly_route") or {}).get("enabled")) if isinstance(rule.get("anomaly_route"), dict) else False,
                "drift_flags_enabled": bool((rule.get("drift_flags") or {}).get("enabled")) if isinstance(rule.get("drift_flags"), dict) else False,
                "failures": sorted(set(rule_failures)),
            }
        )

    if policy.get("require_whitebox_only_mode") is True and "whitebox_only" not in modes_seen:
        failures.append("whitebox_only_rule_missing")
    if policy.get("require_rule_guard_after_ml") is True and not any(item.get("model_score_may_apply") and item.get("stage") == "pre_and_post_ml" for item in rule_results):
        failures.append("guarded_ml_rule_missing")

    checks = [
        {"id": "whitebox_only_mode", "status": "passed" if not any("whitebox" in item for item in failures) else "failed"},
        {"id": "ml_score_guarded", "status": "passed" if not any("ml_score" in item for item in failures) else "failed"},
        {"id": "thresholds", "status": "passed" if not any("threshold" in item for item in failures) else "failed"},
        {"id": "anomaly_route", "status": "passed" if not any("anomaly" in item for item in failures) else "failed"},
        {"id": "drift_flags", "status": "passed" if not any("drift" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "rules": len(rule_results),
        "passing_rules": sum(1 for item in rule_results if item["ok"]),
        "whitebox_only_rules": sum(1 for item in rule_results if item["mode"] == "whitebox_only"),
        "guarded_ml_rules": sum(1 for item in rule_results if item["model_score_may_apply"]),
        "thresholds": sum(int(item["thresholds"]) for item in rule_results),
        "anomaly_routes": sum(1 for item in rule_results if item["anomaly_route_enabled"]),
        "drift_flag_rules": sum(1 for item in rule_results if item["drift_flags_enabled"]),
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
        "rule_results": sorted(rule_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def edge_rules_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("edge_rules_engine_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge offline Edge Rules Engine contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/edge-rules-engine-policy.json",
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

    report = validate_edge_rules_engine_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "EdgeRulesEngineSummary",
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
