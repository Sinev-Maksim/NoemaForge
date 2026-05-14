#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/bootstrap/microvm/noemaforge-microvm-run.py
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


# === NoemaForge Autodoc File Header ===
# File: bootstrap/microvm/noemaforge-microvm-run.py
# Purpose: Validate the delegated microVM runner contract and emit structured diagnostics for sandbox wiring tests.
# Invoked by / imported from:
#   - direct CLI entrypoint
# Public API / entry functions:
#   - _load_spec
#   - _validate_spec
#   - main
# Inputs:
#   - --spec
#   - JSON runner spec produced by sandbox._run_microvm
# Output formats / side effects:
#   - JSON written to stdout
# AutoDoc: refreshed 2026-04-09 (manual)
# === End NoemaForge Autodoc File Header ===

"""Reference microVM runner interface for NoemaForge.

This script implements the delegated runner contract expected by
``sandbox._run_microvm`` as a deterministic contract-validation backend.
Real guest execution remains host-specific (firecracker, qemu,
cloud-hypervisor, image build, mounts, and IO plumbing).

The wrapper does not claim to boot a guest. Instead it validates the shape of
the requested runner spec so that NoemaForge can verify sandbox wiring even on
hosts where no microVM backend is installed.
"""


import argparse
import base64
import json
import sys
from typing import Any, Dict, List


# === NoemaForge Autodoc Function Header ===
# Function: _load_spec(path: str)
# Purpose: Load a microVM spec from disk without crashing the wrapper.
# Inputs:
#   - path: str
# Called by:
#   - main
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _load_spec(path: str) -> Dict[str, Any]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            obj = json.load(f) or {}
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _validate_spec(spec: Dict[str, Any])
# Purpose: Validate the core spec shape expected by sandbox._run_microvm.
# Inputs:
#   - spec: Dict[str, Any]
# Called by:
#   - main
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _validate_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    required = {
        'argv': list,
        'cwd': str,
        'env': dict,
        'quota': dict,
        'mounts': dict,
        'allow_network': bool,
    }
    missing: List[str] = []
    invalid: List[str] = []
    for key, typ in required.items():
        if key not in spec:
            missing.append(key)
            continue
        val = spec.get(key)
        if not isinstance(val, typ):
            invalid.append(f'{key}:{type(val).__name__}')

    quota = spec.get('quota') if isinstance(spec.get('quota'), dict) else {}
    quota_missing = [
        k for k in ('cpu_time_sec', 'mem_max_mib', 'pids_max', 'file_max_mib', 'timeout_sec')
        if k not in quota
    ]

    mounts = spec.get('mounts') if isinstance(spec.get('mounts'), dict) else {}
    mount_invalid: List[str] = []
    for key in ('ro', 'rw'):
        val = mounts.get(key)
        if val is None:
            mount_invalid.append(f'mounts.{key}:missing')
        elif not isinstance(val, list):
            mount_invalid.append(f'mounts.{key}:{type(val).__name__}')

    return {
        'valid': not missing and not invalid and not quota_missing and not mount_invalid,
        'missing': missing,
        'invalid': invalid,
        'quota_missing': quota_missing,
        'mount_invalid': mount_invalid,
    }


# === NoemaForge Autodoc Function Header ===
# Function: main(argv: List[str] | None = None)
# Purpose: Validate the spec and emit a structured contract-diagnostics payload.
# Inputs:
#   - argv: List[str] | None = None
# Called by:
#   - CLI entrypoint
# Returns / emits: int
# Side effects:
#   - reads files
#   - writes JSON to stdout
# === End NoemaForge Autodoc Function Header ===
def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--spec', required=True)
    args = ap.parse_args(argv)

    spec = _load_spec(args.spec)
    validation = _validate_spec(spec)

    lines = [
        'NoemaForge microVM contract-validation runner.',
        'This backend validates the delegated runner spec but does not boot a guest.',
        'Install a real runtime and point sandbox-policy.yaml backends.microvm.runtime',
        'to that binary when live microVM execution is required.',
    ]
    if validation['valid']:
        lines.append('Spec validation: OK')
    else:
        lines.append('Spec validation: FAILED')
        if validation['missing']:
            lines.append('Missing keys: ' + ', '.join(validation['missing']))
        if validation['invalid']:
            lines.append('Invalid types: ' + ', '.join(validation['invalid']))
        if validation['quota_missing']:
            lines.append('Missing quota keys: ' + ', '.join(validation['quota_missing']))
        if validation['mount_invalid']:
            lines.append('Mount issues: ' + ', '.join(validation['mount_invalid']))
    msg = '\n'.join(lines) + '\n'

    out = {
        'exit_code': 126,
        'stdout_b64': base64.b64encode(b'').decode('ascii'),
        'stderr_b64': base64.b64encode(msg.encode('utf-8')).decode('ascii'),
        'meta': {
            'backend': 'microvm',
            'isolation': 'microvm',
            'supported': False,
            'mode': 'contract_validation',
            'spec_valid': bool(validation.get('valid')),
            'missing': list(validation.get('missing') or []),
            'invalid': list(validation.get('invalid') or []),
            'quota_missing': list(validation.get('quota_missing') or []),
            'mount_invalid': list(validation.get('mount_invalid') or []),
            'run_id': spec.get('run_id'),
        },
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
