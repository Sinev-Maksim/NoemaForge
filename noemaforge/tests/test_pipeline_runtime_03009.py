"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_runtime_03009.py
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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pipeline_runtime
import persona_runtime


def read_out(capsys):
    return json.loads(capsys.readouterr().out)


def test_pipeline_readiness_gate_repair_and_template_import(tmp_path, capsys):
    root = Path(__file__).resolve().parents[1]
    state = tmp_path / 'pipe'
    pipeline_runtime.main(['--root', str(root), '--state', str(state), 'readiness', '--json'])
    ready = read_out(capsys)
    assert ready['ok'] is True
    assert ready['runtime']['max_active_llms'] == 1
    assert ready['readiness_score'] >= 80

    pipeline_runtime.main(['--root', str(root), '--state', str(state), 'run', 'public_mwp', '--run-id', 'pytest_gate', '--request', 'gate smoke'])
    run = read_out(capsys)
    assert run['run_id'] == 'pytest_gate'

    pipeline_runtime.main(['--root', str(root), '--state', str(state), 'gate', 'pytest_gate', '--json'])
    gate = read_out(capsys)
    assert gate['ok'] is True
    assert gate['ready_to_advance'] is False
    assert gate['checks'][0]['packet_exists'] is True

    pipeline_runtime.main(['--root', str(root), '--state', str(state), 'repair', 'pytest_gate', '--dry-run'])
    repair = read_out(capsys)
    assert repair['ok'] is True
    assert repair['run_count'] == 1

    template = tmp_path / 'n8n.json'
    template.write_text('{"nodes":[{"name":"Webhook"},{"name":"Draft"}],"connections":{}}', encoding='utf-8')
    pipeline_runtime.main(['--root', str(root), '--state', str(state), 'template-import', str(template), '--family', 'n8n', '--pipeline-id', 'pytest_import'])
    imported = read_out(capsys)
    assert imported['ok'] is True
    assert imported['pipeline']['llm_policy']['max_active_llms'] == 1
    assert 'Webhook' in imported['pipeline']['stages']


def test_persona_lineage_export_and_active_evolve(tmp_path, capsys):
    root = Path(__file__).resolve().parents[1]
    state = tmp_path / 'persona'
    persona_runtime.main(['--root', str(root), '--state', str(state), 'activate', 'Гармр', '--reason', 'pytest'])
    active = read_out(capsys)
    assert active['ok'] is True
    assert active['active']['codename'] == 'Гармр'

    persona_runtime.main(['--root', str(root), '--state', str(state), 'evolve', 'Гармр', '--reason', 'pytest_evolve'])
    evolved = read_out(capsys)
    assert evolved['generation'] == 1
    assert Path(evolved['portrait']).exists()

    persona_runtime.main(['--root', str(root), '--state', str(state), 'lineage', 'Гармр', '--json'])
    lineage = read_out(capsys)
    assert lineage['active']['generation'] == 1
    assert len(lineage['events']) >= 2

    out = tmp_path / 'persona_export.json'
    persona_runtime.main(['--root', str(root), '--state', str(state), 'export', '--out', str(out)])
    exported = read_out(capsys)
    assert exported['ok'] is True
    assert out.exists()
