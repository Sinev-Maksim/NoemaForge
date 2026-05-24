"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_team_member_03101.py
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'bin' / 'noemaforge'


def run_cli(args, env=None):
    e = os.environ.copy()
    e['NOEMAFORGE_ROOT'] = str(ROOT)
    if env:
        e.update(env)
    return subprocess.run([str(CLI)] + args, text=True, capture_output=True, env=e, check=False)


def test_member_policy_validates():
    cp = run_cli(['member', 'validate'])
    assert cp.returncode == 0, cp.stderr
    doc = json.loads(cp.stdout)
    assert doc['ok'] is True
    assert doc['member_count'] >= 3


def test_member_team_excludes_producer():
    cp = run_cli(['member', 'team', '--member', 'qa', '--producer', 'qwen25-coder-14b', '--json'])
    assert cp.returncode == 0, cp.stderr
    doc = json.loads(cp.stdout)
    mids = [m['id'] for m in doc['models']]
    assert len(mids) >= 2
    assert 'qwen25-coder-14b' not in mids
    assert doc['effective_execution'] == 'sequential_by_single_llm_lease'


def test_member_analyser_writes_diagrams_and_handoff(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'app.py').write_text('''
class A:
    def twice(self, x):
        return helper(x) + helper(x)

def helper(x):
    return x + 1
''')
    state = tmp_path / 'state'
    cp = run_cli(['member', 'run', '--member', 'code_analyser_visualiser', '--project', str(project), '--state', str(state), '--run-id', 'pytest_member_analyser', '--json'])
    assert cp.returncode == 0, cp.stderr
    doc = json.loads(cp.stdout)
    run_dir = Path(doc['run_dir'])
    assert (run_dir / 'architecture_overview.mmd').exists()
    assert (run_dir / 'call_graph.mmd').exists()
    assert (run_dir / 'bottleneck_report.json').exists()
    assert (run_dir / 'next_participant_handoff_context.json.sha256').exists()
    bottleneck = json.loads((run_dir / 'bottleneck_report.json').read_text())
    assert any(x.get('callee') == 'helper' and x.get('call_count', 0) >= 2 for x in bottleneck.get('repeated_calls', []))


def test_pipeline_member_delegate_registers_artifact(tmp_path):
    env = {'NOEMAFORGE_PIPELINE_STATE': str(tmp_path / 'pipes')}
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'app.py').write_text('def add(a,b):\n    return a+b\n')
    cp = run_cli(['pipeline', 'run', 'dev_pipeline_member_cells', '--task-id', 'pytest', '--request', 'pytest member cells'], env=env)
    assert cp.returncode == 0, cp.stderr
    run_id = json.loads(cp.stdout)['run_id']
    cp = run_cli(['pipeline', 'member', 'run', run_id, '--stage', 'code_analyser_visualiser', '--member', 'code_analyser_visualiser', '--project', str(project), '--json'], env=env)
    assert cp.returncode == 0, cp.stderr
    doc = json.loads(cp.stdout)
    assert doc['pipeline_run_id'] == run_id
    gate = run_cli(['pipeline', 'gate', run_id, '--stage', 'code_analyser_visualiser', '--json'], env=env)
    assert gate.returncode == 0, gate.stderr
    g = json.loads(gate.stdout)
    # The member handoff is registered as a pipeline artifact for the stage.
    current = [x for x in g['checks'] if x['stage'] == 'code_analyser_visualiser'][0]
    assert current['artifact_count'] >= 1
