"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_control_plane_03112.py
Zone: release/package
Version: 0.31.13.alpha
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = "/usr/bin/python3"


def run_json(args, env=None):
    proc = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_admin_routes_core_operator_intents():
    samples = [
        ("Привет!", "greeting", "dashboard_operator_console"),
        ("доработай код через dev team", "code", "dev_pipeline_member_cells"),
        ("создай музыку", "music", "music_generation"),
        ("эволюция модели", "model_evolution", "model_evolution"),
    ]
    for message, route_id, pipeline_id in samples:
        data = run_json([PYTHON, str(ROOT / "src" / "admin_runtime.py"), "--root", str(ROOT), "route", "--message", message, "--json"])
        assert data["ok"] is True
        assert data["route"]["id"] == route_id
        assert data["route"]["pipeline_id"] == pipeline_id


def test_admin_executes_model_evolution_pipeline(tmp_path):
    data = run_json([
        PYTHON, str(ROOT / "src" / "admin_runtime.py"),
        "--root", str(ROOT), "--state", str(tmp_path / "pipes"), "--evolution-state", str(tmp_path / "evo"),
        "message", "--message", "эволюция модели для dev роли", "--execute", "--allow-degraded", "--json",
    ])
    assert data["ok"] is True
    assert data["executed"] is True
    action_types = [a["type"] for a in data["actions"]]
    assert "pipeline_run" in action_types
    assert "model_evolution" in action_types
