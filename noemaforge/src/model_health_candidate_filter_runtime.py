#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/model_health_candidate_filter_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate that filtered role candidate maps exclude failed-runtime models.
Inputs: Model health candidate filter policy, role candidate map, model health registry.
Outputs: JSON-compatible validation reports.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_model_health_candidate_filter_runtime.py
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
from typing import Any, Dict, List, Sequence, Set


API_VERSION = "noemaforge.model-health-candidate-filter/v1"
POLICY_KIND = "ModelHealthCandidateFilterPolicy"
REPORT_KIND = "ModelHealthCandidateFilterValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
DEFAULT_EXCLUDED_STATES = {"failed_runtime", "failed_any_reason"}


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
    if not text or text.startswith("~"):
        return False
    if text.startswith("/") and not text.startswith("/opt/noemaforge/"):
        return False
    parts = PurePosixPath(text.lstrip("/")).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _localize_ref(ref: str) -> str:
    text = str(ref or "").strip().replace("\\", "/")
    prefix = "/opt/noemaforge/"
    if text.startswith(prefix):
        return text[len(prefix):]
    return text.lstrip("/")


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    local = _localize_ref(ref)
    candidates = [("project", project_root / local), ("package", package_root / local)]
    if not local.startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / local))
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


def load_json(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return load_json(policy_path)


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
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if str(policy.get("activation_state") or "") != "filtered_candidate_map_excludes_failed_runtime_models":
        failures.append("policy_activation_state_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_model_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["candidate_map_artifact", "health_registry_artifact", "failure_report_artifact"]:
        if not str(policy.get(key) or "").endswith(".json"):
            failures.append(f"policy_{key}_invalid")
    for key in ["exclude_health_states", "selected_model_paths", "required_runtime_scripts", "required_runtime_tokens", "required_docs"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def excluded_model_ids(health_registry: Dict[str, Any], *, excluded_states: Set[str] | None = None) -> Set[str]:
    states = excluded_states or DEFAULT_EXCLUDED_STATES
    excluded: Set[str] = set()
    for model_id, rec in (health_registry.get("models") or {}).items():
        if not isinstance(rec, dict):
            continue
        health_state = str(rec.get("health_state") or "")
        if rec.get("exclude_from_selection") is True or health_state in states:
            if str(model_id or "").strip():
                excluded.add(str(model_id))
            logical_id = str(rec.get("logical_model_id") or "").strip()
            if logical_id:
                excluded.add(logical_id)
    return excluded


def selected_model_ids(candidate_map: Dict[str, Any]) -> Set[str]:
    selected: Set[str] = set()
    for model_id in candidate_map.get("unique_selected_model_ids") or []:
        text = str(model_id or "").strip()
        if text:
            selected.add(text)
    for role_key, role in (candidate_map.get("roles") or {}).items():
        if not isinstance(role, dict):
            continue
        chosen = role.get("chosen")
        if isinstance(chosen, dict):
            model_id = str(chosen.get("model_id") or "").strip()
            if model_id:
                selected.add(model_id)
        for rec in role.get("selected") or []:
            if not isinstance(rec, dict):
                continue
            model_id = str(rec.get("model_id") or "").strip()
            if model_id:
                selected.add(model_id)
    return selected


def validate_filtered_candidate_map(
    candidate_map: Dict[str, Any],
    health_registry: Dict[str, Any],
    *,
    policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    failures: List[str] = []
    policy_body = _policy_dict(policy or {})
    states = set(_as_string_list(policy_body.get("exclude_health_states"))) or DEFAULT_EXCLUDED_STATES
    excluded = excluded_model_ids(health_registry, excluded_states=states)
    selected = selected_model_ids(candidate_map)
    overlap = sorted(selected & excluded)

    if candidate_map.get("kind") != "RoleCandidateMap":
        failures.append("candidate_map_kind_invalid")
    if overlap:
        failures.append(f"failed_model_selected:{','.join(overlap)}")
    if candidate_map.get("excluded_model_count") is not None and int(candidate_map.get("excluded_model_count") or 0) != len(excluded):
        failures.append("candidate_map_excluded_model_count_mismatch")
    if "health_registry" not in candidate_map:
        failures.append("candidate_map_missing_health_registry_ref")
    diagnostics = candidate_map.get("selection_diagnostics") or {}
    if excluded and not selected and diagnostics.get("no_candidates_reason") not in {None, "no_candidates_after_failed_model_filter", "runtime_infrastructure_failed", "no_candidates_after_thresholds"}:
        failures.append("candidate_map_no_candidates_reason_unexpected")
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "failures": failures,
        "metrics": {
            "selected_model_count": len(selected),
            "excluded_model_count": len(excluded),
            "selected_failed_model_count": len(overlap),
        },
        "selected_models": sorted(selected),
        "excluded_models": sorted(excluded),
    }


def _runtime_script_reports(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_runtime_scripts")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        text = Path(resolved["path"]).read_text(encoding="utf-8", errors="replace") if resolved.get("ok") else ""
        local_failures: List[str] = []
        if not resolved.get("ok"):
            local_failures.append(f"runtime_script_missing:{ref}")
        for token in _as_string_list(policy.get("required_runtime_tokens")):
            if text and token not in text:
                local_failures.append(f"runtime_token_missing:{ref}:{token}")
        failures.extend(local_failures)
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved})
    return {"failures": failures, "reports": reports}


def validate_model_health_candidate_filter_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path,
    package_root: Path,
) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    failures = _policy_failures(payload)
    refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project_root, package_root=package_root, owner=str(payload.get("id") or "policy"))
    failures.extend(refs["failures"])
    scripts = _runtime_script_reports(policy, project_root=project_root, package_root=package_root)
    failures.extend(scripts["failures"])
    doc_refs = _resolve_refs(_as_string_list(policy.get("required_docs")), project_root=project_root, package_root=package_root, owner="required_docs")
    failures.extend(doc_refs["failures"])
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "id": payload.get("id"),
        "version": payload.get("version"),
        "failures": failures,
        "metrics": {
            "refs": len(_as_string_list(payload.get("refs"))),
            "resolved_refs": len(refs["resolved_refs"]),
            "runtime_scripts": len(scripts["reports"]),
            "required_docs": len(doc_refs["resolved_refs"]),
        },
        "refs": refs,
        "runtime_scripts": scripts["reports"],
        "required_docs": doc_refs,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge model-health candidate filtering.")
    parser.add_argument("--policy", default=str(Path(__file__).resolve().parents[1] / "configs" / "model-health-candidate-filter-policy.json"))
    parser.add_argument("--candidate-map", default="")
    parser.add_argument("--health-registry", default="")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--package-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    policy = load_policy(args.policy)
    report = validate_model_health_candidate_filter_policy(policy, project_root=Path(args.project_root), package_root=Path(args.package_root))
    if args.candidate_map and args.health_registry:
        artifact_report = validate_filtered_candidate_map(load_json(args.candidate_map), load_json(args.health_registry), policy=policy)
        report["artifact_report"] = artifact_report
        if not artifact_report["ok"]:
            report["ok"] = False
            report["failures"].extend(artifact_report["failures"])
    print(json.dumps(report if not args.summary else {k: report[k] for k in ["apiVersion", "kind", "ok", "id", "version", "metrics", "failures"]}, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
