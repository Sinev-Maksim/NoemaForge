#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_current_loop_readonly_adapter.py
Zone: tests
Version: 0.33.0
Created: 2026-07-18
Modified: 2026-07-18
Purpose: Validate bounded read-only import of the current prod-ready loop state.
Inputs: Temporary current-loop state layouts.
Outputs: pytest assertions only.
Side effects: Temporary files only.
Tests: pytest -q noemaforge/tests/test_current_loop_readonly_adapter.py
Notes: The adapter exposes no mutating operations.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from evolution_adapters import current_loop  # noqa: E402


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _json(path: Path, payload: dict) -> None:
    _write(path, json.dumps(payload, indent=2))


def _state(root: Path) -> None:
    _write(root / "status.md", """# status

- timestamp: 2026-07-18T10:00:00Z
- cycle: 7
- stage: scheduler-reconcile
- active_agent: codex
- branch: release/0.33.0-dev
- head: abcdef1
- issue_gate: pass
- security_gate: blocked
- issue_manual_pending: 1
""")
    _json(root / "coordinator-lock-v51.json", {
        "schema": "nf.coordinator-lock.v51/v1",
        "pid": 123,
        "started_at": "2026-07-18T09:00:00Z",
        "version": "4.11",
        "repo": "Sinev-Maksim/NoemaForge",
        "base": "release/0.33.0-dev",
    })
    _json(root / "work-items-v51/issue-42.json", {
        "schema": "nf.work-item.v51/issue/v1",
        "issue": 42,
        "phase": "pr-open",
        "branch": "fix/42",
        "head": "a" * 40,
        "last_mutator": "claude",
        "pr": 99,
        "reason": "",
    })
    _json(root / "scheduler/pr-100.json", {
        "schema": "nf.scheduler.v52/pr-state/v1",
        "pr": 100,
        "last_seen_head": "b" * 40,
        "last_mutated_head": "b" * 40,
        "last_mutator": "codex",
        "history_trusted": True,
        "broad_review_done": True,
        "reviewed_head": "b" * 40,
        "reviewed_by": "claude",
    })
    _json(root / "review-threads-v46/parked-prs/pr-101.json", {
        "pr": 101,
        "head": "c" * 40,
        "reason": "provider-limit",
    })
    _write(root / "issues-v39/manual-pending/issue-42.marker", "manual")
    _write(root / "codex-write-blocked-until.txt", "2026-07-18T12:00:00Z")
    _write(root / "ledger.md", "ledger")


def _validator(name: str) -> jsonschema.Draft202012Validator:
    schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


def test_explicit_root_wins_and_layout_ambiguity_is_reported(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    v46 = tmp_path / ".local/share/noemaforge-agent-runs/token-aware-0330-v46"
    v3 = tmp_path / ".local/share/noemaforge-agent-runs/token-aware-0330-v3"
    _state(explicit)
    _state(v46)
    _state(v3)
    result = current_loop.probe(explicit, environ={"HOME": str(tmp_path)}, home=tmp_path)
    assert result["selected_state_root"] == str(explicit.absolute())
    unscoped = current_loop.probe(environ={"HOME": str(tmp_path)}, home=tmp_path)
    assert "v46_wrapper_and_v3_base_state_layout_both_present" in unscoped["warnings"]
    assert unscoped["mutating_operations"] == []


def test_snapshot_produces_valid_evolution_contracts_and_does_not_invent_head(tmp_path: Path) -> None:
    root = tmp_path / "state"
    _state(root)
    result = current_loop.snapshot(root, captured_at="2026-07-18T10:01:00Z")
    _validator("evolution_run.schema.json").validate(result["evolution_run"])
    for item in result["work_items"]:
        _validator("evolution_work_item.schema.json").validate(item)
    assert result["evolution_run"]["exact_base_head"] is None
    assert "status_head_is_not_full_sha" in result["warnings"]
    assert {item["work_item_id"] for item in result["work_items"]} == {
        "current-loop:issue:42",
        "current-loop:pr:100",
    }
    assert result["mode"] == "read_only"
    assert result["mutating_operations"] == []


def test_blockers_are_stable_and_include_gates_markers_parked_and_manual(tmp_path: Path) -> None:
    root = tmp_path / "state"
    _state(root)
    first = current_loop.blockers(root)
    second = current_loop.blockers(root)
    assert first == second
    kinds = {item["kind"] for item in first["blockers"]}
    assert {
        "gate",
        "manual_or_target_pending",
        "provider_write_block",
        "parked_review",
        "manual_evidence_pending",
    } <= kinds
    assert all(len(item["fingerprint"]) == 64 for item in first["blockers"])


def test_artifacts_are_hash_stable_and_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "state"
    _state(root)
    first = current_loop.artifacts(root)
    second = current_loop.artifacts(root)
    assert first == second
    assert first["artifacts"]
    assert all(item["artifact_id"] == "sha256:" + item["sha256"] for item in first["artifacts"])


def test_symlink_escape_and_oversized_file_are_not_read(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir()
    outside = tmp_path / "outside.log"
    outside.write_text("secret", encoding="utf-8")
    (root / "logs").mkdir()
    os.symlink(outside, root / "logs/escape.log")
    (root / "logs/large.log").write_bytes(b"x" * 32)
    escaped, escape_error = current_loop._contained_file(root, "logs/escape.log", 16)
    large, large_error = current_loop._contained_file(root, "logs/large.log", 16)
    assert escaped is None and escape_error == "path_escape"
    assert large is None and large_error == "oversized"


def test_malformed_json_degrades_to_warning(tmp_path: Path) -> None:
    root = tmp_path / "state"
    _write(root / "status.md", "- timestamp: 2026-07-18T10:00:00Z\n")
    _write(root / "coordinator-lock-v51.json", "{not-json")
    _json(root / "work-items-v51/issue-bad.json", {
        "issue": "not-a-number",
        "phase": "running",
    })
    result = current_loop.snapshot(root, captured_at="2026-07-18T10:01:00Z")
    assert "coordinator-lock-v51.json:malformed_json" in result["warnings"]
    assert result["evolution_run"]["status"] == "paused"


def test_legacy_scheduler_state_is_imported(tmp_path: Path) -> None:
    root = tmp_path / "state"
    _write(root / "status.md", "- timestamp: 2026-07-18T10:00:00Z\n")
    _json(root / "scheduler-v51/pr-77.json", {
        "pr": 77,
        "last_seen_head": "d" * 40,
        "history_trusted": False,
        "history_source": "legacy-unclassified",
    })
    result = current_loop.snapshot(root, captured_at="2026-07-18T10:01:00Z")
    assert [item["work_item_id"] for item in result["work_items"]] == ["current-loop:pr:77"]
    assert result["work_items"][0]["status"] == "blocked"


def test_adapter_public_surface_has_no_mutating_operation() -> None:
    prohibited = {"start", "stop", "pause", "resume", "cancel", "apply", "write", "merge", "push"}
    assert prohibited.isdisjoint(set(current_loop.probe(environ={}, home="/nonexistent")["operations"]))
