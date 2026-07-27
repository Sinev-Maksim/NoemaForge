"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_noemaforge_status_shape.py
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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import noemaforge_status


def test_noemaforge_status_shape(tmp_path):
    args = type('Args', (), {'share': str(tmp_path / 'missing-share'), 'dataset': str(tmp_path / 'missing-dataset'), 'json': True, 'strict': False})()
    doc = noemaforge_status.collect(args)
    assert doc['runtime_invariant']['runtime_desired_count'] == 1
    assert doc['runtime_invariant']['mode'] == 'switchable'
    assert 'checks' in doc and doc['checks']
    assert 'next_actions' in doc and doc['next_actions']
    assert doc['health'] in {'ready', 'degraded', 'blocked'}


def test_noemaforge_status_failed_units_skips_state_marker(tmp_path, monkeypatch):
    # `systemctl --failed --no-legend` (without --plain) prefixes each row with
    # the "●" state-marker glyph as its own leading column, so unqualified
    # split()[0] parsing picks up the glyph instead of the real unit name
    # (O-002). --plain suppresses the glyph column.
    # Real `systemctl --failed` output; --plain suppresses the leading glyph
    # column that `--no-legend` alone leaves in place.
    marker_line = "● noemaforge-llm-backends-manager.service loaded failed failed Drift report"
    plain_line = "noemaforge-llm-backends-manager.service loaded failed failed Drift report"

    def fake_run_cmd(cmd, timeout=2.0):
        if cmd[:2] == ["systemctl", "--failed"]:
            return 0, (plain_line if "--plain" in cmd else marker_line), ""
        return 1, "", "unused"

    monkeypatch.setattr(noemaforge_status, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(noemaforge_status, "systemctl_available", lambda: True)
    monkeypatch.setattr(noemaforge_status, "systemctl_is_active", lambda unit: "inactive")
    monkeypatch.setattr(noemaforge_status, "systemctl_is_enabled", lambda unit: "disabled")
    monkeypatch.setattr(noemaforge_status, "findmnt", lambda path: False)

    args = type('Args', (), {'share': str(tmp_path / 'missing-share'), 'dataset': str(tmp_path / 'missing-dataset'), 'json': True, 'strict': False})()
    doc = noemaforge_status.collect(args)
    assert doc['failed_units'] == ["noemaforge-llm-backends-manager.service"]
