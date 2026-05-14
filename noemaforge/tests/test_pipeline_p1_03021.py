#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_p1_03021.py
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
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'bin' / 'noemaforge'
sys.path.insert(0, str(ROOT / 'src'))
import pipeline_runtime


def run_cmd(*args: str, state: Path) -> dict:
    env = os.environ.copy()
    env['NOEMAFORGE_ROOT'] = str(ROOT)
    env['NOEMAFORGE_PIPELINE_STATE'] = str(state)
    out = subprocess.check_output([str(CLI), *args], text=True, env=env)
    return json.loads(out)


def test_p1_schema_event_log_lease_and_executor(tmp_path: Path) -> None:
    state = tmp_path / 'state'
    created = run_cmd('pipeline', 'run', 'public_mwp', '--task-id', 'p1', '--request', 'p1 smoke', state=state)
    run_id = created['run_id']
    schema = run_cmd('schema', 'validate', '--run-id', run_id, state=state)
    assert schema['ok'] is True
    assert schema['checked']['typed_context_sidecars'] >= 1
    events = run_cmd('pipeline', 'event-log', '--run-id', run_id, '--json', state=state)
    assert events['count'] >= 1
    assert events['items'][0]['event_type'] == 'pipeline_created'
    lease = run_cmd('pipeline', 'lease', 'acquire', '--owner', 'pytest', '--task-id', run_id, '--ttl-seconds', '60', state=state)
    assert lease['ok'] is True
    busy = subprocess.run([str(CLI), 'pipeline', 'lease', 'acquire', '--owner', 'other'], text=True, stdout=subprocess.PIPE, env={**os.environ, 'NOEMAFORGE_ROOT': str(ROOT), 'NOEMAFORGE_PIPELINE_STATE': str(state)})
    assert busy.returncode == 1
    status = run_cmd('pipeline', 'lease', 'status', state=state)
    assert status['active']['owner'] == 'pytest'
    step = run_cmd('pipeline', 'executor-step', run_id, state=state)
    assert step['ready'] is False
    assert step['stage'] == 'orient'


def test_prometheus_metrics_and_task_contexts_are_canonical(tmp_path: Path) -> None:
    state = tmp_path / 'state'
    created = run_cmd('pipeline', 'run', 'public_mwp', '--task-id', 'p1metrics', '--request', 'metrics', state=state)
    run_id = created['run_id']
    conn = pipeline_runtime.db_connect(state)
    assert conn.execute('SELECT count(*) FROM task_contexts WHERE run_id=?', (run_id,)).fetchone()[0] >= 1
    assert conn.execute('SELECT count(*) FROM stage_states WHERE run_id=?', (run_id,)).fetchone()[0] >= 1
    env = os.environ.copy(); env['NOEMAFORGE_ROOT'] = str(ROOT); env['NOEMAFORGE_PIPELINE_STATE'] = str(state)
    prom = subprocess.check_output([str(CLI), 'pipeline', 'metrics', '--format', 'prometheus'], text=True, env=env)
    assert 'noemaforge_pipeline_runs_total' in prom
    assert 'noemaforge_llm_active_count' in prom


def test_toolproxy_token_smoke_without_live_service(tmp_path: Path) -> None:
    tokens = tmp_path / 'tokens'
    env = os.environ.copy(); env['NOEMAFORGE_ROOT'] = str(ROOT)
    out = subprocess.check_output([str(CLI), 'toolproxy', 'smoke', '--tokens-dir', str(tokens)], text=True, env=env)
    doc = json.loads(out)
    assert doc['ok'] is True
    assert doc['verify']['ok'] is True
    listed = subprocess.check_output([str(CLI), 'toolproxy', 'token', 'list', '--tokens-dir', str(tokens)], text=True, env=env)
    assert json.loads(listed)['count'] >= 1
