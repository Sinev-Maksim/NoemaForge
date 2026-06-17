"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_gui_evolution_03112.py
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
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2]
ROOT = PACKAGE / "noemaforge"
# Use the interpreter running the tests so the suite is cross-platform; allow an
# explicit override. The previous default "/usr/bin/python3" failed on Windows.
PYTHON = os.environ.get("NOEMAFORGE_TEST_PYTHON") or sys.executable


def run_json(cmd, *, env=None, timeout=60):
    proc = subprocess.run(cmd, cwd=str(PACKAGE), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return json.loads(proc.stdout)


def env_with_root(extra=None):
    env = os.environ.copy()
    env["NOEMAFORGE_ROOT"] = str(ROOT)
    if extra:
        env.update({k: str(v) for k, v in extra.items()})
    return env


def test_admin_typo_greeting_routes_inside_gui_ready():
    doc = run_json([PYTHON, str(ROOT / "src" / "admin_runtime.py"), "route", "--message", "Првиет!", "--json"], env=env_with_root())
    assert doc["ok"] is True
    assert doc["version"] == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert doc["route"]["id"] == "greeting"
    assert doc["route"]["pipeline_id"] == "dashboard_operator_console"


def test_admin_launches_music_pipeline_and_prepare_plan(tmp_path):
    env = env_with_root({"NOEMAFORGE_MULTIMODAL_STATE": tmp_path / "multimodal"})
    doc = run_json([
        PYTHON, str(ROOT / "src" / "admin_runtime.py"),
        "--root", str(ROOT),
        "--state", str(tmp_path / "pipelines"),
        "--evolution-state", str(tmp_path / "evolution"),
        "message", "--message", "создай музыку для запуска", "--execute", "--prepare-media", "--allow-degraded", "--json",
    ], env=env)
    assert doc["ok"] is True
    assert doc["route"]["pipeline_id"] == "music_generation"
    assert doc["actions"][0]["result"]["ok"] is True
    assert (tmp_path / "multimodal" / "music_generate-plan.json").exists()


def test_admin_can_modify_pipeline_overlay(tmp_path):
    tmp_root = tmp_path / "root"
    (tmp_root / "configs").mkdir(parents=True)
    (tmp_root / "configs" / "pipelines.json").write_text((ROOT / "configs" / "pipelines.json").read_text(), encoding="utf-8")
    (tmp_root / "configs" / "pipeline-teams.json").write_text((ROOT / "configs" / "pipeline-teams.json").read_text(), encoding="utf-8")
    doc = run_json([
        PYTHON, str(ROOT / "src" / "admin_runtime.py"),
        "--root", str(tmp_root),
        "modify-pipeline", "admin_test_pipeline", "--create", "--add-stage", "dev_review", "--apply", "--json",
    ], env=env_with_root())
    assert doc["ok"] is True
    overlay = json.loads((tmp_root / "configs" / "pipelines.local.json").read_text())
    assert "admin_test_pipeline" in overlay
    assert "dev_review" in overlay["admin_test_pipeline"]["stages"]


def test_dev_team_direct_write_and_replace(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    state = tmp_path / "dev-state"
    doc = run_json([
        PYTHON, str(ROOT / "src" / "dev_team_runtime.py"),
        "--state", str(state),
        "write-file", "--project", str(project), "--path", "hello.py", "--content", "print('old')\n", "--apply", "--json",
    ], env=env_with_root())
    assert doc["ok"] is True and doc["applied"] is True
    doc = run_json([
        PYTHON, str(ROOT / "src" / "dev_team_runtime.py"),
        "--state", str(state),
        "replace", "--project", str(project), "--path", "hello.py", "--old", "old", "--new", "new", "--apply", "--json",
    ], env=env_with_root())
    assert doc["ok"] is True and doc["applied"] is True
    assert "new" in (project / "hello.py").read_text()


def test_model_evolution_conducts_cycle(tmp_path):
    doc = run_json([
        PYTHON, str(ROOT / "src" / "model_evolution_runtime.py"),
        "--root", str(ROOT),
        "--state", str(tmp_path / "evolution"),
        "--pipeline-state", str(tmp_path / "pipelines"),
        "run", "--request", "эволюция модели для dev роли", "--json",
    ], env=env_with_root())
    assert doc["ok"] is True
    assert doc["conducted"] is True
    assert doc["status"] == "conducted_candidate_ready"
    for path in doc["artifacts"].values():
        assert Path(path).exists()


def test_admin_gui_api_surface_is_packaged():
    proc = subprocess.run([PYTHON, "-m", "py_compile", str(ROOT / "src" / "admin_gui_server.py")], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    assert proc.returncode == 0, proc.stderr
    app_js = (ROOT / "templates" / "pipeline-dashboard" / "app.js").read_text(encoding="utf-8")
    assert "/api/admin/message" in app_js
    assert "/api/shutdown" in app_js
    launcher = (ROOT / "tools" / "prep" / "noemaforge-dashboard.sh").read_text(encoding="utf-8")
    assert "admin_gui_server.py" in launcher
