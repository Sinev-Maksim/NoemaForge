"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_dev_team_and_evolution_03112.py
Zone: release/package
Version: 0.32.1
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
PYTHON = sys.executable


def run_json(args):
    proc = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_model_evolution_writes_measured_artifacts(tmp_path):
    data = run_json([
        PYTHON, str(ROOT / "src" / "model_evolution_runtime.py"),
        "--root", str(ROOT), "--state", str(tmp_path / "evo"), "run", "--request", "improve dev role", "--json",
    ])
    assert data["ok"] is True
    assert data["status"] == "conducted_candidate_ready"
    names = {Path(path).name for path in data["artifacts"].values()}
    assert {"baseline_snapshot.json", "mutation_plan.json", "scorecard.json", "rollback_plan.json", "candidate_profile.json"} <= names
    assert any("--keep-display" in step for step in data["next"])


def test_dev_team_replace_can_apply_direct_patch(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    source = project / "app.py"
    source.write_text("def add(a,b):\n    return a+b\n", encoding="utf-8")
    data = run_json([
        PYTHON, str(ROOT / "src" / "dev_team_runtime.py"),
        "--root", str(ROOT), "--state", str(tmp_path / "dev"),
        "replace", "--project", str(project), "--path", "app.py", "--old", "return a+b", "--new", "return a + b", "--apply", "--json",
    ])
    assert data["ok"] is True
    assert data["applied"] is True
    assert "return a + b" in source.read_text(encoding="utf-8")
