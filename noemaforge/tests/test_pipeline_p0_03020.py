"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_p0_03020.py
Zone: release/package
Version: 0.31.13.alpha
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Manage NoemaForge pipeline catalog, runs, gates, artifacts and state.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pipeline_runtime


def test_snapshot_has_no_dead_branch_placeholder() -> None:
    text = (ROOT / "src" / "pipeline_runtime.py").read_text(encoding="utf-8", errors="replace")
    assert "if False" not in text


def test_context_packet_writes_json_sidecar(tmp_path: Path) -> None:
    pipeline = {"id": "p0_test", "permission_mode": "plan_only", "deliverables": ["note"]}
    team = {"coordinator": "architect", "roles": ["tester"]}
    packet = pipeline_runtime.write_stage_packet(tmp_path, pipeline, team, "task", "project", "stage", "request", None)
    sidecar = packet.with_suffix(".json")
    assert packet.exists()
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["llm_policy"]["max_active_llms"] == 1
    assert data["stage"] == "stage"
    assert sidecar.with_suffix(".json.sha256").exists()


def test_degraded_readonly_blocks_mutating_pipeline_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    staffing = tmp_path / "firstboot-staffing-summary.json"
    staffing.write_text(json.dumps({"staffing_state": "degraded_selected"}), encoding="utf-8")
    monkeypatch.setenv("NOEMAFORGE_FIRSTBOOT_STAFFING_SUMMARY", str(staffing))
    monkeypatch.delenv("NOEMAFORGE_ALLOW_DEGRADED_MUTATION", raising=False)
    with pytest.raises(SystemExit) as exc:
        pipeline_runtime.main(["--root", str(ROOT), "--state", str(tmp_path / "state"), "run", "public_mwp", "--request", "blocked"])
    assert exc.value.code == 3


def test_degraded_readonly_override_allows_pipeline_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    staffing = tmp_path / "firstboot-staffing-summary.json"
    staffing.write_text(json.dumps({"staffing_state": "degraded_selected"}), encoding="utf-8")
    monkeypatch.setenv("NOEMAFORGE_FIRSTBOOT_STAFFING_SUMMARY", str(staffing))
    rc = pipeline_runtime.main(["--root", str(ROOT), "--state", str(tmp_path / "state"), "run", "public_mwp", "--request", "allowed", "--allow-degraded"])
    assert rc == 0
