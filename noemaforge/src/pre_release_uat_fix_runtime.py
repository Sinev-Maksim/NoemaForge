#!/usr/bin/env python3
"""
NoemaForge 0.33.0 pre-release UAT artifact helpers.

These helpers are intentionally read-only. They normalize UAT artifacts collected
on the target host without starting services, changing epochs, or deleting state.
"""
from __future__ import annotations

import json
import hashlib
import os
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence

CANONICAL_GATEWAY_SOCKET = "/run/noemaforge/llm/gateway.sock"
CANONICAL_MAIN_BACKEND_SOCKET = "/run/noemaforge/llm/backends/main.sock"
CANONICAL_TOOLPROXY_SOCKET = "/run/noemaforge/toolproxy.sock"
CANONICAL_GATEWAY_SMOKE_URL = "http://localhost/v1/models"
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
DEFAULT_OPT_ROOT = "/opt/noemaforge"
_PYTHONPATH_RE = re.compile(r"(?:^|[\s\"'])PYTHONPATH=([^\"'\s]+)")
_SRC_PATH_RE = re.compile(r"(/[A-Za-z0-9_./-]+/src)(?:/|\s|$)")


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


def _posix(path: str | os.PathLike[str]) -> str:
    text = str(path).replace("\\", "/").rstrip("/")
    return text or "/"


def _dedupe_paths(paths: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in paths:
        raw = str(value or "").strip()
        if not raw:
            continue
        text = _posix(raw)
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def extract_service_unit_source_paths(unit_texts: Iterable[str]) -> List[str]:
    """Extract configured Python source roots from already-collected unit text."""
    candidates: List[str] = []
    for text in unit_texts:
        for match in _PYTHONPATH_RE.finditer(str(text or "")):
            for entry in match.group(1).split(":"):
                if entry.endswith("/src") or entry.endswith("\\src"):
                    candidates.append(entry)
        for match in _SRC_PATH_RE.finditer(str(text or "")):
            candidates.append(match.group(1))
    return _dedupe_paths(candidates)


def target_source_root_candidates(
    *,
    opt_root: str = DEFAULT_OPT_ROOT,
    configured_source_paths: Iterable[Any] = (),
    service_unit_texts: Iterable[str] = (),
) -> List[str]:
    """Return target Python source roots in intentional deploy order."""
    opt = _posix(opt_root)
    configured = list(configured_source_paths)
    configured.extend(extract_service_unit_source_paths(service_unit_texts))
    return _dedupe_paths([
        *configured,
        f"{opt}/src",
        f"{opt}/noemaforge/src",
    ])


def discover_target_layout(
    *,
    opt_root: str = DEFAULT_OPT_ROOT,
    configured_source_paths: Iterable[Any] = (),
    service_unit_texts: Iterable[str] = (),
    existing_paths: Iterable[Any] = (),
) -> Dict[str, Any]:
    """Choose the active target layout from explicit/service paths before defaults."""
    candidates = target_source_root_candidates(
        opt_root=opt_root,
        configured_source_paths=configured_source_paths,
        service_unit_texts=service_unit_texts,
    )
    existing = set(_dedupe_paths(existing_paths))
    selected = ""
    if existing:
        selected = next((path for path in candidates if path in existing), "")
    if not selected and candidates:
        selected = candidates[0]
    package_root = _posix(str(PurePosixPath(selected).parent)) if selected else ""
    return {
        "ok": bool(selected),
        "opt_root": _posix(opt_root),
        "source_root": selected,
        "package_root": package_root,
        "candidates": candidates,
        "matched_existing": bool(selected and selected in existing),
        "evidence": "repo-evidenced",
        "live_evidence_claimed": False,
    }


def map_changed_file_to_target(changed_file: str, *, source_root: str, opt_root: str = DEFAULT_OPT_ROOT) -> Dict[str, Any]:
    """Map a repo-relative changed file into the discovered target layout."""
    rel = _posix(changed_file).lstrip("/")
    src_root = _posix(source_root) if str(source_root or "").strip() else ""
    package_root = _posix(str(PurePosixPath(src_root).parent)) if src_root else _posix(opt_root)
    target = ""
    role = "unmapped"
    if rel.startswith("noemaforge/src/"):
        if src_root:
            target = _posix(str(PurePosixPath(src_root) / rel[len("noemaforge/src/"):]))
            role = "python_source"
    elif rel.startswith("noemaforge/tests/"):
        target = _posix(str(PurePosixPath(package_root) / "tests" / rel[len("noemaforge/tests/"):]))
        role = "python_test"
    elif rel.startswith("noemaforge/configs/"):
        target = _posix(str(PurePosixPath(package_root) / "configs" / rel[len("noemaforge/configs/"):]))
        role = "package_config"
    elif rel.startswith("noemaforge/"):
        target = _posix(str(PurePosixPath(package_root) / rel[len("noemaforge/"):]))
        role = "package_file"
    elif rel.startswith(("helpers/", "lib/", "ci/")):
        target = _posix(str(PurePosixPath(opt_root) / rel))
        role = "repo_support_file"
    return {
        "repo_path": rel,
        "target_path": target,
        "role": role,
        "mapped": bool(target),
    }


def build_runtime_deploy_plan(
    changed_files: Iterable[str],
    *,
    source_root: str,
    opt_root: str = DEFAULT_OPT_ROOT,
) -> Dict[str, Any]:
    mappings = [map_changed_file_to_target(path, source_root=source_root, opt_root=opt_root) for path in changed_files]
    unmapped = [item["repo_path"] for item in mappings if not item["mapped"]]
    return {
        "ok": not unmapped,
        "source_root": _posix(source_root),
        "opt_root": _posix(opt_root),
        "mappings": mappings,
        "unmapped": unmapped,
        "evidence": "repo-evidenced",
        "live_evidence_claimed": False,
    }


def deployed_pythonpath(source_root: str, *, service_unit_texts: Iterable[str] = ()) -> List[str]:
    """Return PYTHONPATH entries needed to run deployed tests in the active layout."""
    src = _posix(source_root) if str(source_root or "").strip() else ""
    package = _posix(str(PurePosixPath(src).parent)) if src else ""
    configured: List[str] = []
    for text in service_unit_texts:
        for match in _PYTHONPATH_RE.finditer(str(text or "")):
            configured.extend(entry for entry in match.group(1).split(":") if entry)
    return _dedupe_paths([src, package, *configured])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_deployed_file_hashes(project_root: Path, mappings: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Verify copied target files match their repo sources by SHA256."""
    checked: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for mapping in mappings:
        if not mapping.get("mapped"):
            continue
        repo_path = str(mapping.get("repo_path") or "")
        target_path = str(mapping.get("target_path") or "")
        src = Path(project_root) / repo_path
        dst = Path(target_path)
        record = {"repo_path": repo_path, "target_path": target_path}
        try:
            src_hash = sha256_file(src)
            dst_hash = sha256_file(dst)
            record.update({"source_sha256": src_hash, "target_sha256": dst_hash, "ok": src_hash == dst_hash})
        except OSError as exc:
            record.update({"ok": False, "error": repr(exc)})
        checked.append(record)
        if not record["ok"]:
            failures.append(record)
    return {
        "ok": not failures,
        "checked": checked,
        "failures": failures,
        "evidence": "repo-evidenced",
        "live_evidence_claimed": False,
    }


def write_runtime_deploy_summary(out_dir: Path, payload: Dict[str, Any], *, stem: str = "runtime-deploy-summary") -> Dict[str, str]:
    """Write JSON and Markdown summaries without shell heredoc interpolation."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        f"# {stem}",
        "",
        f"- ok: {str(bool(payload.get('ok'))).lower()}",
        f"- evidence: {payload.get('evidence', 'repo-evidenced')}",
        f"- live_evidence_claimed: {str(bool(payload.get('live_evidence_claimed'))).lower()}",
    ]
    failures = payload.get("failures")
    if isinstance(failures, list):
        lines.append(f"- failures: {len(failures)}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def _clean_path_values(values: Iterable[Any]) -> List[str]:
    paths: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text:
            paths.append(text.rstrip("/") or "/")
    return paths


def classify_gateway_probe(
    *,
    observed_sockets: Iterable[Any] = (),
    probed_sockets: Iterable[Any] = (),
) -> Dict[str, Any]:
    """Classify gateway state from already-collected socket and probe evidence."""
    observed = _clean_path_values(observed_sockets)
    probed = _clean_path_values(probed_sockets)
    candidate_order = gateway_socket_candidates()
    observed_set = set(observed)
    probed_set = set(probed)
    matched_probe_paths = [path for path in probed if path in observed_set]
    canonical_present = CANONICAL_GATEWAY_SOCKET in observed_set
    legacy_present = [path for path in LEGACY_GATEWAY_SOCKETS if path in observed_set]
    canonical_probed = CANONICAL_GATEWAY_SOCKET in probed_set
    probe_path_mismatch = bool(canonical_present and probed and not canonical_probed and not matched_probe_paths)
    gateway_ok_now = bool(canonical_present or matched_probe_paths or legacy_present)
    if canonical_present and matched_probe_paths:
        reason = "canonical_gateway_socket_probe_hit"
    elif canonical_present and probe_path_mismatch:
        reason = "legacy_probe_path_mismatch"
    elif canonical_present:
        reason = "canonical_gateway_socket_observed"
    elif legacy_present:
        reason = "legacy_gateway_socket_observed"
    else:
        reason = "gateway_socket_missing"
    return {
        "gateway_ok_now": gateway_ok_now,
        "reason": reason,
        "canonical_socket": CANONICAL_GATEWAY_SOCKET,
        "legacy_sockets": list(LEGACY_GATEWAY_SOCKETS),
        "probe_order": candidate_order,
        "observed_sockets": observed,
        "probed_sockets": probed,
        "matched_probe_paths": matched_probe_paths,
        "canonical_socket_present": canonical_present,
        "legacy_socket_present": bool(legacy_present),
        "probe_path_mismatch": probe_path_mismatch,
        "real_gateway_failure": not gateway_ok_now,
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

    # A basename/id match is not sufficient: an external symlink target can share
    # the expected epoch id's *name* while resolving to a path entirely outside the
    # canonical epochs directory (e.g. an unrelated directory that happens to be
    # named "00006"). Require the full resolved path to equal the canonical
    # `<epochs_dir>/<epoch_id>` path before treating "current" as pointing at the
    # applied epoch.
    current_target_matches_canonical_dir = True
    if current_target and epoch_dir is not None:
        try:
            canonical_epoch_dir = str(epoch_dir.resolve(strict=False))
        except OSError:
            canonical_epoch_dir = str(epoch_dir)
        current_target_matches_canonical_dir = current_target == canonical_epoch_dir
        if not current_target_matches_canonical_dir:
            problems.append("current_epoch_link_outside_canonical_dir")

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
        "current_target_matches_canonical_dir": current_target_matches_canonical_dir,
        "current_epoch_txt": current_epoch_txt,
        "current_epoch_id": epoch_id,
        "epoch_dir": str(epoch_dir) if epoch_dir else "",
        "epoch_dir_exists": epoch_dir_exists,
        "problems": problems,
    }


def classify_contract_epoch_resolution(
    epoch_id: str,
    *,
    current_resolved: str = "",
    epoch_dir_exists: Optional[bool] = None,
    current_exists: Optional[bool] = None,
    data_root: str = "/var/lib/noemaforge",
) -> Dict[str, Any]:
    """Classify applied-epoch evidence from read-only path resolution artifacts."""
    paths = contract_epoch_paths(epoch_id, data_root=data_root)
    epoch_dir = str(paths["epoch_dir"])
    resolved = str(current_resolved or "").strip().rstrip("/")
    expected = epoch_dir.rstrip("/") if epoch_dir else ""
    current_points_to_epoch = bool(resolved and expected and resolved == expected)
    resolved_epoch_id = Path(resolved).name if resolved else ""
    applied_epoch_dir_exists = bool(epoch_dir_exists) or current_points_to_epoch
    path_mismatch_suspected = bool(current_points_to_epoch and epoch_dir_exists is False)
    if current_points_to_epoch and epoch_dir_exists is False:
        reason = "current_symlink_confirms_epoch_path_mismatch"
    elif current_points_to_epoch:
        reason = "current_symlink_points_to_applied_epoch"
    elif epoch_dir_exists:
        reason = "applied_epoch_dir_exists"
    elif epoch_dir:
        reason = "applied_epoch_dir_missing"
    else:
        reason = "applied_epoch_id_missing"
    return {
        **paths,
        "epoch_id": str(epoch_id or "").strip(),
        "current_resolved": resolved,
        "current_exists": current_exists,
        "epoch_dir_exists": epoch_dir_exists,
        "current_points_to_epoch": current_points_to_epoch,
        "current_resolved_epoch_id": resolved_epoch_id,
        "applied_epoch_dir_exists": applied_epoch_dir_exists,
        "path_mismatch_suspected": path_mismatch_suspected,
        "reason": reason,
    }


def load_json_any(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _materialize_artifact_value(value: Any) -> Any:
    if isinstance(value, Path):
        try:
            return load_json_any(value)
        except (OSError, json.JSONDecodeError):
            return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return value
        candidate = Path(text)
        if candidate.is_file():
            try:
                return load_json_any(candidate)
            except (OSError, json.JSONDecodeError):
                return value
        if text[:1] in {"{", "["}:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
    return value


def _as_list(value: Any) -> List[Any]:
    value = _materialize_artifact_value(value)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("records", "model_run_records", "model_runs", "runs"):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
        return [value]
    return [value]


def normalize_model_run_records(value: Any) -> List[Dict[str, Any]]:
    """Accept model-run artifacts stored as a list or wrapped in a dict."""
    records: List[Dict[str, Any]] = []
    for item in _as_list(value):
        item = _materialize_artifact_value(item)
        if isinstance(item, list):
            records.extend(normalize_model_run_records(item))
        elif isinstance(item, dict):
            records.append(item)
        else:
            records.append({"raw": item, "reason": "unknown"})
    return records


def extract_model_run_records(*artifacts: Any) -> List[Dict[str, Any]]:
    """Merge model-run records from common firstboot/tournament artifact shapes."""
    out: List[Dict[str, Any]] = []
    for artifact in artifacts:
        out.extend(normalize_model_run_records(artifact))
    return out


def classify_runtime_finding(record: Dict[str, Any]) -> str:
    """Stable runtime finding classes for release decision summaries."""
    reason = str(record.get("reason") or "").strip()
    selection_status = str(record.get("selection_status") or "").strip()
    lowered = " ".join(part.lower() for part in (reason, selection_status) if part)
    if bool(record.get("partial_valid")):
        return "partial_valid"
    if lowered in {"", "completed"} and bool(record.get("started")):
        return "completed"
    if lowered == "default_safety_filter" or "default_safety_filter" in lowered:
        return "safety-filtered"
    if "invalid_backend_calls" in lowered:
        return "invalid_backend_calls"
    if "warmup_failed" in lowered:
        return "warmup_failed"
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if lowered.startswith("systemctl_start_failed"):
        return "systemctl_start_failed"
    return "unknown"


def _runtime_reason(record: Dict[str, Any]) -> str:
    reason = str(record.get("reason") or "").strip()
    if reason:
        return reason
    selection_status = str(record.get("selection_status") or "").strip()
    if selection_status and selection_status != "completed":
        return selection_status
    if not bool(record.get("started")):
        # Never started and no reason/selection_status recorded: this is a
        # genuinely unknown outcome, not a completed run. Defaulting to
        # "completed" here would misclassify never-started records inside
        # failure/incomplete groupings (see summarize_model_run_records).
        return "unknown"
    return "completed"


def summarize_model_run_records(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(records, (dict, str, Path)):
        materialized = normalize_model_run_records(records)
    else:
        materialized = []
        for rec in records:
            materialized.extend(normalize_model_run_records(rec))
    classes = Counter(classify_runtime_finding(rec) for rec in materialized)
    raw_reasons = Counter(_runtime_reason(rec) for rec in materialized)
    failed_or_incomplete = [
        {
            "model_id": rec.get("model_id"),
            "logical_model_id": rec.get("logical_model_id"),
            "classification": classify_runtime_finding(rec),
            "reason": _runtime_reason(rec),
        }
        for rec in materialized
        if classify_runtime_finding(rec) not in {"completed", "partial_valid", "safety-filtered"}
    ]
    failure_groups_by_model: List[Dict[str, Any]] = []
    grouped_by_model: Dict[str, Dict[str, Any]] = {}
    grouped_by_reason: Dict[tuple[str, str], Dict[str, Any]] = {}
    for index, rec in enumerate(failed_or_incomplete):
        model_id = str(rec.get("model_id") or "").strip()
        logical_model_id = str(rec.get("logical_model_id") or "").strip()
        classification = str(rec.get("classification") or "unknown")
        reason = str(rec.get("reason") or "completed")
        # Records without a model_id must not collapse into a single ""-keyed
        # group: that would silently merge distinct failures as if they came
        # from one model. Give each model_id-less record its own group key.
        group_key = model_id if model_id else f"__no_model_id__{index}"
        if group_key not in grouped_by_model:
            grouped_by_model[group_key] = {
                "model_id": model_id,
                "logical_model_id": logical_model_id,
                "classifications": [],
                "reasons": [],
            }
        model_group = grouped_by_model[group_key]
        if classification not in model_group["classifications"]:
            model_group["classifications"].append(classification)
        if reason not in model_group["reasons"]:
            model_group["reasons"].append(reason)

        reason_key = (classification, reason)
        if reason_key not in grouped_by_reason:
            grouped_by_reason[reason_key] = {
                "classification": classification,
                "reason": reason,
                "count": 0,
                "model_ids": [],
            }
        reason_group = grouped_by_reason[reason_key]
        reason_group["count"] += 1
        if model_id and model_id not in reason_group["model_ids"]:
            reason_group["model_ids"].append(model_id)

    failure_groups_by_model = sorted(
        grouped_by_model.values(),
        key=lambda item: (
            item["model_id"],
            item["logical_model_id"],
        ),
    )
    failure_groups_by_reason = sorted(
        grouped_by_reason.values(),
        key=lambda item: (
            item["classification"],
            item["reason"],
        ),
    )
    return {
        "model_runs": len(materialized),
        "models_started": sum(1 for rec in materialized if bool(rec.get("started"))),
        "classification_counts": dict(sorted(classes.items())),
        "reason_counts": dict(sorted(raw_reasons.items())),
        "failed_or_incomplete": failed_or_incomplete,
        "failed_model_ids": [item["model_id"] for item in failure_groups_by_model if item["model_id"]],
        "failure_groups_by_model": failure_groups_by_model,
        "failure_groups_by_reason": failure_groups_by_reason,
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


def _load_json_artifact(path: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "data": None,
        "present": False,
        "error": "",
    }
    try:
        if not path.is_file():
            return result
        result["present"] = True
        result["data"] = load_json_any(path)
        return result
    except json.JSONDecodeError as exc:
        result["error"] = f"parse_error:{exc.msg}"
        return result
    except OSError as exc:
        result["error"] = f"read_error:{exc.__class__.__name__}"
        return result


def _load_json_if_exists(path: Path) -> Any:
    return _load_json_artifact(path)["data"]


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


def _safe_int(value: Any, *, field: str, invalid_fields: List[str], default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        invalid_fields.append(field)
        return default


def _safe_bool(value: Any, *, field: str, invalid_fields: List[str], default: bool = False) -> bool:
    """Accept only a real JSON boolean (Python bool after json.load).

    `bool("false")` is True (any non-empty string is truthy) -- a malformed or
    string-typed field in an artifact must never be silently coerced like that.
    Anything that isn't already a bool is recorded as an invalid-field condition
    and the conservative default is returned instead.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    invalid_fields.append(field)
    return default


def _safe_list(value: Any, *, field: str, invalid_fields: List[str]) -> List[Any]:
    """Only accept an actual list for fields expected to be collections.

    Iterating a non-list directly is a classic footgun: a string silently yields
    its individual characters instead of the intended items, and an int raises
    TypeError. Anything other than a list (or an absent/None value, which is a
    normal "nothing reported" case) is recorded as an invalid-field condition.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    invalid_fields.append(field)
    return []


def summarize_model_selection_decision(decision: Any) -> Dict[str, Any]:
    doc = decision if isinstance(decision, dict) else {}
    invalid_fields: List[str] = []
    chosen_by_role = doc.get("chosen_by_role") if isinstance(doc.get("chosen_by_role"), dict) else {}
    chosen_model_ids = sorted(
        {
            _candidate_model_id(candidate)
            for candidate in chosen_by_role.values()
            if isinstance(candidate, dict) and _candidate_model_id(candidate)
        }
    )
    missing_mandatory_core_roles = _safe_list(
        doc.get("missing_mandatory_core_roles"), field="missing_mandatory_core_roles", invalid_fields=invalid_fields
    )
    return {
        "mode": str(doc.get("mode") or ""),
        "dry_run": _safe_bool(doc.get("dry_run"), field="dry_run", invalid_fields=invalid_fields),
        "ready_to_apply": _safe_bool(doc.get("ready_to_apply"), field="ready_to_apply", invalid_fields=invalid_fields),
        "chosen_roles": len(chosen_by_role),
        "chosen_model_ids": chosen_model_ids,
        "unique_chosen_models": len(chosen_model_ids),
        "staffing_state": str(doc.get("staffing_state") or ""),
        "missing_mandatory_core_roles": missing_mandatory_core_roles,
        "has_dry_run_evaluation_scope": isinstance(doc.get("dry_run_evaluation_scope"), dict),
        "invalid_fields": sorted(set(invalid_fields)),
    }


def summarize_staffing_summary(staffing: Any) -> Dict[str, Any]:
    doc = staffing if isinstance(staffing, dict) else {}
    invalid_fields: List[str] = []
    raw_selected_model_ids = _safe_list(
        doc.get("selected_model_ids"), field="selected_model_ids", invalid_fields=invalid_fields
    )
    selected_model_ids = sorted({str(item).strip() for item in raw_selected_model_ids if str(item).strip()})
    return {
        "staffing_state": str(doc.get("staffing_state") or ""),
        "selected_roles": _safe_int(doc.get("selected_roles"), field="selected_roles", invalid_fields=invalid_fields),
        "target_met_roles": _safe_int(doc.get("target_met_roles"), field="target_met_roles", invalid_fields=invalid_fields),
        "selected_model_count": _safe_int(doc.get("selected_model_count"), field="selected_model_count", invalid_fields=invalid_fields, default=len(selected_model_ids)),
        "selected_model_ids": selected_model_ids,
        "missing_mandatory_core_roles": _safe_list(
            doc.get("missing_mandatory_core_roles"), field="missing_mandatory_core_roles", invalid_fields=invalid_fields
        ),
        "unstaffed_roles": _safe_list(doc.get("unstaffed_roles"), field="unstaffed_roles", invalid_fields=invalid_fields),
        "invalid_fields": invalid_fields,
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
    invalid_fields: List[str] = []
    for role_spec in roles.values():
        if not isinstance(role_spec, dict):
            continue
        role_candidates = _safe_list(role_spec.get("candidates"), field="roles.candidates", invalid_fields=invalid_fields)
        candidate_counts.append(
            _safe_int(
                role_spec.get("candidate_count"),
                field="roles.candidate_count",
                invalid_fields=invalid_fields,
                default=len(role_candidates),
            )
        )
    return {
        "top_n": _safe_int(doc.get("top_n"), field="top_n", invalid_fields=invalid_fields),
        "role_count": len(roles),
        "estimated_compositions": _safe_int(doc.get("estimated_compositions"), field="estimated_compositions", invalid_fields=invalid_fields),
        "valid_compositions": _safe_int(doc.get("valid_compositions"), field="valid_compositions", invalid_fields=invalid_fields, default=len(compositions)),
        "materialized": bool(doc.get("materialized")),
        "missing_candidate_roles": _safe_list(
            doc.get("missing_candidate_roles"), field="missing_candidate_roles", invalid_fields=invalid_fields
        ),
        "total_candidate_slots": sum(candidate_counts),
        "invalid_fields": sorted(set(invalid_fields)),
    }


def summarize_preferred_model_run_records(
    model_run_records: Any,
    tournament: Any,
    *,
    dedicated_loaded: bool = True,
) -> Dict[str, Any]:
    """Prefer the dedicated artifact; fall back to tournament-embedded records only when
    the dedicated artifact is genuinely absent or failed to load.

    A dedicated artifact that is present and validly empty is NOT the same as an absent
    one: silently substituting the embedded source in that case would hide a real
    inconsistency (dedicated source says "zero records", embedded source disagrees).
    Callers must pass `dedicated_loaded=False` only when the dedicated artifact file is
    missing or could not be parsed -- never merely because it normalized to an empty list.
    """
    dedicated = normalize_model_run_records(model_run_records)
    embedded = normalize_model_run_records(tournament)
    if dedicated_loaded:
        summary = summarize_model_run_records(dedicated)
        summary["source"] = "model-run-records.json"
        summary["embedded_model_runs"] = len(embedded)
        summary["dedicated_present_and_empty"] = bool(not dedicated)
        return summary
    summary = summarize_model_run_records(embedded)
    summary["source"] = "role-tournament-results.json:model_run_records"
    summary["embedded_model_runs"] = len(embedded)
    return summary


def _recorded_dry_run_scope_flags(decision_doc: Any) -> Dict[str, Optional[bool]]:
    """Return retry_failed_models/clear_model_health as recorded by the ORIGINAL run.

    `_write_selection_artifacts` persists the flags that were actually in effect for a
    run inside `model-selection-decision.json`'s `dry_run_evaluation_scope`. That is run
    evidence. A CLI flag supplied to THIS analysis invocation is not: re-running the
    analysis tool with different flags on unchanged artifacts must not be able to flip
    the computed gate result. Only a real `bool` recorded in the artifact counts as
    corroboration; anything else (missing key, wrong type, no scope at all) is "not
    recorded" and must not be trusted.
    """
    doc = decision_doc if isinstance(decision_doc, dict) else {}
    scope = doc.get("dry_run_evaluation_scope")
    if not isinstance(scope, dict):
        return {"retry_failed_models": None, "clear_model_health": None}
    retry_val = scope.get("retry_failed_models")
    clear_val = scope.get("clear_model_health")
    return {
        "retry_failed_models": retry_val if isinstance(retry_val, bool) else None,
        "clear_model_health": clear_val if isinstance(clear_val, bool) else None,
    }


def reconcile_full_composite_artifacts(
    root: Path | str,
    *,
    retry_failed_models: bool = False,
    clear_model_health: bool = False,
) -> Dict[str, Any]:
    artifact_paths = forensic_artifact_paths(root)
    artifact_results = {key: _load_json_artifact(path) for key, path in artifact_paths.items()}
    loaded = {key: artifact_results[key]["data"] for key in artifact_paths}

    def artifact_ok(key: str) -> bool:
        result = artifact_results[key]
        return bool(result["present"] and not result["error"])

    decision_summary = summarize_model_selection_decision(loaded["decision"])
    staffing_summary = summarize_staffing_summary(loaded["staffing_summary"])
    candidate_map_summary = summarize_role_candidate_map(loaded["role_candidate_map"])
    tournament_summary = summarize_role_tournament_results(loaded["role_tournament_results"])
    model_run_summary = summarize_preferred_model_run_records(
        loaded["model_run_records"],
        loaded["role_tournament_results"],
        dedicated_loaded=artifact_ok("model_run_records"),
    )
    composite_summary = summarize_composite_selection_plan(loaded["composite_selection_plan"])

    mode = (
        decision_summary["mode"]
        or tournament_summary["selection_mode"]
        or ("full_composite" if loaded["composite_selection_plan"] else "")
    )
    dry_run = bool(decision_summary["dry_run"])

    # CLI flags describe the ANALYST's current invocation, not what actually happened
    # during the run being analyzed. Only trust the recorded run evidence; an unverified
    # CLI claim is ignored for gate computation (never used to relax the gate) rather
    # than trusted outright.
    recorded_flags = _recorded_dry_run_scope_flags(loaded["decision"])
    retry_failed_models_recorded = recorded_flags["retry_failed_models"]
    clear_model_health_recorded = recorded_flags["clear_model_health"]
    effective_retry_failed_models = bool(retry_failed_models_recorded) if retry_failed_models_recorded is not None else False
    effective_clear_model_health = bool(clear_model_health_recorded) if clear_model_health_recorded is not None else False
    cli_retry_failed_models_contradicted = bool(
        retry_failed_models_recorded is not None and bool(retry_failed_models) != retry_failed_models_recorded
    )
    cli_clear_model_health_contradicted = bool(
        clear_model_health_recorded is not None and bool(clear_model_health) != clear_model_health_recorded
    )

    evaluation_scope = classify_full_composite_dry_run_scope(
        model_run_summary,
        mode=mode,
        dry_run=dry_run,
        retry_failed_models=effective_retry_failed_models,
        clear_model_health=effective_clear_model_health,
    )

    mismatches: List[str] = []
    if mode == "full_composite" and not loaded["composite_selection_plan"]:
        mismatches.append("composite_selection_plan_missing_for_full_composite")
    if decision_summary["mode"] and tournament_summary["selection_mode"] and decision_summary["mode"] != tournament_summary["selection_mode"]:
        mismatches.append("selection_mode_mismatch")
    if artifact_ok("staffing_summary") and artifact_ok("role_candidate_map"):
        if staffing_summary["selected_roles"] != candidate_map_summary["selected_roles"]:
            mismatches.append("selected_roles_mismatch")
        if staffing_summary["selected_model_count"] != candidate_map_summary["unique_selected_models"]:
            mismatches.append("selected_model_count_mismatch")
    if artifact_ok("decision") and artifact_ok("role_candidate_map"):
        if decision_summary["chosen_roles"] != candidate_map_summary["chosen_roles"]:
            mismatches.append("chosen_roles_mismatch")
    if artifact_ok("role_tournament_results") and artifact_ok("model_run_records"):
        if tournament_summary["model_run_records_count"] != model_run_summary["model_runs"]:
            mismatches.append("model_run_record_count_mismatch")
    if candidate_map_summary["measured_candidate_count"] > 0 and model_run_summary["model_runs"] == 0:
        mismatches.append("measured_candidates_without_model_run_evidence")
    if candidate_map_summary["selected_roles"] > 0 and model_run_summary["models_started"] == 0:
        mismatches.append("selected_roles_without_started_models")
    if decision_summary["ready_to_apply"] and staffing_summary["missing_mandatory_core_roles"]:
        mismatches.append("ready_to_apply_with_missing_mandatory_roles")
    if artifact_ok("composite_selection_plan") and artifact_ok("role_candidate_map"):
        if composite_summary["role_count"] != candidate_map_summary["role_count"]:
            mismatches.append("composite_role_count_mismatch")
    if model_run_summary.get("dedicated_present_and_empty") and model_run_summary.get("embedded_model_runs"):
        mismatches.append("dedicated_model_run_records_empty_but_embedded_present")
    if decision_summary["invalid_fields"]:
        mismatches.append("model_selection_decision_invalid_fields")
    if staffing_summary["invalid_fields"]:
        mismatches.append("staffing_summary_invalid_fields")
    if composite_summary["invalid_fields"]:
        mismatches.append("composite_selection_plan_invalid_fields")

    artifact_integrity_blockers: List[str] = []
    for key, result in artifact_results.items():
        if result["error"]:
            artifact_integrity_blockers.append(f"{key}_artifact_{str(result['error']).split(':', 1)[0]}")
        elif not result["present"]:
            artifact_integrity_blockers.append(f"{key}_artifact_missing")

    gate_blockers = list(dict.fromkeys([*evaluation_scope["blocking_reasons"], *mismatches, *artifact_integrity_blockers]))
    return {
        "ok": not artifact_integrity_blockers,
        "mode": mode,
        "dry_run": dry_run,
        "artifacts": {
            key: {
                "path": str(path),
                "present": bool(artifact_results[key]["present"]),
                "loaded": loaded[key] is not None,
                "error": str(artifact_results[key]["error"]),
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
        "cli_flag_provenance": {
            "retry_failed_models_cli_argument": bool(retry_failed_models),
            "clear_model_health_cli_argument": bool(clear_model_health),
            "retry_failed_models_recorded": retry_failed_models_recorded,
            "clear_model_health_recorded": clear_model_health_recorded,
            "retry_failed_models_effective": effective_retry_failed_models,
            "clear_model_health_effective": effective_clear_model_health,
            "cli_retry_failed_models_contradicted_by_evidence": cli_retry_failed_models_contradicted,
            "cli_clear_model_health_contradicted_by_evidence": cli_clear_model_health_contradicted,
        },
        "artifact_integrity_blockers": artifact_integrity_blockers,
        "max_complexity_gate": {
            "accepted": bool(evaluation_scope["ok_to_label_max_complexity"] and not mismatches and not artifact_integrity_blockers),
            "blocking_reasons": gate_blockers,
        },
    }


def locate_operator_degraded_apply(root: Path) -> Optional[Path]:
    """Find the real degraded apply run, explicitly excluding plan-only dirs."""
    root = Path(root)
    candidates: List[tuple[tuple[int, int, int, str], Path]] = []
    for path in root.glob("operator_degraded_apply_*"):
        if not path.is_dir():
            continue
        if path.name.startswith("operator_degraded_apply_plan_"):
            continue
        summary = path / OPERATOR_APPLY_SUMMARY
        post_apply = path / "post_apply_artifacts"
        has_summary = summary.is_file()
        has_post_apply = post_apply.is_dir()
        if has_summary or has_post_apply:
            candidates.append((
                (
                    int(has_summary and has_post_apply),
                    int(has_summary),
                    int(has_post_apply),
                    path.name,
                ),
                path,
            ))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


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


def _reconcile_direct_and_summary_health(direct: Any, summary_value: Any) -> tuple[bool, bool]:
    """Give a direct, current health probe precedence over an indirect summary field.

    ``direct`` is expected to be the freshly-collected probe artifact (e.g. a
    ``gateway_health`` document); ``summary_value`` is a possibly-stale field pulled
    from an apply summary recorded earlier/elsewhere. When both are present and they
    disagree, this is a genuine conflict worth surfacing rather than something an
    ``or`` should silently paper over by letting the stale/indirect field win.

    Returns ``(effective_ok, conflict)``.
    """
    direct_present = isinstance(direct, dict) and bool(direct)
    direct_ok = _bool_from_health(direct) if direct_present else None
    summary_present = summary_value is not None
    summary_ok = _bool_from_health(summary_value) if summary_present else None
    if direct_ok is not None and summary_ok is not None and direct_ok != summary_ok:
        return direct_ok, True
    if direct_ok is not None:
        return direct_ok, False
    if summary_ok is not None:
        return summary_ok, False
    return False, False


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

    # Do NOT fall back to the *current* epoch id here: the current epoch is merely
    # what is active right now, not evidence of what an apply actually applied. If
    # neither the apply summary nor the firstboot status recorded an explicit
    # applied_epoch_id, that is missing evidence, not something to fabricate by
    # borrowing the current epoch id.
    applied_epoch_id = str(
        apply_doc.get("applied_epoch_id")
        or status_doc.get("applied_epoch_id")
        or ""
    ).strip()
    current_epoch_target = str(epoch_doc.get("current_target") or epoch_doc.get("epoch_dir") or "").strip()
    current_epoch_id = str(epoch_doc.get("current_epoch_id") or "").strip()
    post_backend_ok = _bool_from_health(backend_doc) or _bool_from_health(apply_doc.get("post_backend_ok")) or _bool_from_health(apply_doc.get("main_backend_smoke"))
    post_gateway_ok, post_gateway_health_conflict = _reconcile_direct_and_summary_health(
        gateway_doc, apply_doc.get("post_gateway_ok")
    )
    toolproxy_ok = _bool_from_health(toolproxy_doc)

    probe = gateway_probe_spec()
    observed_socket = str(gateway_doc.get("socket") or gateway_doc.get("sock") or gateway_doc.get("path") or apply_doc.get("gateway_socket") or "").strip()
    observed_protocol = str(gateway_doc.get("protocol") or apply_doc.get("gateway_protocol") or "").strip()
    canonical_protocol_aliases = {probe["protocol"], "http", "http_unix", "http_over_unix_socket"}
    gateway_probe_metadata_recorded = bool(observed_socket or observed_protocol)
    # Affirmative evidence is required for BOTH the socket and the protocol before a
    # probe is confirmed canonical. An absent/empty value must never silently satisfy
    # this check (it previously matched via `observed_socket in {"", canonical}`,
    # which let a probe that was never recorded at all pass as "canonical").
    canonical_probe_used = bool(
        observed_socket
        and observed_protocol
        and observed_socket == probe["socket"]
        and observed_protocol in canonical_protocol_aliases
    )
    if not gateway_probe_metadata_recorded:
        gateway_probe_evidence = "unrecorded"
    elif canonical_probe_used:
        gateway_probe_evidence = "canonical"
    else:
        gateway_probe_evidence = "mismatch"

    blockers: List[str] = []
    if not applied_epoch_id:
        blockers.append("applied_epoch_id_missing")
    if not current_epoch_target:
        blockers.append("current_epoch_target_missing")
    if applied_epoch_id and current_epoch_id and applied_epoch_id != current_epoch_id:
        blockers.append("applied_epoch_current_epoch_mismatch")
    if epoch_doc.get("problems"):
        blockers.extend(f"contracts:{item}" for item in epoch_doc.get("problems") or [])
    if post_gateway_health_conflict:
        blockers.append("post_gateway_health_conflict")
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
        "post_gateway_health_conflict": post_gateway_health_conflict,
        "toolproxy_diag_ok": toolproxy_ok,
        "canonical_gateway_probe": probe,
        "canonical_gateway_probe_used": canonical_probe_used,
        "gateway_probe_evidence": gateway_probe_evidence,
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
    return 0 if report["ok"] and report["max_complexity_gate"]["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
