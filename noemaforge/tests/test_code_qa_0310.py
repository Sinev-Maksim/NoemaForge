"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_code_qa_0310.py
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
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'bin' / 'noemaforge'


def run_cli(args, env=None):
    e = os.environ.copy()
    e['NOEMAFORGE_ROOT'] = str(ROOT)
    if env:
        e.update(env)
    return subprocess.run([str(CLI)] + args, text=True, capture_output=True, env=e, check=False)


def test_code_qa_team_excludes_producer():
    cp = run_cli(['qa', 'code', 'team', '--producer', 'qwen25-coder-14b', '--json'])
    assert cp.returncode == 0, cp.stderr
    doc = json.loads(cp.stdout)
    reviewers = [r['id'] for r in doc['reviewers']]
    assert len(reviewers) == 2
    assert 'qwen25-coder-14b' not in reviewers
    assert doc['effective_execution'] == 'sequential_enforced_by_single_llm'


def test_code_qa_run_writes_handoff(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'app.py').write_text('def add(a,b):\n    return a+b\n')
    state = tmp_path / 'state'
    cp = run_cli(['qa', 'code', 'run', '--project', str(project), '--state', str(state), '--run-id', 'pytest_codeqa', '--producer', 'qwen25-coder-14b', '--json'])
    assert cp.returncode == 0, cp.stderr
    doc = json.loads(cp.stdout)
    assert doc['ok'] is True
    run_dir = Path(doc['run_dir'])
    assert (run_dir / 'consensus.json').exists()
    assert (run_dir / 'next_participant_handoff_context.md').exists()
    assert (run_dir / 'next_participant_handoff_context.json').exists()
