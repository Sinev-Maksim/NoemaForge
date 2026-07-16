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
from typing import Any, Dict, Iterable, List, Optional

CANONICAL_GATEWAY_SOCKET = "/run/noemaforge/llm/gateway.sock"
LEGACY_GATEWAY_SOCKETS = [
    "/run/noemaforge/llm-gateway.sock",
    "/run/noemaforge/gateway.sock",
]
OPERATOR_APPLY_SUMMARY = "operator-degraded-apply-summary.json"


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
