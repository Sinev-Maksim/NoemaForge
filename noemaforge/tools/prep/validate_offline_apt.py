#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/prep/validate_offline_apt.py
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
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: tools/prep/validate_offline_apt.py
# Purpose: Validate a NoemaForge offline APT repository and optional driver vault before install time.
# Invoked by / imported from:
#   - bootstrap/noemaforge-bootstrap.sh
#   - tests/test_validate_offline_apt.py
# Public API / entry functions:
#   - validate_repo
#   - main
# Inputs:
#   - --repo, --driver-vault, --out
# Output formats / side effects:
#   - JSON validation reports.
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===


import argparse
import gzip
import json
import os
from pathlib import Path
from typing import Any, Dict


def validate_repo(repo: str, driver_vault: str = '') -> Dict[str, Any]:
    rp = Path(repo).resolve()
    packages = rp / 'Packages'
    packages_gz = rp / 'Packages.gz'
    debs = sorted(rp.glob('*.deb'))
    report: Dict[str, Any] = {
        'ok': True,
        'repo': str(rp),
        'exists': rp.is_dir(),
        'packages_index': '',
        'deb_count': len(debs),
        'sample_debs': [p.name for p in debs[:10]],
        'driver_vault': driver_vault,
        'driver_deb_count': 0,
        'notes': [],
    }
    if not rp.is_dir():
        report['ok'] = False
        report['notes'].append('Offline repo directory is missing.')
        return report
    if packages.exists():
        report['packages_index'] = str(packages)
    elif packages_gz.exists():
        report['packages_index'] = str(packages_gz)
        try:
            gzip.open(packages_gz, 'rt', encoding='utf-8').read(256)
        except Exception:
            report['ok'] = False
            report['notes'].append('Packages.gz exists but could not be read.')
    else:
        report['ok'] = False
        report['notes'].append('Packages or Packages.gz is missing.')
    if not debs:
        report['notes'].append('No .deb packages were found in the offline repo root.')
    if driver_vault:
        dv = Path(driver_vault).resolve()
        if dv.is_dir():
            report['driver_deb_count'] = len(list(dv.glob('*.deb')))
        else:
            report['notes'].append('Driver vault path is set but missing.')
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', required=True)
    ap.add_argument('--driver-vault', default='')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    rep = validate_repo(args.repo, driver_vault=args.driver_vault)
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(args.out)
    return 0 if rep.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
