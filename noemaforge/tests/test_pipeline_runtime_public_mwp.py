"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_runtime_public_mwp.py
Zone: release/package
Version: 0.31.13.alpha-patched1
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
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pipeline_runtime


def test_public_mwp_pipeline_lifecycle(tmp_path, capsys, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    state = tmp_path / 'state'
    pipeline_runtime.main(['--root', str(root), '--state', str(state), 'validate'])
    validate = json.loads(capsys.readouterr().out)
    assert validate['ok'] is True
    assert validate['pipeline_count'] >= 5

    pipeline_runtime.main(['--root', str(root), '--state', str(state), 'run', 'public_mwp', '--task-id', 'pytest', '--request', 'smoke'])
    created = json.loads(capsys.readouterr().out)
    run_id = created['run_id']
    run_dir = Path(created['run_dir'])
    assert (run_dir / 'project_context_snapshot.md').exists()
    assert (run_dir / 'context_packets').exists()
    assert (run_dir / 'outputs' / 'orient.md').exists()

    pipeline_runtime.main(['--root', str(root), '--state', str(state), 'approve', run_id])
    approved = json.loads(capsys.readouterr().out)
    assert approved['status'] == 'approved'

    pipeline_runtime.main(['--root', str(root), '--state', str(state), 'advance', run_id, '--stage', 'status_check', '--status', 'in_progress'])
    advanced = json.loads(capsys.readouterr().out)
    assert advanced['stage'] == 'status_check'

    pipeline_runtime.main(['--root', str(root), '--state', str(state), 'doctor', run_id])
    doctor = json.loads(capsys.readouterr().out)
    assert doctor['ok'] is True

    out = tmp_path / 'dashboard-state.json'
    pipeline_runtime.main(['--root', str(root), '--state', str(state), 'dashboard-state', '--out', str(out)])
    capsys.readouterr()
    assert out.exists()
    dashboard = json.loads(out.read_text())
    assert dashboard['runtime']['max_active_llms'] == 1
    assert dashboard['current']['pipeline_id'] == 'public_mwp'

    archive = tmp_path / 'run.tar.gz'
    pipeline_runtime.main(['--root', str(root), '--state', str(state), 'export', run_id, '--out', str(archive)])
    exported = json.loads(capsys.readouterr().out)
    assert exported['ok'] is True
    assert archive.exists()
    assert archive.with_suffix(archive.suffix + '.sha256').exists()
