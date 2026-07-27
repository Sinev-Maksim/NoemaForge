#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/evolution_adapters/night_watch_readonly.py
Zone: release/package
Version: 0.33.0
Created: 2026-07-27
Modified: 2026-07-27
Purpose: Project untrusted night_watch/current-loop state into canonical Evolution
  execution contracts without invoking or mutating the observed runtime.
Inputs: A selected local state root and bounded known state artifacts.
Outputs: Deterministic read-only probe, snapshot, artifact and blocker JSON.
Side effects: None; CLI writes JSON to stdout only.
Tests: pytest -q noemaforge/tests/test_night_watch_readonly_adapter.py
Notes: Classification is "UAT request findings resolution". Reference samples
  stay local-only and no reference runtime or source file is shipped.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import evolution_execution_contracts_runtime as contracts


ADAPTER_ID = "evolution.observer.night-watch"
ADAPTER_VERSION = "noemaforge.evolution.night-watch-readonly/v1"
CANONICAL_API_VERSION = "noemaforge.evolution-execution/v1"
PROVENANCE = "UAT request findings resolution"

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_ARTIFACTS = 250
SHA40 = re.compile(r"^[0-9a-f]{40}$")
STATUS_LINE = re.compile(r"^-\s*([A-Za-z0-9_.-]+):\s*(.*)$")

READ_OPERATIONS = ("probe", "snapshot", "artifacts", "blockers")
FORBIDDEN_ACTIONS = (
    "start",
    "stop",
    "pause",
    "resume",
    "cancel",
    "apply",
    "commit",
    "push",
    "merge",
    "service_control",
    "github_write",
    "model_invoke",
)

ARTIFACT_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("status.md", "coordinator_status"),
    ("ledger.md", "coordinator_ledger"),
    ("coordinator-lock-v51.json", "coordinator_lock"),
    ("last-staged-paths.txt", "staged_paths"),
    ("scheduler/open-pr-snapshot.json", "github_snapshot"),
    ("scheduler/pr-creation-epochs.json", "pr_creation_ledger"),
    ("scheduler/pr-*.json", "scheduler_pr_state"),
    ("scheduler-v51/pr-*.json", "scheduler_pr_state_legacy"),
    ("scheduler-v47/pr-*.json", "scheduler_pr_state_legacy"),
    ("work-items-v51/issue-*.json", "issue_work_item"),
    ("work-items-v51/recovery/*", "issue_recovery"),
    ("review-threads-v46/parked-prs/pr-*.json", "parked_review"),
    ("issues-v39/manual-pending/*", "manual_evidence_pending"),
    ("security-v36/last-branch-gate.txt", "security_gate"),
    ("evolution-v43/**/*.json", "evolution_evidence"),
    ("evolution-v43/**/*.md", "evolution_evidence"),
    ("visual-v44/**/*.json", "visual_evidence"),
    ("visual-v44/**/*.md", "visual_evidence"),
    ("semantic-loops/**/*.quarantined", "quarantine_marker"),
    ("*-pause-until.txt", "provider_pause_marker"),
    ("*-write-blocked-until.txt", "provider_write_block_marker"),
    ("logs/*.log", "loop_log"),
)


def _stable_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(_stable_json(payload)).hexdigest()


def exact_head(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    return text if SHA40.fullmatch(text) else None


def integer_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def observed_timestamp(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        return text
    return "unknown"


def parse_status(text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    inside_fence = False
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            inside_fence = not inside_fence
            continue
        if inside_fence:
            continue
        match = STATUS_LINE.match(line)
        if match:
            values[match.group(1)] = match.group(2).strip()
    return values


def _dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    seen: set[str] = set()
    result: List[Path] = []
    for path in paths:
        key = os.path.abspath(os.path.expanduser(str(path)))
        if key not in seen:
            seen.add(key)
            result.append(Path(key))
    return result


def candidate_state_roots(
    explicit: Optional[Path | str] = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
    home: Optional[Path | str] = None,
) -> List[Path]:
    env = dict(os.environ if environ is None else environ)
    home_path = Path(home or env.get("HOME") or Path.home())
    candidates: List[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    for key in ("NIGHT_WATCH_STATE_ROOT", "STATE_ROOT", "NF_V46_STATE_DIR"):
        if env.get(key):
            candidates.append(Path(env[key]))
    candidates.extend(
        [
            home_path / ".local/share/noemaforge-agent-runs/token-aware-0330-v46",
            home_path / ".local/share/noemaforge-agent-runs/token-aware-0330-v3",
        ]
    )
    return _dedupe_paths(candidates)


def _root_score(root: Path) -> Tuple[int, List[str]]:
    indicators = {
        "status.md": 6,
        "coordinator-lock-v51.json": 5,
        "scheduler": 4,
        "work-items-v51": 3,
        "logs": 2,
        "ledger.md": 1,
    }
    present = [name for name in indicators if (root / name).exists()]
    return sum(indicators[name] for name in present), present


def probe(
    state_root: Optional[Path | str] = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
    home: Optional[Path | str] = None,
) -> Dict[str, Any]:
    records: List[Dict[str, Any]] = []
    for order, root in enumerate(
        candidate_state_roots(state_root, environ=environ, home=home)
    ):
        score, indicators = _root_score(root)
        records.append(
            {
                "path": str(root),
                "exists": root.exists(),
                "score": score,
                "indicators": indicators,
                "order": order,
            }
        )

    if not records:
        selected = {
            "path": "",
            "exists": False,
            "score": 0,
            "indicators": [],
            "order": 0,
        }
    elif state_root is not None:
        selected = records[0]
    else:
        selected = max(records, key=lambda item: (item["score"], -item["order"]))

    active = [item for item in records if item["score"] > 0]
    warnings: List[str] = []
    if len(active) > 1:
        warnings.append("multiple_night_watch_state_roots_detected")
    if (
        any("token-aware-0330-v46" in item["path"] for item in active)
        and any("token-aware-0330-v3" in item["path"] for item in active)
    ):
        warnings.append("v46_and_v3_state_layouts_both_present")
    if selected["score"] == 0:
        warnings.append("night_watch_state_not_detected")

    return {
        "apiVersion": ADAPTER_VERSION,
        "kind": "NightWatchReadOnlyProbe",
        "adapter_id": ADAPTER_ID,
        "mode": "read_only",
        "available": selected["score"] > 0,
        "selected_state_root": selected["path"],
        "candidates": records,
        "operations": list(READ_OPERATIONS),
        "mutating_operations": [],
        "warnings": sorted(set(warnings)),
    }


def contained_file(
    root: Path | str,
    relative: str,
    *,
    max_bytes: int = MAX_FILE_BYTES,
) -> Tuple[Optional[Path], Optional[str]]:
    base = Path(root).resolve()
    try:
        resolved = (base / relative).resolve(strict=True)
    except (OSError, RuntimeError):
        return None, "missing_or_unresolvable"
    try:
        if os.path.commonpath([str(base), str(resolved)]) != str(base):
            return None, "path_escape"
    except ValueError:
        return None, "path_escape"
    try:
        if not resolved.is_file():
            return None, "not_file"
        if resolved.stat().st_size > max_bytes:
            return None, "oversized"
    except OSError:
        return None, "stat_failed"
    return resolved, None


def read_text(root: Path | str, relative: str, warnings: List[str]) -> Optional[str]:
    path, error = contained_file(root, relative)
    if path is None:
        if error not in {"missing_or_unresolvable", "not_file"}:
            warnings.append(f"{relative}:{error}")
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        warnings.append(f"{relative}:read_failed")
        return None


def read_json(
    root: Path | str,
    relative: str,
    warnings: List[str],
) -> Optional[Dict[str, Any]]:
    text = read_text(root, relative, warnings)
    if text is None:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        warnings.append(f"{relative}:malformed_json")
        return None
    if not isinstance(value, dict):
        warnings.append(f"{relative}:json_not_object")
        return None
    return value


def artifacts(
    state_root: Path | str,
    *,
    max_artifacts: int = MAX_ARTIFACTS,
) -> Dict[str, Any]:
    root = Path(state_root)
    warnings: List[str] = []
    records: Dict[str, Dict[str, Any]] = {}
    limit_reached = False

    for pattern, artifact_kind in ARTIFACT_PATTERNS:
        for candidate in sorted(root.glob(pattern)):
            if len(records) >= max_artifacts:
                limit_reached = True
                break
            try:
                relative = str(candidate.relative_to(root))
            except ValueError:
                warnings.append(f"{candidate}:path_escape")
                continue
            path, error = contained_file(root, relative)
            if path is None:
                if error not in {"missing_or_unresolvable", "not_file"}:
                    warnings.append(f"{relative}:{error}")
                continue
            try:
                payload = path.read_bytes()
                stat = path.stat()
            except OSError:
                warnings.append(f"{relative}:read_failed")
                continue
            digest = hashlib.sha256(payload).hexdigest()
            records[relative] = {
                "artifact_id": f"sha256:{digest}",
                "relative_path": relative,
                "artifact_kind": artifact_kind,
                "size_bytes": stat.st_size,
                "sha256": digest,
                "source": "night_watch_readonly",
            }
        if limit_reached:
            break

    if limit_reached:
        warnings.append("artifact_limit_reached")

    ordered = [records[key] for key in sorted(records)]
    fingerprint_payload = [
        {
            "relative_path": item["relative_path"],
            "sha256": item["sha256"],
            "size_bytes": item["size_bytes"],
        }
        for item in ordered
    ]
    return {
        "artifacts": ordered,
        "source_fingerprint": stable_hash(fingerprint_payload),
        "warnings": sorted(set(warnings)),
    }


def blockers(
    state_root: Path | str,
    *,
    status: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    root = Path(state_root)
    warnings: List[str] = []
    status_values = dict(
        status or parse_status(read_text(root, "status.md", warnings) or "")
    )
    records: List[Dict[str, Any]] = []

    def add(kind: str, source: str, details: Mapping[str, Any]) -> None:
        record = {
            "blocker_kind": kind,
            "source": source,
            "details": dict(details),
        }
        record["fingerprint"] = stable_hash(record)
        records.append(record)

    stage = str(status_values.get("stage") or "")
    if any(
        token in stage.lower()
        for token in ("blocked", "waiting", "parked", "deferred", "quarantine")
    ):
        add("stage", "status.md", {"stage": stage})

    for key, raw_value in sorted(status_values.items()):
        value = str(raw_value or "")
        lower = value.lower()
        if key.endswith("_gate") and lower not in {
            "pass",
            "passed",
            "green",
            "ok",
            "none",
            "not-applicable",
        }:
            add("gate", "status.md", {"gate": key, "value": value})
        if key.endswith("_pending"):
            count = integer_or_none(value)
            if count is not None and count > 0:
                add(
                    "manual_or_target_pending",
                    "status.md",
                    {"field": key, "count": count},
                )

    for pattern, kind in (
        ("*-pause-until.txt", "provider_pause"),
        ("*-write-blocked-until.txt", "provider_write_block"),
    ):
        for candidate in sorted(root.glob(pattern)):
            relative = str(candidate.relative_to(root))
            add(
                kind,
                relative,
                {
                    "until": (
                        read_text(root, relative, warnings) or ""
                    ).strip()
                    or None
                },
            )

    quarantine_root = root / "semantic-loops"
    if quarantine_root.is_dir():
        for candidate in sorted(quarantine_root.rglob("*.quarantined")):
            relative = str(candidate.relative_to(root))
            path, error = contained_file(root, relative)
            if path is not None:
                add("quarantined_semantic_loop", relative, {})
            elif error not in {"missing_or_unresolvable", "not_file"}:
                warnings.append(f"{relative}:{error}")

    parked_root = root / "review-threads-v46/parked-prs"
    if parked_root.is_dir():
        for candidate in sorted(parked_root.glob("pr-*.json")):
            relative = str(candidate.relative_to(root))
            payload = read_json(root, relative, warnings) or {}
            add(
                "parked_review",
                relative,
                {
                    "pr": payload.get("pr"),
                    "reason": payload.get("reason"),
                    "head": exact_head(payload.get("head")),
                },
            )

    manual_root = root / "issues-v39/manual-pending"
    if manual_root.is_dir():
        for candidate in sorted(manual_root.glob("*")):
            relative = str(candidate.relative_to(root))
            path, error = contained_file(root, relative)
            if path is not None:
                add("manual_evidence_pending", relative, {})
            elif error not in {"missing_or_unresolvable", "not_file"}:
                warnings.append(f"{relative}:{error}")

    deduped = {item["fingerprint"]: item for item in records}
    return {
        "blockers": [deduped[key] for key in sorted(deduped)],
        "warnings": sorted(set(warnings)),
    }


def canonical_status(value: Any, warnings: List[str], source: str) -> str:
    phase = str(value or "").strip().lower()
    if any(token in phase for token in ("merged", "completed", "done", "released")):
        return "completed"
    if any(token in phase for token in ("failed", "error", "fatal")):
        return "failed"
    if any(
        token in phase
        for token in (
            "blocked",
            "quarantine",
            "duplicate",
            "pause",
            "defer",
            "waiting",
            "parked",
        )
    ):
        return "blocked"
    if any(
        token in phase
        for token in ("active", "running", "in_progress", "in-progress", "review", "ready")
    ):
        return "ready"
    if phase in {"", "planned", "queued", "discovered", "unknown"}:
        return "planned"
    warnings.append(f"{source}:unknown_phase:{phase}")
    return "planned"


def _work_item(
    *,
    work_item_id: str,
    run_id: str,
    status: str,
    objective: str,
) -> Dict[str, Any]:
    return {
        "apiVersion": CANONICAL_API_VERSION,
        "kind": "EvolutionWorkItem",
        "work_item_id": work_item_id,
        "run_id": run_id,
        "status": status,
        "provenance": PROVENANCE,
        "objective": objective,
        "requires_operator_approval": True,
        "toolproxy_required": True,
        "allowed_actions": ["observe", "inspect_evidence"],
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }


def _issue_work_items(
    root: Path,
    run_id: str,
    warnings: List[str],
) -> Tuple[List[Dict[str, Any]], set[int]]:
    items: List[Dict[str, Any]] = []
    linked_prs: set[int] = set()
    directory = root / "work-items-v51"
    paths = sorted(directory.glob("issue-*.json")) if directory.is_dir() else []

    for path in paths:
        relative = str(path.relative_to(root))
        payload = read_json(root, relative, warnings)
        if not payload:
            continue
        issue = integer_or_none(payload.get("issue"))
        if issue is None or issue <= 0:
            warnings.append(f"{relative}:invalid_issue_number")
            continue
        pr = integer_or_none(payload.get("pr"))
        if pr is not None and pr > 0:
            linked_prs.add(pr)
        items.append(
            _work_item(
                work_item_id=f"night-watch:issue:{issue}",
                run_id=run_id,
                status=canonical_status(
                    payload.get("phase"),
                    warnings,
                    relative,
                ),
                objective=f"Observe evidence and disposition for issue #{issue}.",
            )
        )
    return items, linked_prs


def _pr_work_items(
    root: Path,
    run_id: str,
    linked_prs: set[int],
    warnings: List[str],
) -> List[Dict[str, Any]]:
    candidates: List[Path] = []
    for directory_name in ("scheduler", "scheduler-v51", "scheduler-v47"):
        directory = root / directory_name
        if directory.is_dir():
            candidates.extend(directory.glob("pr-*.json"))

    items: List[Dict[str, Any]] = []
    seen: set[int] = set()
    for path in sorted(set(candidates)):
        relative = str(path.relative_to(root))
        payload = read_json(root, relative, warnings)
        if not payload:
            continue
        pr = integer_or_none(payload.get("pr"))
        if pr is None or pr <= 0:
            warnings.append(f"{relative}:invalid_pr_number")
            continue
        if pr in linked_prs or pr in seen:
            continue
        seen.add(pr)

        full_head = exact_head(
            payload.get("last_seen_head")
            or payload.get("head")
            or payload.get("reviewed_head")
        )
        raw_head = (
            payload.get("last_seen_head")
            or payload.get("head")
            or payload.get("reviewed_head")
        )
        if raw_head and full_head is None:
            warnings.append(f"{relative}:head_not_full_sha")

        trusted = payload.get("history_trusted")
        reviewed = payload.get("broad_review_done")
        if trusted is False:
            status = "blocked"
        elif reviewed is True and full_head is not None:
            status = "completed"
        else:
            status = canonical_status(
                payload.get("phase") or payload.get("status") or "ready",
                warnings,
                relative,
            )

        items.append(
            _work_item(
                work_item_id=f"night-watch:pr:{pr}",
                run_id=run_id,
                status=status,
                objective=f"Observe review and remediation evidence for PR #{pr}.",
            )
        )
    return items


def _schema_shape_failures(doc: Mapping[str, Any]) -> List[str]:
    kind = str(doc.get("kind") or "")
    filename = contracts.CONTRACT_KINDS.get(kind)
    if not filename:
        return [f"{kind or 'unknown'}:schema_not_registered"]
    schema = json.loads(
        (contracts.CONTRACTS_ROOT / filename).read_text(encoding="utf-8")
    )
    failures: List[str] = []
    required = schema.get("required") if isinstance(schema.get("required"), list) else []
    for key in required:
        if key not in doc:
            failures.append(f"{kind}:required_field_missing:{key}")
    properties = (
        schema.get("properties")
        if isinstance(schema.get("properties"), dict)
        else {}
    )
    unknown = sorted(set(doc) - set(properties))
    if schema.get("additionalProperties") is False and unknown:
        failures.append(f"{kind}:unknown_fields:{','.join(unknown)}")
    for key, definition in properties.items():
        if key not in doc or not isinstance(definition, dict):
            continue
        if "const" in definition and doc[key] != definition["const"]:
            failures.append(f"{kind}:const_mismatch:{key}")
        if "enum" in definition and doc[key] not in definition["enum"]:
            failures.append(f"{kind}:enum_mismatch:{key}")
    return failures


def validate_projection(
    run: Mapping[str, Any],
    work_items: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    documents: List[Mapping[str, Any]] = [run, *work_items]
    failures: List[str] = []
    for document in documents:
        failures.extend(contracts.validate_contract_doc(document))
        failures.extend(_schema_shape_failures(document))

    work_item_ids = [str(item.get("work_item_id") or "") for item in work_items]
    if len(work_item_ids) != len(set(work_item_ids)):
        failures.append("projection:duplicate_work_item_ids")
    if list(run.get("work_items") or []) != work_item_ids:
        failures.append("projection:run_work_item_references_mismatch")

    return {
        "ok": not failures,
        "failures": sorted(set(failures)),
        "document_count": len(documents),
        "canonical_api_version": CANONICAL_API_VERSION,
    }


def snapshot(
    state_root: Optional[Path | str] = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
    home: Optional[Path | str] = None,
) -> Dict[str, Any]:
    probe_result = probe(state_root, environ=environ, home=home)
    root = Path(probe_result["selected_state_root"])
    warnings: List[str] = list(probe_result["warnings"])

    status_text = read_text(root, "status.md", warnings) or ""
    status_values = parse_status(status_text)
    lock = read_json(root, "coordinator-lock-v51.json", warnings) or {}

    artifact_result = artifacts(root)
    blocker_result = blockers(root, status=status_values)
    warnings.extend(artifact_result["warnings"])
    warnings.extend(blocker_result["warnings"])

    source_fingerprint = artifact_result["source_fingerprint"]
    run_id = f"night-watch:{source_fingerprint[:20]}"

    issue_items, linked_prs = _issue_work_items(root, run_id, warnings)
    work_items = issue_items + _pr_work_items(
        root,
        run_id,
        linked_prs,
        warnings,
    )
    work_items = sorted(work_items, key=lambda item: item["work_item_id"])

    raw_head = status_values.get("head") or lock.get("head")
    full_head = exact_head(raw_head)
    if raw_head and full_head is None:
        warnings.append("observed_head_not_full_sha")

    created_at = observed_timestamp(
        lock.get("started_at"),
        status_values.get("timestamp"),
        status_values.get("updated_at"),
    )
    if created_at == "unknown":
        warnings.append("observed_timestamp_unknown")

    run = {
        "apiVersion": CANONICAL_API_VERSION,
        "kind": "EvolutionRun",
        "run_id": run_id,
        "created_at": created_at,
        "provenance": PROVENANCE,
        "runtime_neutral": True,
        "external_reference_policy": {
            "source_samples_local_only": True,
            "reference_runtime_shipped": False,
        },
        "safety_invariants": {
            "single_active_heavy_llm": True,
            "explicit_operator_approval": True,
            "toolproxy_capability_boundary": True,
            "contract_epochs_runtime_immutable": True,
            "no_hidden_llm_media_camera_microphone_gpu_autostart": True,
        },
        "work_items": [item["work_item_id"] for item in work_items],
        "resource_leases": [],
        "events": [],
        "agent_requests": [],
        "agent_results": [],
        "mutation_evidence": [],
        "review_evidence": [],
        "release_gate_results": [],
    }

    validation = validate_projection(run, work_items)
    active_agent_raw = str(status_values.get("active_agent") or "").strip()
    active_agent = (
        None
        if active_agent_raw.lower() in {"", "none", "unknown", "null"}
        else active_agent_raw
    )

    return {
        "apiVersion": ADAPTER_VERSION,
        "kind": "NightWatchReadOnlySnapshot",
        "adapter_id": ADAPTER_ID,
        "mode": "read_only",
        "available": probe_result["available"],
        "state_root": str(root),
        "source_fingerprint": source_fingerprint,
        "observed_timestamp": created_at,
        "source_observations": {
            "exact_head": full_head,
            "stage": status_values.get("stage") or None,
            "repository": lock.get("repo") or None,
            "base_ref": lock.get("base") or None,
        },
        "probe": probe_result,
        "evolution_run": run,
        "work_items": work_items,
        "artifacts": artifact_result["artifacts"],
        "blockers": blocker_result["blockers"],
        "resource_usage": {
            "active_agent": active_agent,
            "cycle": integer_or_none(status_values.get("cycle")),
            "artifact_count": len(artifact_result["artifacts"]),
            "work_item_count": len(work_items),
            "blocker_count": len(blocker_result["blockers"]),
            "token_usage": None,
            "cpu_usage": None,
            "ram_usage": None,
            "vram_usage": None,
        },
        "warnings": sorted(set(warnings)),
        "operations": list(READ_OPERATIONS),
        "mutating_operations": [],
        "canonical_validation": validation,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="noemaforge-night-watch-readonly")
    parser.add_argument(
        "operation",
        choices=list(READ_OPERATIONS),
    )
    parser.add_argument("--state-root")
    args = parser.parse_args(argv)

    if args.operation == "probe":
        result = probe(args.state_root)
    elif args.operation == "snapshot":
        result = snapshot(args.state_root)
    else:
        selected = probe(args.state_root)["selected_state_root"]
        if args.operation == "artifacts":
            result = artifacts(selected)
        else:
            result = blockers(selected)

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.operation == "snapshot":
        return 0 if result["canonical_validation"]["ok"] else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
