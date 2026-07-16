#!/usr/bin/env python3
"""
NoemaForge 0.33.0 pre-release UAT artifact helpers.

These helpers are intentionally read-only. They normalize UAT artifacts collected
on the target host without starting services, changing epochs, or deleting state.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

CANONICAL_GATEWAY_SOCKET = "/run/noemaforge/llm/gateway.sock"
LEGACY_GATEWAY_SOCKETS = [
    "/run/noemaforge/llm-gateway.sock",
    "/run/noemaforge/gateway.sock",
]
OPERATOR_APPLY_SUMMARY = "operator-degraded-apply-summary.json"
FORENSIC_ARTIFACT_NAMES = {
    "decision": "model-selection-decision.json",
    "staffing_summary": "firstboot-staffing-summary.json",
    "role_candidate_map": "role-candidate-map.json",
    "role_tournament_results": "role-tournament-results.json",
    "model_run_records": "model-run-records.json",
    "composite_selection_plan": "composite-selection-plan.json",
}


def gateway_socket_candidates() -> List[str]:
    """Return probe order: canonical target socket first, legacy fallbacks after."""
    return [CANONICAL_GATEWAY_SOCKET, *LEGACY_GATEWAY_SOCKETS]


def contract_epoch_paths(epoch_id: str, *, data_root: str = "/var/lib/noemaforge") -> Dict[str, str]:
    """Return canonical contract epoch paths for target-host checks."""
    base = Path(data_root) / "contracts" / "epochs"
    epoch = str(epoch_id or "").strip()
    return {
        "epochs_dir": str(base),
        "current": str(base / "current"),
        "epoch_dir": str(base / epoch) if epoch else "",
    }


def load_json_any(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("records", "model_run_records", "model_runs", "runs"):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
    return []


def normalize_model_run_records(value: Any) -> List[Dict[str, Any]]:
    """Accept model-run artifacts stored as a list or wrapped in a dict."""
    records: List[Dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            records.append(item)
        else:
            records.append({"raw": item, "reason": "unknown"})
    return records


def extract_model_run_records(*artifacts: Any) -> List[Dict[str, Any]]:
    """Merge model-run records from common firstboot/tournament artifact shapes."""
    out: List[Dict[str, Any]] = []
    for artifact in artifacts:
        if isinstance(artifact, (str, Path)):
            try:
                artifact = load_json_any(Path(artifact))
            except (OSError, json.JSONDecodeError):
                continue
        out.extend(normalize_model_run_records(artifact))
    return out


def classify_runtime_finding(record: Dict[str, Any]) -> str:
    """Stable runtime finding classes for release decision summaries."""
    reason = str(record.get("reason") or "").strip()
    lowered = reason.lower()
    if bool(record.get("partial_valid")):
        return "partial_valid"
    if lowered in {"", "completed"} and bool(record.get("started")):
        return "completed"
    if lowered == "default_safety_filter" or "default_safety_filter" in lowered:
        return "safety-filtered"
    if "warmup_failed" in lowered:
        return "warmup_failed"
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if lowered.startswith("systemctl_start_failed"):
        return "systemctl_start_failed"
    return "unknown"


def summarize_model_run_records(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    materialized = list(records)
    classes = Counter(classify_runtime_finding(rec) for rec in materialized)
    raw_reasons = Counter(str(rec.get("reason") or "completed") for rec in materialized)
    failed_or_incomplete = [
        {
            "model_id": rec.get("model_id"),
            "logical_model_id": rec.get("logical_model_id"),
            "classification": classify_runtime_finding(rec),
            "reason": rec.get("reason") or "completed",
        }
        for rec in materialized
        if classify_runtime_finding(rec) not in {"completed", "partial_valid", "safety-filtered"}
    ]
    return {
        "model_runs": len(materialized),
        "models_started": sum(1 for rec in materialized if bool(rec.get("started"))),
        "classification_counts": dict(sorted(classes.items())),
        "reason_counts": dict(sorted(raw_reasons.items())),
        "failed_or_incomplete": failed_or_incomplete,
    }


def classify_full_composite_dry_run_scope(
    summary: Dict[str, Any],
    *,
    mode: str = "full_composite",
    dry_run: bool = True,
    retry_failed_models: bool = False,
    clear_model_health: bool = False,
    min_started_models: int = 2,
    stale_health_dominance_ratio: float = 0.5,
) -> Dict[str, Any]:
    """Classify whether a full_composite dry-run really exercised max complexity."""
    mode = str(mode or "").strip().lower()
    model_runs = int(summary.get("model_runs") or 0)
    models_started = int(summary.get("models_started") or 0)
    reason_counts = summary.get("reason_counts") if isinstance(summary.get("reason_counts"), dict) else {}
    stale_skips = int(reason_counts.get("previously_failed_runtime") or 0)
    stale_ratio = round(stale_skips / max(1, model_runs), 4)
    persisted_health_reused = bool(stale_skips and not (retry_failed_models or clear_model_health))
    unexpectedly_low_started = bool(model_runs and models_started < max(1, int(min_started_models)))
    stale_health_dominates = bool(model_runs and stale_ratio > float(stale_health_dominance_ratio))

    blocking_reasons: List[str] = []
    if mode != "full_composite":
        blocking_reasons.append("not_full_composite")
    if not dry_run:
        blocking_reasons.append("not_dry_run")
    if model_runs <= 0:
        blocking_reasons.append("model_run_evidence_missing")
    if persisted_health_reused:
        blocking_reasons.append("persisted_model_health_reused")
    if unexpectedly_low_started:
        blocking_reasons.append("models_started_unexpectedly_low")
    if stale_health_dominates:
        blocking_reasons.append("previously_failed_runtime_dominates")

    max_complexity = bool(mode == "full_composite" and dry_run and not blocking_reasons)
    return {
        "scope": "max_complexity_evaluation_dry_run" if max_complexity else "conservative_health_filtered_dry_run",
        "max_complexity_evaluation": max_complexity,
        "ok_to_label_max_complexity": max_complexity,
        "persisted_health_reused": persisted_health_reused,
        "retry_failed_models": bool(retry_failed_models),
        "clear_model_health": bool(clear_model_health),
        "models_started": models_started,
        "model_runs": model_runs,
        "previously_failed_runtime": stale_skips,
        "previously_failed_runtime_ratio": stale_ratio,
        "blocking_reasons": blocking_reasons,
        "next_actions": [] if max_complexity else [
            "rerun full_composite with --clear-model-health or --retry-failed-models after operator review",
            "use this result only as conservative degraded apply evidence, not as max-complexity evaluation evidence",
        ],
    }


def summarize_artifacts(paths: Iterable[Path]) -> Dict[str, Any]:
    materialized_paths = list(paths)
    records = extract_model_run_records(*materialized_paths)
    summary = summarize_model_run_records(records)
    summary["artifact_count"] = len(materialized_paths)
    summary["source"] = "raw_model_run_records"
    return summary


def forensic_artifact_paths(root: Path | str) -> Dict[str, Path]:
    base = Path(root)
    return {key: base / name for key, name in FORENSIC_ARTIFACT_NAMES.items()}


def _load_json_if_exists(path: Path) -> Any:
    try:
        if path.is_file():
            return load_json_any(path)
    except (OSError, json.JSONDecodeError):
        return None
    return None


def _selected_candidates(role_spec: Any) -> List[Dict[str, Any]]:
    if not isinstance(role_spec, dict):
        return []
    selected = role_spec.get("selected")
    if not isinstance(selected, list):
        return []
    return [item for item in selected if isinstance(item, dict)]


def _chosen_candidate(role_spec: Any) -> Dict[str, Any]:
    if not isinstance(role_spec, dict):
        return {}
    chosen = role_spec.get("chosen")
    return chosen if isinstance(chosen, dict) else {}


def _candidate_model_id(candidate: Dict[str, Any]) -> str:
    return str(candidate.get("model_id") or candidate.get("logical_model_id") or "").strip()


def _candidate_looks_measured(candidate: Dict[str, Any]) -> bool:
    if not isinstance(candidate, dict):
        return False
    if any(candidate.get(key) is not None for key in ("score", "pass_rate", "json_parse_rate", "quality_score")):
        return True
    return str(candidate.get("selection_status") or "") in {"valid_measured", "reuse_verified", "reuse_with_warning"}


def summarize_model_selection_decision(decision: Any) -> Dict[str, Any]:
    doc = decision if isinstance(decision, dict) else {}
    chosen_by_role = doc.get("chosen_by_role") if isinstance(doc.get("chosen_by_role"), dict) else {}
    chosen_model_ids = sorted(
        {
            _candidate_model_id(candidate)
            for candidate in chosen_by_role.values()
            if isinstance(candidate, dict) and _candidate_model_id(candidate)
        }
    )
    return {
        "mode": str(doc.get("mode") or ""),
        "dry_run": bool(doc.get("dry_run")),
        "ready_to_apply": bool(doc.get("ready_to_apply")),
        "chosen_roles": len(chosen_by_role),
        "chosen_model_ids": chosen_model_ids,
        "unique_chosen_models": len(chosen_model_ids),
        "staffing_state": str(doc.get("staffing_state") or ""),
        "missing_mandatory_core_roles": list(doc.get("missing_mandatory_core_roles") or []),
        "has_dry_run_evaluation_scope": isinstance(doc.get("dry_run_evaluation_scope"), dict),
    }


def summarize_staffing_summary(staffing: Any) -> Dict[str, Any]:
    doc = staffing if isinstance(staffing, dict) else {}
    selected_model_ids = sorted({str(item).strip() for item in (doc.get("selected_model_ids") or []) if str(item).strip()})
    return {
        "staffing_state": str(doc.get("staffing_state") or ""),
        "selected_roles": int(doc.get("selected_roles") or 0),
        "target_met_roles": int(doc.get("target_met_roles") or 0),
        "selected_model_count": int(doc.get("selected_model_count") or len(selected_model_ids)),
        "selected_model_ids": selected_model_ids,
        "missing_mandatory_core_roles": list(doc.get("missing_mandatory_core_roles") or []),
        "unstaffed_roles": list(doc.get("unstaffed_roles") or []),
    }


def summarize_role_candidate_map(candidate_map: Any) -> Dict[str, Any]:
    doc = candidate_map if isinstance(candidate_map, dict) else {}
    roles = doc.get("roles") if isinstance(doc.get("roles"), dict) else {}
    selected_roles = 0
    chosen_roles = 0
    candidate_count = 0
    measured_candidate_count = 0
    selected_model_ids = set()
    measured_selected_model_ids = set()
    for role_spec in roles.values():
        selected = _selected_candidates(role_spec)
        chosen = _chosen_candidate(role_spec)
        if selected:
            selected_roles += 1
        if chosen and _candidate_model_id(chosen):
            chosen_roles += 1
            selected_model_ids.add(_candidate_model_id(chosen))
        for candidate in selected:
            candidate_count += 1
            model_id = _candidate_model_id(candidate)
            if model_id:
                selected_model_ids.add(model_id)
            if _candidate_looks_measured(candidate):
                measured_candidate_count += 1
                if model_id:
                    measured_selected_model_ids.add(model_id)
    return {
        "role_count": len(roles),
        "selected_roles": selected_roles,
        "chosen_roles": chosen_roles,
        "candidate_count": candidate_count,
        "measured_candidate_count": measured_candidate_count,
        "selected_model_ids": sorted(selected_model_ids),
        "unique_selected_models": len(selected_model_ids),
        "measured_selected_model_ids": sorted(measured_selected_model_ids),
        "unique_measured_selected_models": len(measured_selected_model_ids),
    }


def summarize_role_tournament_results(tournament: Any) -> Dict[str, Any]:
    doc = tournament if isinstance(tournament, dict) else {}
    roles = doc.get("roles") if isinstance(doc.get("roles"), dict) else {}
    records = normalize_model_run_records(doc)
    return {
        "selection_mode": str(doc.get("selection_mode") or ""),
        "runtime_mode": str(doc.get("runtime_mode") or ""),
        "role_count": len(roles),
        "model_run_records_count": len(records),
        "has_composite_selection_plan_path": bool(doc.get("composite_selection_plan")),
    }


def summarize_composite_selection_plan(plan: Any) -> Dict[str, Any]:
    doc = plan if isinstance(plan, dict) else {}
    roles = doc.get("roles") if isinstance(doc.get("roles"), dict) else {}
    compositions = doc.get("compositions") if isinstance(doc.get("compositions"), list) else []
    candidate_counts = []
    for role_spec in roles.values():
        if not isinstance(role_spec, dict):
            continue
        candidate_counts.append(int(role_spec.get("candidate_count") or len(role_spec.get("candidates") or [])))
    return {
        "top_n": int(doc.get("top_n") or 0),
        "role_count": len(roles),
        "estimated_compositions": int(doc.get("estimated_compositions") or 0),
        "valid_compositions": int(doc.get("valid_compositions") or len(compositions)),
        "materialized": bool(doc.get("materialized")),
        "missing_candidate_roles": list(doc.get("missing_candidate_roles") or []),
        "total_candidate_slots": sum(candidate_counts),
    }


def summarize_preferred_model_run_records(model_run_records: Any, tournament: Any) -> Dict[str, Any]:
    """Prefer the dedicated artifact and fall back to tournament-embedded records."""
    dedicated = normalize_model_run_records(model_run_records)
    embedded = normalize_model_run_records(tournament)
    if dedicated:
        summary = summarize_model_run_records(dedicated)
        summary["source"] = "model-run-records.json"
        summary["embedded_model_runs"] = len(embedded)
        return summary
    summary = summarize_model_run_records(embedded)
    summary["source"] = "role-tournament-results.json:model_run_records"
    summary["embedded_model_runs"] = len(embedded)
    return summary


def reconcile_full_composite_artifacts(
    root: Path | str,
    *,
    retry_failed_models: bool = False,
    clear_model_health: bool = False,
) -> Dict[str, Any]:
    artifact_paths = forensic_artifact_paths(root)
    loaded = {key: _load_json_if_exists(path) for key, path in artifact_paths.items()}
    decision_summary = summarize_model_selection_decision(loaded["decision"])
    staffing_summary = summarize_staffing_summary(loaded["staffing_summary"])
    candidate_map_summary = summarize_role_candidate_map(loaded["role_candidate_map"])
    tournament_summary = summarize_role_tournament_results(loaded["role_tournament_results"])
    model_run_summary = summarize_preferred_model_run_records(loaded["model_run_records"], loaded["role_tournament_results"])
    composite_summary = summarize_composite_selection_plan(loaded["composite_selection_plan"])

    mode = (
        decision_summary["mode"]
        or tournament_summary["selection_mode"]
        or ("full_composite" if loaded["composite_selection_plan"] else "")
    )
    dry_run = bool(decision_summary["dry_run"])
    evaluation_scope = classify_full_composite_dry_run_scope(
        model_run_summary,
        mode=mode,
        dry_run=dry_run,
        retry_failed_models=retry_failed_models,
        clear_model_health=clear_model_health,
    )

    mismatches: List[str] = []
    if mode == "full_composite" and not loaded["composite_selection_plan"]:
        mismatches.append("composite_selection_plan_missing_for_full_composite")
    if decision_summary["mode"] and tournament_summary["selection_mode"] and decision_summary["mode"] != tournament_summary["selection_mode"]:
        mismatches.append("selection_mode_mismatch")
    if staffing_summary["selected_roles"] and candidate_map_summary["selected_roles"] and staffing_summary["selected_roles"] != candidate_map_summary["selected_roles"]:
        mismatches.append("selected_roles_mismatch")
    if decision_summary["chosen_roles"] and candidate_map_summary["chosen_roles"] and decision_summary["chosen_roles"] != candidate_map_summary["chosen_roles"]:
        mismatches.append("chosen_roles_mismatch")
    if staffing_summary["selected_model_count"] and candidate_map_summary["unique_selected_models"] and staffing_summary["selected_model_count"] != candidate_map_summary["unique_selected_models"]:
        mismatches.append("selected_model_count_mismatch")
    if tournament_summary["model_run_records_count"] and model_run_summary["model_runs"] and tournament_summary["model_run_records_count"] != model_run_summary["model_runs"]:
        mismatches.append("model_run_record_count_mismatch")
    if candidate_map_summary["measured_candidate_count"] > 0 and model_run_summary["model_runs"] == 0:
        mismatches.append("measured_candidates_without_model_run_evidence")
    if candidate_map_summary["selected_roles"] > 0 and model_run_summary["models_started"] == 0:
        mismatches.append("selected_roles_without_started_models")
    if decision_summary["ready_to_apply"] and staffing_summary["missing_mandatory_core_roles"]:
        mismatches.append("ready_to_apply_with_missing_mandatory_roles")
    if loaded["composite_selection_plan"] and composite_summary["role_count"] and candidate_map_summary["role_count"] and composite_summary["role_count"] != candidate_map_summary["role_count"]:
        mismatches.append("composite_role_count_mismatch")

    gate_blockers = list(dict.fromkeys([*evaluation_scope["blocking_reasons"], *mismatches]))
    return {
        "ok": True,
        "mode": mode,
        "dry_run": dry_run,
        "artifacts": {
            key: {
                "path": str(path),
                "present": loaded[key] is not None,
            }
            for key, path in artifact_paths.items()
        },
        "sources": {
            "model_selection_decision": decision_summary,
            "firstboot_staffing_summary": staffing_summary,
            "role_candidate_map": candidate_map_summary,
            "role_tournament_results": tournament_summary,
            "model_run_records": model_run_summary,
            "composite_selection_plan": composite_summary,
        },
        "mismatches": mismatches,
        "dry_run_evaluation_scope": evaluation_scope,
        "max_complexity_gate": {
            "accepted": bool(evaluation_scope["ok_to_label_max_complexity"] and not mismatches),
            "blocking_reasons": gate_blockers,
        },
    }


def locate_operator_degraded_apply(root: Path) -> Optional[Path]:
    """Find the real degraded apply run, explicitly excluding plan-only dirs."""
    root = Path(root)
    candidates: List[Path] = []
    for path in root.glob("operator_degraded_apply_*"):
        if not path.is_dir():
            continue
        if path.name.startswith("operator_degraded_apply_plan_"):
            continue
        summary = path / OPERATOR_APPLY_SUMMARY
        post_apply = path / "post_apply_artifacts"
        if summary.is_file() or post_apply.exists():
            candidates.append(path)
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.name)[-1]


def write_failure_report(out_dir: Path, *, stem: str, error: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Always emit JSON and Markdown failure evidence for early helper failures."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "ok": False,
        "error": str(error),
        "context": context or {},
    }
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        f"# {stem}\n\n"
        f"- ok: false\n"
        f"- error: `{payload['error']}`\n",
        encoding="utf-8",
    )
    return {"json": str(json_path), "markdown": str(md_path)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="NoemaForge full-composite artifact forensics")
    ap.add_argument("--root", required=True, help="Directory containing firstboot selection artifacts")
    ap.add_argument("--retry-failed-models", action="store_true")
    ap.add_argument("--clear-model-health", action="store_true")
    args = ap.parse_args(argv)

    report = reconcile_full_composite_artifacts(
        args.root,
        retry_failed_models=bool(args.retry_failed_models),
        clear_model_health=bool(args.clear_model_health),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
