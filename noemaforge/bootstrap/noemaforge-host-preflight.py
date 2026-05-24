#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/bootstrap/noemaforge-host-preflight.py
Zone: release/package
Version: 0.31.13.alpha-patched1
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

# === NoemaForge Autodoc File Header ===
# File: bootstrap/noemaforge-host-preflight.py
# Purpose: Validate seed layout and host prerequisites before or during NoemaForge bootstrap on Debian/Trixie-class systems.
# Invoked by / imported from:
#   - bootstrap/noemaforge-bootstrap.sh
#   - tests/test_host_preflight.py
# Public API / entry functions:
#   - collect_report
#   - main
# Inputs:
#   - --seed, --out, --offline-apt
# Output formats / side effects:
#   - JSON reports only.
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===


import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict


def _check_exe(name: str) -> Dict[str, Any]:
    path = shutil.which(name)
    return {'name': name, 'present': bool(path), 'path': path or ''}


def collect_report(seed: str, offline_apt: str = '') -> Dict[str, Any]:
    seed_path = Path(seed).resolve()
    repo = offline_apt or str(seed_path / 'offline-apt' / 'aptrepo')
    report = {
        'ok': True,
        'seed_root': str(seed_path),
        'checks': {
            'seed_exists': seed_path.is_dir(),
            'gateway_source': (seed_path / 'src' / 'noemaforge-llm-gateway.go').is_file(),
            'gateway_binary': (seed_path / 'bin' / 'noemaforge-llm-gateway').is_file(),
            'llama_server_binary': (seed_path / 'bin' / 'llama-server').is_file(),
            'offline_apt_repo': os.path.isdir(repo),
            'offline_apt_packages': os.path.exists(os.path.join(repo, 'Packages')) or os.path.exists(os.path.join(repo, 'Packages.gz')),
            'voice_policy': (seed_path / 'configs' / 'voice-backends-policy.yaml').is_file(),
            'tts_policy': (seed_path / 'configs' / 'tts-backends-policy.yaml').is_file(),
            'bridge_policy': (seed_path / 'configs' / 'discord-bridge-policy.yaml').is_file(),
        },
        'executables': {
            'python3': _check_exe('python3'),
            'go': _check_exe('go'),
            'ffmpeg': _check_exe('ffmpeg'),
            'pactl': _check_exe('pactl'),
            'modprobe': _check_exe('modprobe'),
        },
        'notes': [],
    }
    if not report['checks']['seed_exists']:
        report['ok'] = False
        report['notes'].append('Seed root does not exist.')
    if report['checks']['gateway_source'] and not report['checks']['gateway_binary']:
        report['notes'].append('Gateway source is present; bootstrap can auto-build the binary if Go is available.')
    if not report['checks']['offline_apt_repo']:
        report['notes'].append('Offline APT repo is optional but recommended for a reproducible offline-first install.')
    if not report['checks']['llama_server_binary']:
        report['notes'].append('llama-server is still an external runtime dependency and must be supplied on the host or seed.')
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--offline-apt', default='')
    args = ap.parse_args()
    rep = collect_report(seed=args.seed, offline_apt=args.offline_apt)
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(args.out)
    return 0 if rep.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
