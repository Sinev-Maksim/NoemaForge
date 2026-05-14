#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_runtime_03019.py
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
import json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'bin' / 'noemaforge'

def run_cmd(*args: str, state: Path, persona_state: Path | None = None) -> dict:
    env = os.environ.copy()
    env['NOEMAFORGE_ROOT'] = str(ROOT)
    env['NOEMAFORGE_PIPELINE_STATE'] = str(state)
    if persona_state:
        env['NOEMAFORGE_PERSONA_STATE'] = str(persona_state)
    out = subprocess.check_output([str(CLI), *args], text=True, env=env)
    return json.loads(out)

def test_context_lint_compact_queue_metrics(tmp_path: Path) -> None:
    state = tmp_path / 'state'
    created = run_cmd('pipeline', 'run', 'public_mwp', '--task-id', 'pytest03019', '--request', 'pytest', state=state)
    run_id = created['run_id']
    linted = run_cmd('pipeline', 'context-lint', run_id, state=state)
    assert linted['ok'] is True
    assert linted['stage_count'] >= 1
    compacted = run_cmd('pipeline', 'compact', run_id, '--register', state=state)
    assert compacted['ok'] is True
    assert Path(compacted['out']).exists()
    queued = run_cmd('pipeline', 'queue', '--json', state=state)
    assert queued['items'][0]['run_id'] == run_id
    metrics = run_cmd('pipeline', 'metrics', state=state)
    assert metrics['flow.wip'] >= 1
    assert metrics['runtime']['max_active_llms'] == 1

def test_template_append_requires_approval_and_can_write_local_catalog(tmp_path: Path) -> None:
    state = tmp_path / 'state'
    src = tmp_path / 'sample.json'
    draft = tmp_path / 'draft.json'
    out = tmp_path / 'pipelines.local.json'
    src.write_text('{"name":"T","nodes":[{"name":"Webhook"}],"connections":{}}', encoding='utf-8')
    env = os.environ.copy(); env['NOEMAFORGE_ROOT'] = str(ROOT); env['NOEMAFORGE_PIPELINE_STATE'] = str(state)
    subprocess.check_call([str(CLI), 'pipeline', 'template-import', str(src), '--pipeline-id', 'pytest_import', '--out', str(draft)], env=env)
    denied = subprocess.run([str(CLI), 'pipeline', 'template-append', str(draft), '--out', str(out)], env=env, text=True, stdout=subprocess.PIPE)
    assert denied.returncode == 1
    appended = subprocess.check_output([str(CLI), 'pipeline', 'template-append', str(draft), '--approve', '--out', str(out)], env=env, text=True)
    doc = json.loads(appended)
    assert doc['ok'] is True
    assert 'pytest_import' in json.loads(out.read_text(encoding='utf-8'))

def test_persona_doctor_and_dashboard_state(tmp_path: Path) -> None:
    state = tmp_path / 'state'
    persona_state = tmp_path / 'personas'
    doc = run_cmd('persona', 'doctor', state=state, persona_state=persona_state)
    assert doc['ok'] is True
    assert doc['invariant']['max_active_llms'] == 1
    dash = tmp_path / 'dashboard.json'
    env = os.environ.copy(); env['NOEMAFORGE_ROOT'] = str(ROOT); env['NOEMAFORGE_PIPELINE_STATE'] = str(state); env['NOEMAFORGE_PERSONA_STATE'] = str(persona_state)
    subprocess.check_call([str(CLI), 'dashboard', 'state', '--out', str(dash)], env=env)
    data = json.loads(dash.read_text(encoding='utf-8'))
    assert data['runtime']['max_active_llms'] == 1
    assert 'metrics' in data
