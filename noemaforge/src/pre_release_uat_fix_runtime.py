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
CANONICAL_MAIN_BACKEND_SOCKET = "/run/noemaforge/llm/backends/main.sock"
CANONICAL_TOOLPROXY_SOCKET = "/run/noemaforge/toolproxy.sock"
CANONICAL_GATEWAY_SMOKE_URL = "http://localhost/v1/models"
LEGACY_GATEWAY_SOCKETS = [
    "/run/noemaforge/llm-gateway.sock",
    "/run/noemaforge/gateway.sock",
]
OPERATOR_APPLY_SUMMARY = "operator-degraded-apply-summary.json"


def gateway_socket_candidates() -> List[str]:
    """Return probe order: canonical target socket first, legacy fallbacks after."""
    return [CANONICAL_GATEWAY_SOCKET, *LEGACY_GATEWAY_SOCKETS]


def gateway_probe_spec() -> Dict[str, Any]:
    """Return the canonical read-only gateway smoke shape for target forensics."""
    return {
        "socket": CANONICAL_GATEWAY_SOCKET,
        "url": CANONICAL_GATEWAY_SMOKE_URL,
        "method": "GET",
        "protocol": "http_over_unix_socket",
        "command": [
            "curl",
            "-fsS",
            "--unix-socket",
            CANONICAL_GATEWAY_SOCKET,
            CANONICAL_GATEWAY_SMOKE_URL,
        ],
        "legacy_socket_candidates": list(LEGACY_GATEWAY_SOCKETS),
    }


def contract_epoch_paths(epoch_id: str, *, data_root: str = "/var/lib/noemaforge") -> Dict[str, str]:
    """Return canonical contract epoch paths for target-host checks."""
    base = Path(data_root) / "contracts" / "epochs"
    epoch = str(epoch_id or "").strip()
    return {
        "epochs_dir": str(base),
        "current": str(base / "current"),
        "epoch_dir": str(base / epoch) if epoch else "",
    }


def resolve_current_epoch_state(contracts_root: Path | str) -> Dict[str, Any]:
    """Resolve contracts/epochs/current and current_epoch.txt without mutation."""
    root = Path(contracts_root)
    epochs_dir = root / "epochs"
    current = epochs_dir / "current"
    txt = epochs_dir / "current_epoch.txt"
    current_epoch_txt = ""
    problems: List[str] = []

    try:
        current_epoch_txt = txt.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        problems.append("current_epoch_txt_missing_or_unreadable")

    current_is_symlink = current.is_symlink()
    current_exists = current.exists()
    current_target = ""
    current_target_exists = False
    current_target_epoch_id = ""
    try:
        if current_is_symlink or current_exists:
            target = current.resolve(strict=False)
            current_target = str(target)
            current_target_exists = target.exists()
            current_target_epoch_id = target.name
        else:
            problems.append("current_epoch_link_missing")
    except OSError as exc:
        problems.append(f"current_epoch_link_unreadable:{exc}")

    epoch_id = current_epoch_txt or current_target_epoch_id
    epoch_dir = epochs_dir / epoch_id if epoch_id else None
    epoch_dir_exists = bool(epoch_dir and epoch_dir.is_dir())
    if epoch_id and not epoch_dir_exists:
        problems.append("current_epoch_dir_missing")
    if current_epoch_txt and current_target_epoch_id and current_epoch_txt != current_target_epoch_id:
        problems.append("current_epoch_txt_target_mismatch")
    if current_is_symlink and not current_target_exists:
        problems.append("current_epoch_link_dangling")

    return {
        "ok": not problems,
        "contracts_root": str(root),
        "epochs_dir": str(epochs_dir),
        "current": str(current),
        "current_exists": current_exists,
        "current_is_symlink": current_is_symlink,
        "current_target": current_target,
        "current_target_exists": current_target_exists,
        "current_target_epoch_id": current_target_epoch_id,
        "current_epoch_txt": current_epoch_txt,
        "current_epoch_id": epoch_id,
        "epoch_dir": str(epoch_dir) if epoch_dir else "",
        "epoch_dir_exists": epoch_dir_exists,
        "problems": problems,
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


def _load_json_or_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, (str, Path)):
        try:
            loaded = load_json_any(Path(value))
            return loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _bool_from_health(value: Any) -> bool:
    if isinstance(value, dict):
        if "ok" in value:
            return bool(value.get("ok"))
        if "present" in value:
            return bool(value.get("present"))
        state = str(value.get("state") or value.get("status") or "").lower()
        return state in {"ok", "ready", "active", "present", "healthy"}
    return bool(value)


def reconcile_post_apply_forensics(
    *,
    apply_summary: Any = None,
    firstboot_status: Any = None,
    current_epoch: Optional[Dict[str, Any]] = None,
    contracts_root: Path | str | None = None,
    prestart_requests: Any = None,
    backend_health: Any = None,
    gateway_health: Any = None,
    toolproxy_diag: Any = None,
) -> Dict[str, Any]:
    """Classify post-apply evidence without probing live services."""
    apply_doc = _load_json_or_dict(apply_summary)
    status_doc = _load_json_or_dict(firstboot_status)
    requests_doc = _load_json_or_dict(prestart_requests)
    backend_doc = _load_json_or_dict(backend_health)
    gateway_doc = _load_json_or_dict(gateway_health)
    toolproxy_doc = _load_json_or_dict(toolproxy_diag)
    epoch_doc = dict(current_epoch or {})
    if not epoch_doc and contracts_root is not None:
        epoch_doc = resolve_current_epoch_state(contracts_root)

    applied_epoch_id = str(
        apply_doc.get("applied_epoch_id")
        or status_doc.get("applied_epoch_id")
        or epoch_doc.get("current_epoch_id")
        or ""
    ).strip()
    current_epoch_target = str(epoch_doc.get("current_target") or epoch_doc.get("epoch_dir") or "").strip()
    current_epoch_id = str(epoch_doc.get("current_epoch_id") or "").strip()
    post_backend_ok = _bool_from_health(backend_doc) or _bool_from_health(apply_doc.get("post_backend_ok")) or _bool_from_health(apply_doc.get("main_backend_smoke"))
    post_gateway_ok = _bool_from_health(gateway_doc) or _bool_from_health(apply_doc.get("post_gateway_ok"))
    toolproxy_ok = _bool_from_health(toolproxy_doc)

    probe = gateway_probe_spec()
    observed_socket = str(gateway_doc.get("socket") or gateway_doc.get("sock") or gateway_doc.get("path") or apply_doc.get("gateway_socket") or "").strip()
    observed_protocol = str(gateway_doc.get("protocol") or apply_doc.get("gateway_protocol") or "").strip()
    canonical_probe_used = (
        observed_socket in {"", probe["socket"]}
        and observed_protocol in {"", probe["protocol"], "http", "http_unix", "http_over_unix_socket"}
    )

    blockers: List[str] = []
    if not current_epoch_target:
        blockers.append("current_epoch_target_missing")
    if applied_epoch_id and current_epoch_id and applied_epoch_id != current_epoch_id:
        blockers.append("applied_epoch_current_epoch_mismatch")
    if epoch_doc.get("problems"):
        blockers.extend(f"contracts:{item}" for item in epoch_doc.get("problems") or [])
    if not post_gateway_ok:
        blockers.append("post_gateway_not_ok")
    if not post_backend_ok:
        blockers.append("post_backend_not_ok")

    if post_backend_ok and not post_gateway_ok:
        if not canonical_probe_used:
            determination = "wrong_smoke_path_or_protocol"
        elif not _bool_from_health(gateway_doc.get("socket_present", gateway_doc.get("present", True))):
            determination = "gateway_outage"
        else:
            determination = "gateway_smoke_failed"
    elif "current_epoch_target_missing" in blockers and current_epoch_id:
        determination = "summary_helper_issue"
    elif blockers:
        determination = "post_apply_evidence_incomplete"
    else:
        determination = "post_apply_state_reconciled"

    return {
        "ok": not blockers,
        "determination": determination,
        "applied_epoch_id": applied_epoch_id,
        "current_epoch_id": current_epoch_id,
        "current_epoch_target": current_epoch_target,
        "post_backend_ok": post_backend_ok,
        "post_gateway_ok": post_gateway_ok,
        "toolproxy_diag_ok": toolproxy_ok,
        "canonical_gateway_probe": probe,
        "canonical_gateway_probe_used": canonical_probe_used,
        "firstboot_state": status_doc.get("state") or "",
        "prestart_request_count": len(requests_doc.get("requests") or []) if isinstance(requests_doc.get("requests"), list) else 0,
        "blockers": blockers,
    }


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
