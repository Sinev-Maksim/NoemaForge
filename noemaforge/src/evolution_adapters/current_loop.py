#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/evolution_adapters/current_loop.py
Zone: release/package
Version: 0.33.0
Created: 2026-07-18
Modified: 2026-07-18
Purpose: Observe the current prod-ready loop through NF-native Evolution contracts.
Inputs: A selected current-loop state root and known read-only state artifacts.
Outputs: Probe, snapshot, artifact and blocker JSON documents.
Side effects: None; the adapter never writes source state or invokes loop commands.
Tests: pytest -q noemaforge/tests/test_current_loop_readonly_adapter.py
Notes: UAT request findings resolution; all reads are bounded and root-contained.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .current_loop_io import (
    ADAPTER_ID,
    MAX_FILE_BYTES,
    artifacts,
    candidate_state_roots,
    contained_file,
    date_time,
    exact_head,
    integer,
    nowz,
    parse_status,
    probe,
    read_json,
    read_text,
    stable_hash,
)
from .current_loop_normalize import issue_work_items, pr_work_items

# Backward-compatible test/debug alias; no write-capable helper is exported.
_contained_file = contained_file


def blockers(state_root: Path | str, *, status: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    root = Path(state_root)
    warnings: List[str] = []
    found: List[Dict[str, Any]] = []
    state = dict(status or parse_status(read_text(root, "status.md", warnings) or ""))

    def add(kind: str, source: str, details: Dict[str, Any]) -> None:
        record = {"kind": kind, "source": source, "details": details}
        record["fingerprint"] = stable_hash(record)
        found.append(record)

    stage = state.get("stage", "")
    if any(token in stage.lower() for token in ("blocked", "waiting", "parked", "deferred", "quarantine")):
        add("stage", "status.md", {"stage": stage})
    for key, value in sorted(state.items()):
        lower = value.lower()
        if key.endswith("_gate") and lower not in {"pass", "passed", "green", "ok", "none", "not-applicable"}:
            add("gate", "status.md", {"gate": key, "value": value})
        if key.endswith("_pending") and integer(value) > 0:
            add("manual_or_target_pending", "status.md", {"field": key, "count": integer(value)})
    for pattern, kind in (
        ("*-pause-until.txt", "provider_pause"),
        ("*-write-blocked-until.txt", "provider_write_block"),
    ):
        for path in sorted(root.glob(pattern)):
            relative = str(path.relative_to(root))
            add(kind, relative, {"until": (read_text(root, relative, warnings) or "").strip() or "unknown"})
    quarantine = root / "semantic-loops"
    for path in sorted(quarantine.rglob("*.quarantined")) if quarantine.is_dir() else []:
        add("quarantined_semantic_loop", str(path.relative_to(root)), {})
    parked = root / "review-threads-v46/parked-prs"
    for path in sorted(parked.glob("pr-*.json")) if parked.is_dir() else []:
        relative = str(path.relative_to(root))
        payload = read_json(root, relative, warnings) or {}
        add("parked_review", relative, {
            "pr": payload.get("pr"),
            "reason": payload.get("reason"),
            "head": payload.get("head"),
        })
    manual = root / "issues-v39/manual-pending"
    for path in sorted(manual.glob("*")) if manual.is_dir() else []:
        if path.is_file():
            add("manual_evidence_pending", str(path.relative_to(root)), {})
    return {
        "blockers": sorted(found, key=lambda item: item["fingerprint"]),
        "warnings": sorted(set(warnings)),
    }


def snapshot(
    state_root: Optional[Path | str] = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
    home: Optional[Path | str] = None,
    captured_at: Optional[str] = None,
) -> Dict[str, Any]:
    captured = captured_at or nowz()
    probe_result = probe(state_root, environ=environ, home=home)
    root = Path(probe_result["selected_state_root"])
    warnings: List[str] = list(probe_result["warnings"])
    state = parse_status(read_text(root, "status.md", warnings) or "")
    lock = read_json(root, "coordinator-lock-v51.json", warnings) or {}
    repo = str(lock.get("repo") or "Sinev-Maksim/NoemaForge")
    base = str(lock.get("base") or "release/0.33.0-dev")
    run_id = "current-loop:" + hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]

    issue_items, linked_prs = issue_work_items(root, repo, warnings)
    work_items = issue_items + pr_work_items(root, repo, linked_prs, warnings)
    for item in work_items:
        item["run_id"] = run_id
    blocker_result = blockers(root, status=state)
    artifact_result = artifacts(root)
    warnings.extend(blocker_result["warnings"])
    warnings.extend(artifact_result["warnings"])

    head = exact_head(state.get("head"))
    if state.get("head") and head is None:
        warnings.append("status_head_is_not_full_sha")
    stage = state.get("stage", "")
    if any(token in stage.lower() for token in ("complete", "release-ready")):
        run_status = "completed"
    elif lock:
        run_status = "running"
    elif blocker_result["blockers"]:
        run_status = "blocked"
    elif state:
        run_status = "paused"
    else:
        run_status = "planned"
    manual_pending = any(
        item["kind"] in {"manual_evidence_pending", "manual_or_target_pending"}
        for item in blocker_result["blockers"]
    )

    run = {
        "apiVersion": "noemaforge.evolution.run/v1",
        "kind": "EvolutionRun",
        "run_id": run_id,
        "project_id": "noemaforge",
        "mission": f"Observe current prod-ready loop for {repo}@{base}",
        "status": run_status,
        "created_at": date_time(
            lock.get("started_at") or state.get("timestamp"), captured, warnings, "created_at"
        ),
        "updated_at": date_time(state.get("timestamp"), captured, warnings, "updated_at"),
        "source_adapter": ADAPTER_ID,
        "policy_epoch": "external-loop-v46-r12",
        "exact_base_head": head,
        "current_stage": stage or None,
        "work_item_ids": [item["work_item_id"] for item in work_items],
        "approval_state": "pending" if manual_pending else "not_required",
        "provenance": {
            "classification": "UAT request findings resolution",
            "reference_material": "local-only",
            "external_source_code_imported": False,
        },
    }
    return {
        "apiVersion": "noemaforge.evolution.current-loop-snapshot/v1",
        "kind": "CurrentLoopSnapshot",
        "adapter_id": ADAPTER_ID,
        "mode": "read_only",
        "captured_at": captured,
        "available": probe_result["available"],
        "state_root": str(root),
        "probe": probe_result,
        "evolution_run": run,
        "work_items": work_items,
        "artifacts": artifact_result["artifacts"],
        "blockers": blocker_result["blockers"],
        "resource_usage": {
            "active_agent": state.get("active_agent", "none"),
            "cycle": integer(state.get("cycle")),
            "artifact_count": len(artifact_result["artifacts"]),
            "work_item_count": len(work_items),
            "blocker_count": len(blocker_result["blockers"]),
            "token_usage": None,
            "cpu_usage": None,
            "ram_usage": None,
            "vram_usage": None,
        },
        "warnings": sorted(set(warnings)),
        "operations": ["probe", "snapshot", "artifacts", "blockers"],
        "mutating_operations": [],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="noemaforge-current-loop-adapter")
    parser.add_argument("operation", choices=["probe", "snapshot", "artifacts", "blockers"])
    parser.add_argument("--state-root")
    args = parser.parse_args(argv)
    if args.operation == "probe":
        result = probe(args.state_root)
    elif args.operation == "snapshot":
        result = snapshot(args.state_root)
    else:
        root = probe(args.state_root)["selected_state_root"]
        result = artifacts(root) if args.operation == "artifacts" else blockers(root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
