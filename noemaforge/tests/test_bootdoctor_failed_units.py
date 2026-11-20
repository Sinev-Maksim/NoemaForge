"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_bootdoctor_failed_units.py
Zone: release/package
Purpose: Regression test for bootdoctor._detect_failed_units unit-name parsing.
Inputs: Monkeypatched subprocess output.
Outputs: Test assertions only.
Side effects: None.
Tests: pytest noemaforge/tests/test_bootdoctor_failed_units.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import bootdoctor


def test_detect_failed_units_skips_state_marker(monkeypatch):
    # `systemctl --failed --no-legend` (without --plain) prefixes each row
    # with the "●" state-marker glyph as its own leading column; naive
    # split()[0] parsing then picks up the glyph instead of the real unit
    # name and the .service/.timer suffix filter silently drops it,
    # masking real failures (O-002). --plain suppresses the glyph column.
    marker_line = "● noemaforge-llm-backends-manager.service loaded failed failed Drift report"
    plain_line = "noemaforge-llm-backends-manager.service loaded failed failed Drift report"

    def fake_run(cmd, timeout_sec=10):
        assert cmd[:2] == ["systemctl", "--failed"]
        return 0, (plain_line if "--plain" in cmd else marker_line), ""

    monkeypatch.setattr(bootdoctor, "_run", fake_run)
    assert bootdoctor._detect_failed_units() == ["noemaforge-llm-backends-manager.service"]
