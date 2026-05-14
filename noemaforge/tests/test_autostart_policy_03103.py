"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_autostart_policy_03103.py
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
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTOSTART = ROOT / 'tools' / 'prep' / 'noemaforge-autostart-safe.sh'
BOOT_MODE = ROOT / 'tools' / 'prep' / 'noemaforge-boot-mode.sh'
SAFE_START = ROOT / 'tools' / 'ops' / 'noemaforge-op-safe-start.sh'


def run(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged['NOEMAFORGE_ROOT'] = str(ROOT)
    if env:
        merged.update(env)
    return subprocess.run(cmd, text=True, capture_output=True, check=True, env=merged)


def test_gui_autostart_defaults_runtime_only(tmp_path: Path) -> None:
    env = {'NOEMAFORGE_BOOT_MODE_FILE': str(tmp_path / 'boot-mode'), 'NOEMAFORGE_AUTOSTART_PROFILE_DIR': str(tmp_path)}
    (tmp_path / 'boot-mode').write_text('gui\n')
    out = run([str(AUTOSTART), '--mode', 'gui', '--dry-run', '--json'], env=env).stdout
    payload = json.loads(out)
    assert payload['mode'] == 'gui'
    assert payload['profile'] == 'runtime_only'


def test_wogui_autostart_defaults_bootstrap_cpu_llm(tmp_path: Path) -> None:
    env = {'NOEMAFORGE_BOOT_MODE_FILE': str(tmp_path / 'boot-mode'), 'NOEMAFORGE_AUTOSTART_PROFILE_DIR': str(tmp_path)}
    (tmp_path / 'boot-mode').write_text('wogui\n')
    out = run([str(AUTOSTART), '--mode', 'wogui', '--dry-run', '--json'], env=env).stdout
    payload = json.loads(out)
    assert payload['mode'] == 'wogui'
    assert payload['profile'] == 'bootstrap_cpu_llm'


def test_boot_mode_human_status_exposes_profiles(tmp_path: Path) -> None:
    env = {'NOEMAFORGE_BOOT_MODE_FILE': str(tmp_path / 'boot-mode'), 'NOEMAFORGE_AUTOSTART_PROFILE_DIR': str(tmp_path)}
    (tmp_path / 'boot-mode').write_text('manual\n')
    out = run([str(BOOT_MODE), 'show'], env=env).stdout
    assert 'Systemd autostart:' in out
    assert 'Autostart profiles:' in out
    assert 'gui:' in out and 'runtime_only' in out
    assert 'wogui:' in out and 'bootstrap_cpu_llm' in out
    assert 'heavy LLM manual-only' in out or 'manual-only' in out


def test_safe_start_help_documents_profiles() -> None:
    out = run([str(SAFE_START), '--help']).stdout
    assert '--llm-profile=runtime_only' in out
    assert '--llm-profile=bootstrap_cpu_llm' in out
    assert 'heavy' in out.lower() and 'manual' in out.lower()
